"""Synthetic repair metadata/provider fixtures with real gateway authentication and persistence."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from infra import verify_repaired_search as probe
from infra import recover_retrieval_index as repair
from tests import test_restored_data_api as common
from tests import test_restored_retrieval_api as retrieval


class RepairedSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_case = probe.ROOT / '.local/restored-api' / uuid4().hex
        cls.addClassCleanup(common.remove_owned, cls.source_case, probe.ROOT / '.local/restored-api')
        state = cls.source_case / 'state'; (state / 'knowledge').mkdir(parents=True)
        retrieval.RestoredRetrievalApiTests.configure_model(state)
        index = state / 'knowledge/index.json'
        cls.original_index = index.read_bytes()
        cls.source = index
        index.rename(cls.source_case / 'retained-knowledge-index.json')
        plan = {'with_retrieval': True, 'with_retrieval_recovery': True, 'with_prediction': False,
                'files': {'knowledge/index.json': probe.checksum(cls.source_case / 'retained-knowledge-index.json')}}
        (cls.source_case / 'plan.json').write_text(json.dumps(plan))
        record, cls.report = repair.run_repair(cls.source_case, probe.checksum(cls.source_case / 'plan.json'), offline=True)
        cls.addClassCleanup(common.remove_owned, cls.report.parent, probe.ROOT / '.local/index-repairs')
        cls.revision = 'a' * 40
        # Explicit synthetic admission metadata, not an original operator/release attestation.
        record['toolkit_identity'].update(source_revision=cls.revision, working_tree_changes=False)
        cls.raw = json.dumps(record).encode(); cls.report.write_bytes(cls.raw)
        cls.pin = probe.checksum(cls.report)

    def tearDown(self):
        self.report.write_bytes(self.raw); self.source.write_bytes(self.original_index)

    def test_repair_pins_revision_and_tool_hash_required(self):
        for change in ('pin', 'revision', 'verifier', 'failed'):
            record = json.loads(self.raw)
            if change == 'verifier': record['repair_tool_sha256'] = '0' * 64
            if change == 'failed': record['passed'] = False
            self.report.write_text(json.dumps(record))
            with self.subTest(change=change), self.assertRaises(ValueError):
                probe.admit(self.report, '0' * 64 if change == 'pin' else probe.checksum(self.report),
                            'b' * 40 if change == 'revision' else self.revision)

    def test_changed_repaired_artifact_refused_before_services(self):
        self.source.write_bytes(self.original_index + b' ')
        with patch.object(probe.subprocess, 'Popen') as launch, self.assertRaisesRegex(ValueError, 'artifact_changed'):
            probe.run_check(self.report, self.pin, self.revision)
        launch.assert_not_called()

    def test_invalid_ports_refused_before_source_read(self):
        with patch.object(probe, 'admit') as read:
            for web, api in ((80,18202), (18280,18280), (True,18202)):
                with self.subTest(ports=(web,api)), self.assertRaises(ValueError):
                    probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api)
            read.assert_not_called()

    def test_worker_failure_is_sanitized_and_starts_no_services(self):
        web, api = common.free_ports()
        with (patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([],1,'','PRIVATE FAILURE')),
              patch.object(probe.subprocess, 'Popen') as launch, redirect_stdout(io.StringIO())):
            report, path = probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api)
        self.addCleanup(common.remove_owned, path.parent, probe.ROOT / '.local/repaired-search')
        self.assertFalse(report['passed']); self.assertEqual(report['failed_stage'], 'prepare_synthetic_state')
        self.assertNotIn('PRIVATE FAILURE', path.read_text()); self.assertTrue(report['owned_services_stopped'])
        launch.assert_not_called()

    def test_normal_http_search_restart_viewer_and_logout_on_fresh_synthetic_state(self):
        real_run, real_start = subprocess.run, subprocess.Popen
        def run(command, **kwargs):
            if len(command)>2 and command[1]=='-c' and 'from infra.verify_repaired_search import ' in command[2]:
                command = [*command[:2], retrieval.PREFIX + command[2], *command[3:]]
            return real_run(command, **kwargs)
        def start(command, **kwargs):
            if command[1:3] == ['-m','uvicorn']:
                command = [sys.executable,'-c',retrieval.PREFIX + "import os,uvicorn;uvicorn.run('services.api.main:app',host='127.0.0.1',port=int(os.environ['AIN_API_PORT']),access_log=False,log_level='warning')"]
            return real_start(command, **kwargs)
        web, api = common.free_ports()
        with patch.object(probe.subprocess, 'run', side_effect=run), patch.object(probe.subprocess, 'Popen', side_effect=start), redirect_stdout(io.StringIO()):
            report, path = probe.run_check(self.report, self.pin, self.revision, web_port=web, api_port=api)
        self.addCleanup(common.remove_owned, path.parent, probe.ROOT / '.local/repaired-search')
        self.assertTrue(report['passed'], report)
        self.assertTrue(all(report['checks'].values())); self.assertTrue(all(report['state_checks'].values()))
        self.assertEqual(len(report['run_ids']), 2); self.assertEqual(report['evidence_counts'][1],0)
        self.assertTrue(report['embedding_inference_executed']); self.assertTrue(report['owned_services_stopped'])
        self.assertFalse(report['generation_requested']); self.assertFalse(report['original_database_accessed'])
        self.assertEqual(report['fixture_flight_records'],0)
        self.assertEqual(self.original_index,self.source.read_bytes()); self.assertEqual(self.raw,self.report.read_bytes())


if __name__ == '__main__': unittest.main()
