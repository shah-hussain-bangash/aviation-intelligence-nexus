from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from infra.releases import CONTRACTS, PROJECT, compatible, drill, override_document, validate_release, deployed_images
from infra.status import rollback_drill_status


def release(version='a' * 40, byte='a'):
    return {'format': 'ain-local-release-v1', 'schema_version': 7, 'source_revision': version,
            'images': {'api': 'sha256:' + byte * 64, 'web': 'sha256:' + byte * 64},
            'contracts': {key: 'f' * 64 for key in CONTRACTS}}


def facts():
    return {'schema_version': 7, 'active_jobs': 0, 'row_counts': {'flights': 100},
            'account_fingerprint': 'DO-NOT-EXPOSE', 'probability': .14}


class ReleaseTests(unittest.TestCase):
    def test_only_complete_immutable_image_pairs_are_accepted(self):
        self.assertIsNotNone(validate_release(release()))
        bad = release(); bad['images']['api'] = 'ain-api:latest'
        with self.assertRaises(ValueError): validate_release(bad)
        bad = release(); bad['contracts'].pop(CONTRACTS[0])
        with self.assertRaises(ValueError): validate_release(bad)

    def test_schema_contract_changes_or_active_jobs_block_rollback(self):
        current, target = release(), release('b' * 40, 'b')
        compatible(current, target, facts())
        for state in [{**facts(), 'active_jobs': 1}, {**facts(), 'schema_version': 8}]:
            with self.assertRaises(ValueError): compatible(current, target, state)
        target['contracts'][CONTRACTS[0]] = 'e' * 64
        with self.assertRaises(ValueError): compatible(current, target, facts())

    def test_override_contains_only_pinned_images_and_disabled_drill_worker(self):
        override = override_document(release())
        self.assertEqual(override['services']['api']['image'], release()['images']['api'])
        self.assertEqual(override['services']['api']['environment'], {'AIN_AGENT_JOBS': '0'})
        self.assertNotIn('volumes', json.dumps(override))

    def test_invalid_schema_and_ambiguous_state_cannot_qualify(self):
        for version in (0, -1, True):
            value=release();value['schema_version']=version
            with self.assertRaises(ValueError):validate_release(value)
        current,target=release(),release('b'*40,'b')
        for state in ({**facts(),'schema_version':True},{**facts(),'active_jobs':False},{**facts(),'active_jobs':-1},{}):
            with self.assertRaises(ValueError):compatible(current,target,state)

    def test_schema8_to_schema7_pair_is_rejected_before_any_docker_access(self):
        current,target=release(),release('b'*40,'b');current['schema_version']=8
        with patch('infra.releases.inspect_release') as inspect,patch('infra.releases.deployed_images') as deployed,patch('infra.releases.verify') as verify,patch('infra.releases.state_facts') as state,patch('infra.releases.switch') as switch:
            with self.assertRaisesRegex(ValueError,'Schema rollback'):drill(current,target)
            for operation in (inspect,deployed,verify,state,switch):operation.assert_not_called()

    def test_changed_contracts_are_rejected_before_any_docker_access(self):
        current,target=release(),release('b'*40,'b');target['contracts'][CONTRACTS[0]]='e'*64
        with patch('infra.releases.inspect_release') as inspect,patch('infra.releases.switch') as switch:
            with self.assertRaisesRegex(ValueError,'State contracts changed'):drill(current,target)
            inspect.assert_not_called();switch.assert_not_called()

    def test_primary_or_host_state_mount_cannot_be_used_for_the_drill(self):
        container = {'Config': {'Labels': {'com.docker.compose.project': PROJECT}},
                     'Image': release()['images']['api'],
                     'Mounts': [{'Destination': '/app/.local', 'Type': 'volume', 'Name': 'ain-local-release_state'}]}
        with patch('infra.releases.compose', return_value='fixture-id'), patch('infra.releases.docker', return_value=json.dumps([container])):
            with self.assertRaises(ValueError): deployed_images(PROJECT)

    def run_drill(self, states, switching=None):
        current, target = release(), release('b' * 40, 'b')
        patches = [patch('infra.releases.inspect_release', side_effect=[current, target]),
                   patch('infra.releases.deployed_images', return_value=current['images']),
                   patch('infra.releases.verify', return_value={'passed': True}),
                   patch('infra.releases.state_facts', side_effect=states),
                   patch('infra.releases.switch', side_effect=switching)]
        with patches[0], patches[1], patches[2], patches[3], patches[4] as switch:
            result = drill(current, target)
            self.assertEqual(switch.call_args_list[0].args[0], target)
            self.assertEqual(switch.call_args_list[1].args[0], current)
            return result

    def test_success_receipt_excludes_private_state_fingerprint(self):
        result = self.run_drill([facts(), facts(), facts()])
        self.assertTrue(result['candidate_returned_healthy'])
        self.assertFalse(result['production_qualified'])
        self.assertNotIn('DO-NOT-EXPOSE', json.dumps(result))

    def test_failed_target_health_attempts_candidate_recovery(self):
        current, target = release(), release('b' * 40, 'b')
        with patch('infra.releases.inspect_release', side_effect=[current, target]), patch('infra.releases.deployed_images', return_value=current['images']), patch('infra.releases.verify', return_value={'passed': True}), patch('infra.releases.state_facts', return_value=facts()), patch('infra.releases.switch', side_effect=[RuntimeError('target unhealthy'), {}]) as switch:
            with self.assertRaises(RuntimeError): drill(current, target)
            self.assertEqual(switch.call_count, 2)
            self.assertEqual(switch.call_args_list[-1].args[0], current)

    def test_changed_state_never_produces_a_success_receipt(self):
        with self.assertRaises(RuntimeError):
            self.run_drill([facts(), {**facts(), 'probability': .9}])

    def test_ui_receipt_requires_every_check_and_excludes_unrecognized_fields(self):
        receipt = self.run_drill([facts(), facts(), facts()])
        receipt['private_path'] = 'DO-NOT-EXPOSE'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rollback-drill.json'
            self.assertFalse(rollback_drill_status(folder)['recorded'])
            path.write_text(json.dumps(receipt))
            self.assertTrue(rollback_drill_status(folder)['recorded'])
            self.assertNotIn('DO-NOT-EXPOSE', json.dumps(rollback_drill_status(folder)))
            receipt['row_counts_preserved'] = False
            path.write_text(json.dumps(receipt))
            self.assertFalse(rollback_drill_status(folder)['recorded'])
