"""Simulated Docker client timeout; no real container or daemon is used."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from infra import packaged_recovery_rehearsal as runner


class PackagedRehearsalCleanupTests(unittest.TestCase):
    def exercise(self, *, wrong_identity=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def run(command, **kwargs):
                calls.append(command)
                if command[1] == 'run':
                    raise subprocess.TimeoutExpired(command, 180)
                return subprocess.CompletedProcess(command, 0)

            def output(command, **kwargs):
                if command[1] == 'ps': return 'isolated-id\n'
                case = next((root / '.local/packaged-image-recovery').iterdir())
                return json.dumps([{'Name': '/ain-image-recovery-check-' + case.name[:12],
                                    'Config': {'Labels': {'ain.synthetic-recovery':
                                              'wrong' if wrong_identity else case.name}}}])

            images = {'api': 'sha256:' + 'a' * 64, 'web': 'sha256:' + 'b' * 64}
            revision = 'c' * 40
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'toolkit_identity', return_value={}), \
                 patch.object(runner, 'inspect_release', return_value={'source_revision': revision, 'schema_version': 8, 'contracts': {}}), \
                 patch.object(runner, 'contract_digest', return_value='same'), \
                 patch.object(runner, 'current_contract_digest', return_value='same'), \
                 patch.object(runner.subprocess, 'run', side_effect=run), \
                 patch.object(runner.subprocess, 'check_output', side_effect=output), redirect_stdout(io.StringIO()):
                result = runner.run_check(images['api'], images['web'], revision)
            report = json.loads(next(root.glob('.local/packaged-image-recovery/*/report.json')).read_text())
            self.assertEqual(result, 2)
            self.assertFalse(report['passed'])
            return report, calls

    def test_timed_out_client_removes_only_the_label_and_name_bound_probe(self):
        report, calls = self.exercise()
        self.assertTrue(report['temporary_probe_cleaned'])
        self.assertEqual(calls[-1], ['docker', 'rm', '-f', 'isolated-id'])

    def test_unexpected_identity_is_preserved_and_cleanup_is_unqualified(self):
        report, calls = self.exercise(wrong_identity=True)
        self.assertEqual(report['error'], 'probe_cleanup_unverified')
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
