"""Real authentication/proxy/history transport with an explicitly synthetic embedding fixture."""
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests import test_restored_data_api as fixture
from infra import restored_data_api as probe
from rag import index, ollama

PREFIX = """from unittest.mock import patch
from rag import ollama
patch.object(ollama,'models',return_value={ollama.EMBED_MODEL:'a'*64}).start()
patch.object(ollama,'embed',side_effect=lambda texts:[[1.0]*768 for _ in texts]).start()
patch.object(ollama,'generate',side_effect=AssertionError('generation_not_allowed')).start()
"""


class RestoredRetrievalApiTests(unittest.TestCase):
    @classmethod
    def configure_model(cls, state):
        chunks, sources = [], []
        for name in index.SOURCES:
            raw = (index.ROOT / name).read_bytes()
            chunks.extend(index.chunks_for(name, raw.decode('utf-8')))
            sources.append({'path': name, 'sha256': index.digest(raw)})
        payload = {'version': 1, 'revision': 'b' * 40, 'embedding_model': ollama.EMBED_MODEL,
                   'embedding_digest': 'a' * 64, 'sources': sources, 'chunks': chunks,
                   'vectors': [[1.0] * 768 for _ in chunks]}
        (state / 'knowledge/index.json').write_text(json.dumps({'payload': payload,
            'sha256': index.digest(json.dumps(payload, sort_keys=True).encode())}))

    @classmethod
    def setUpClass(cls): fixture.RestoredDataApiTests.setUpClass.__func__(cls)

    def test_combined_modes_and_nonboolean_flag_refused_before_report_read(self):
        with patch.object(probe, 'admit') as admit:
            for kwargs in ({'with_retrieval': 1}, {'with_retrieval': True, 'with_prediction': True, 'trusted_local_model': True}):
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'separate_retrieval'):
                    probe.run_check(self.report, self.pin, self.revision, **kwargs)
            admit.assert_not_called()

    def test_missing_index_refused_before_owned_services(self):
        record = json.loads(self.raw); record['artifact_sha256'].pop('knowledge/index.json')
        altered = self.case / 'report.json'
        try:
            altered.write_text(json.dumps(record))
            with patch.object(probe.subprocess, 'Popen') as start, self.assertRaisesRegex(ValueError, 'retrieval_index_required'):
                probe.run_check(altered, probe.checksum(altered), self.revision, with_retrieval=True)
            start.assert_not_called()
        finally:
            altered.write_bytes(self.raw)

    def test_forged_corpus_and_changed_provider_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory); (state / 'knowledge').mkdir()
            original = json.loads((self.case / 'restored/knowledge/index.json').read_text())
            for changed in ('corpus', 'provider'):
                envelope = json.loads(json.dumps(original))
                if changed == 'corpus':
                    envelope['payload']['chunks'][0]['text'] += ' invented text'
                    envelope['sha256'] = index.digest(json.dumps(envelope['payload'], sort_keys=True).encode())
                (state / 'knowledge/index.json').write_text(json.dumps(envelope))
                with patch.dict(os.environ, AIN_OLLAMA_HOST='127.0.0.1'), patch.object(ollama, 'models', return_value={ollama.EMBED_MODEL:'c'*64}), self.assertRaises((ValueError, RuntimeError)):
                    probe.retrieval_knowledge(state)

    def test_real_http_saved_retrieval_restart_owner_boundary_and_row_tamper(self):
        real_run, real_start = subprocess.run, subprocess.Popen
        def run(command, **kwargs):
            if len(command) > 2 and command[1] == '-c' and 'from infra.restored_data_api import ' in command[2]:
                command = [*command[:2], PREFIX + command[2], *command[3:]]
            return real_run(command, **kwargs)
        def start(command, **kwargs):
            if command[1:3] == ['-m', 'uvicorn']:
                code = PREFIX + "import os,uvicorn;uvicorn.run('services.api.main:app',host='127.0.0.1',port=int(os.environ['AIN_API_PORT']),access_log=False,log_level='warning')"
                command = [sys.executable, '-c', code]
            return real_start(command, **kwargs)
        web, api = fixture.free_ports()
        source_pin = probe.checksum(self.case / 'restored/ain.sqlite3')
        with patch.object(probe.subprocess, 'run', side_effect=run), patch.object(probe.subprocess, 'Popen', side_effect=start), redirect_stdout(io.StringIO()):
            report, target = probe.run_check(self.report, self.pin, self.revision,
                                            web_port=web, api_port=api, with_retrieval=True)
        self.addCleanup(fixture.remove_owned, target.parent, probe.ROOT / '.local/restored-api')
        self.assertTrue(report['passed'], report)
        self.assertTrue(all(report['retrieval_checks'].values()))
        self.assertTrue(report['copy_state_checks']['two_bound_probe_retrievals_only'])
        self.assertEqual(report['retrieval']['evidence_counts'][1], 0)
        self.assertFalse(report['retrieval']['generation_requested'])
        self.assertTrue(report['retrieval_requested'])
        self.assertTrue(report['inference_executed'])
        self.assertTrue(report['embedding_inference_executed'])
        self.assertFalse(report['prediction_requested'])
        self.assertTrue(report['owned_services_stopped'])
        self.assertEqual(source_pin, probe.checksum(self.case / 'restored/ain.sqlite3'))
        state = target.parent / 'state'
        with closing(sqlite3.connect(state / 'ain.sqlite3')) as db, db:
            row = db.execute('SELECT id,result_json FROM knowledge_runs WHERE id=?', (report['retrieval']['run_ids'][0],)).fetchone()
            result = json.loads(row[1]); result['question'] = 'altered'
            db.execute('UPDATE knowledge_runs SET result_json=? WHERE id=?', (json.dumps(result), row[0]))
        env = {k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_OLLAMA_HOST='127.0.0.1', AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state/'ain.sqlite3'))
        code = PREFIX + 'import sys;from infra.restored_data_api import inspect_after;inspect_after(sys.argv[1])'
        failed = real_run([sys.executable, '-c', code, str(target.parent)], env=env, cwd=probe.ROOT, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('stored_retrieval_binding_failed', failed.stderr)


if __name__ == '__main__': unittest.main()
