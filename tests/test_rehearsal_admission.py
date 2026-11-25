"""No Docker daemon required: negative boundaries of the versioned runbook."""
import copy
import subprocess
import sys
import unittest
from unittest.mock import patch

from infra import http_rehearsal
from infra.rehearsal_admission import admit_images, require, validate_configuration, toolkit_identity

PROJECT = 'ain-http-check-' + 'a' * 12
IMAGES = {'api': 'sha256:' + 'a' * 64, 'web': 'sha256:' + 'b' * 64}
REVISION = 'c' * 40


def configuration():
    common = {'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
              'restart': 'no', 'networks': {'default': None}}
    return {'name': PROJECT, 'volumes': {'state': {'name': PROJECT + '_state', 'external': False}},
            'networks': {'default': {'name': PROJECT + '_default'}},
            'services': {
                'api': {**copy.deepcopy(common), 'image': IMAGES['api'],
                        'environment': {'AIN_AGENT_JOBS': '0', 'AIN_MONITOR_ENABLED': '0',
                                        'AIN_STATE_ROOT': '/app/.local/active',
                                        'AIN_DB_PATH': '/app/.local/active/ain.sqlite3'},
                        'volumes': [{'type': 'volume', 'source': 'state', 'target': '/app/.local'}]},
                'web': {**copy.deepcopy(common), 'image': IMAGES['web'],
                        'ports': [{'host_ip': '127.0.0.1', 'published': '18090', 'target': 8080}]}}}


class RehearsalAdmissionTests(unittest.TestCase):
    def test_expected_isolated_configuration_is_admitted(self):
        admit_images(IMAGES, REVISION)
        self.assertTrue(validate_configuration(configuration(), PROJECT, PROJECT + '_state', 18090, IMAGES))

    def test_mutable_tags_and_short_revisions_are_refused_before_docker(self):
        with patch.object(http_rehearsal, 'inspect_release') as docker:
            for api, web, revision in [('ain-api:latest', IMAGES['web'], REVISION),
                                       (IMAGES['api'], IMAGES['web'], 'abc123'),
                                       (IMAGES['api'], 'not-an-image', REVISION)]:
                with self.subTest(api=api, web=web, revision=revision), self.assertRaises(ValueError):
                    http_rehearsal.main(api_image=api, web_image=web, expected_revision=revision)
            docker.assert_not_called()

    def test_primary_project_volume_and_privileged_port_are_refused(self):
        for project, volume, port in [('ain-local-release', 'ain-local-release_state', 18090),
                                       (PROJECT, 'ain-local-release_state', 18090),
                                       (PROJECT, PROJECT + '_state', 80),
                                       (PROJECT, PROJECT + '_state', True)]:
            with self.subTest(project=project, volume=volume, port=port), self.assertRaises(ValueError):
                validate_configuration(configuration(), project, volume, port, IMAGES)

    def test_unsafe_configurations_are_refused(self):
        def change(path, value):
            c = configuration(); target = c
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            return c
        variants = [
            (('volumes', 'state', 'external'), True),
            (('services', 'api', 'volumes'), [{'type': 'bind', 'source': '/primary', 'target': '/app/.local'}]),
            (('services', 'web', 'volumes'), [{'type': 'volume', 'source': 'state', 'target': '/secrets'}]),
            (('services', 'api', 'ports'), [{'host_ip': '0.0.0.0', 'published': '8002', 'target': 8002}]),
            (('services', 'web', 'ports'), [{'host_ip': '0.0.0.0', 'published': '18090', 'target': 8080}]),
            (('services', 'api', 'image'), 'ain-api:latest'),
            (('services', 'api', 'environment', 'AIN_AGENT_JOBS'), '1'),
            (('services', 'api', 'environment', 'AIN_MONITOR_ENABLED'), '1'),
            (('services', 'api', 'read_only'), False),
            (('services', 'web', 'cap_drop'), []),
            (('services', 'api', 'privileged'), True),
            (('services', 'api', 'network_mode'), 'host'),
            (('services', 'api', 'pid'), 'host'),
            (('services', 'api', 'restart'), 'always'),
            (('networks', 'default', 'name'), 'ain-local-release_default'),
            (('networks', 'default', 'external'), True),
            (('services', 'api', 'networks'), {'primary': None}),
        ]
        for path, value in variants:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_configuration(change(path, value), PROJECT, PROJECT + '_state', 18090, IMAGES)

    def test_guards_remain_enabled_under_python_optimization(self):
        result = subprocess.run([sys.executable, '-O', '-c',
                                 "from infra.rehearsal_admission import require;require(False,'refused')"],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ValueError: refused', result.stderr)

    def test_harness_provenance_is_separate_from_image_revision(self):
        identity = toolkit_identity()
        self.assertEqual(len(identity['harness_sha256']), 6)
        self.assertTrue(all(len(digest) == 64 for digest in identity['harness_sha256'].values()))


if __name__ == '__main__':
    unittest.main()
