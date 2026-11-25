"""Synthetic index/provider fixtures; no Ollama daemon is required by these tests."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from infra import retrieval_recovery as recovery
from rag import index, ollama


class RetrievalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name)
        self.snapshot = self.root / 'snapshot'; (self.snapshot / 'knowledge').mkdir(parents=True)
        chunks = []; sources = []
        for source in index.SOURCES:
            raw = (index.ROOT / source).read_bytes()
            sources.append({'path': source, 'sha256': index.digest(raw)})
            chunks.extend(index.chunks_for(source, raw.decode('utf-8')))
        self.payload = {'version': 1, 'revision': 'b' * 40, 'embedding_model': ollama.EMBED_MODEL,
                        'embedding_digest': 'a' * 64, 'sources': sources, 'chunks': chunks,
                        'vectors': [[1.0] * 768 for _ in chunks]}
        self.pin = self.refresh()

    def tearDown(self): self.temporary.cleanup()

    def refresh(self):
        file = self.snapshot / recovery.INDEX_FILE
        file.write_text(json.dumps({'payload': self.payload,
                                    'sha256': index.digest(json.dumps(self.payload, sort_keys=True).encode())}))
        self.manifest = {'format': 'ain-recovery-v1', 'snapshot_id': str(uuid4()), 'database': {'schema_version': 7},
                         'files': [{'path': recovery.INDEX_FILE, 'size_bytes': file.stat().st_size,
                                    'sha256': recovery.checksum(file)}]}
        path = self.snapshot / 'manifest.json'; path.write_text(json.dumps(self.manifest))
        return recovery.checksum(path)

    def test_admission_needs_no_original_database_or_provider_calls(self):
        with patch.object(ollama, 'models') as models, patch.object(ollama, 'embed') as embed:
            _, entry, digest = recovery.admit(self.snapshot, self.pin)
        self.assertEqual(entry['path'], recovery.INDEX_FILE)
        self.assertEqual(digest, 'a' * 64)
        self.assertFalse((self.snapshot / 'ain.sqlite3').exists())
        models.assert_not_called(); embed.assert_not_called()

    def test_changed_manifest_or_index_pin_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'manifest_pin'):
            recovery.admit(self.snapshot, '0' * 64)
        file = self.snapshot / recovery.INDEX_FILE; file.write_bytes(file.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'index_pin'):
            recovery.admit(self.snapshot, self.pin)

    def test_self_consistent_forged_chunk_still_fails_corpus_binding(self):
        self.payload['chunks'][0]['text'] += '\nInvented instruction not in the approved document.'
        pin = self.refresh()
        with self.assertRaisesRegex(ValueError, 'corpus_chunk_binding'):
            recovery.admit(self.snapshot, pin)

    def test_duplicate_and_traversal_inventory_are_refused(self):
        entry = self.manifest['files'][0]
        for entries in ([entry, entry], [entry, {'path': '../outside', 'sha256': '0' * 64, 'size_bytes': 1}]):
            self.manifest['files'] = entries
            path = self.snapshot / 'manifest.json'; path.write_text(json.dumps(self.manifest))
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, 'inventory'):
                recovery.admit(self.snapshot, recovery.checksum(path))

    def test_invalid_dense_vectors_are_refused_without_a_provider(self):
        self.payload['vectors'] = [[1.0] * 767 for _ in self.payload['chunks']]
        pin = self.refresh()
        with self.assertRaisesRegex(RuntimeError, 'embedding matrix'):
            recovery.admit(self.snapshot, pin)

    def test_worker_failure_is_generic_and_original_index_is_preserved(self):
        original = recovery.checksum(self.snapshot / recovery.INDEX_FILE)
        # The report fingerprints its versioned file-parsing helper as well.
        helper = self.root / 'infra/research_model_recovery.py'; helper.parent.mkdir()
        shutil.copyfile(recovery.ROOT / 'infra/research_model_recovery.py', helper)
        with patch.object(recovery, 'ROOT', self.root), patch.object(recovery.subprocess, 'run',
             return_value=subprocess.CompletedProcess([], 1, '', 'PRIVATE PROVIDER FAILURE')), redirect_stdout(io.StringIO()):
            report, path = recovery.run_check(self.snapshot, self.pin)
        self.assertFalse(report['passed'])
        self.assertEqual(report['error'], 'retrieval_recovery_unverified')
        self.assertNotIn('PRIVATE PROVIDER FAILURE', path.read_text())
        self.assertEqual(recovery.checksum(self.snapshot / recovery.INDEX_FILE), original)

    def worker(self, *, changed_provider=False):
        base = recovery.ROOT / '.local/retrieval-recovery'; base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            case = Path(directory).resolve(); self.assertEqual(case.parent, base.resolve())
            state = case / 'state'; (state / 'knowledge').mkdir(parents=True)
            shutil.copyfile(self.snapshot / recovery.INDEX_FILE, state / recovery.INDEX_FILE)
            (case / 'plan.json').write_text(json.dumps({'index_sha256': recovery.checksum(state / recovery.INDEX_FILE),
                                                      'embedding_digest': 'a' * 64}))
            env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
            env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                       AIN_OLLAMA_HOST='127.0.0.1', AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
            code = '''import json,sys
from unittest.mock import patch
from rag import ollama
from infra.retrieval_recovery import execute_case
with patch.object(ollama,'models',return_value={ollama.EMBED_MODEL:sys.argv[2]}), patch.object(ollama,'embed',side_effect=lambda texts:[[1.0]*768 for _ in texts]), patch.object(ollama,'generate',side_effect=AssertionError('Generation must remain disabled')):
    result=execute_case(sys.argv[1])
print(json.dumps(result))
'''
            return subprocess.run([sys.executable, '-c', code, str(case), 'c' * 64 if changed_provider else 'a' * 64],
                                  cwd=recovery.ROOT, env=env, capture_output=True, text=True, timeout=120)

    def test_real_worker_flow_restores_index_and_preserves_scopes_and_abstention(self):
        # Provider vectors are deliberately synthetic; this is not live embedding evidence.
        result = self.worker()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['passed']); self.assertTrue(all(report['checks'].values()))
        self.assertEqual([r['mode'] for r in report['retrieval_results']], ['evidence_only', 'evidence_only', 'abstained'])
        self.assertEqual(report['restoration']['session_revocation_event_id'],
                         report['offline_consistency']['session_revocation_event_id'])
        self.assertFalse(report['index_rebuilt']); self.assertFalse(report['generation_evaluated'])

    def test_worker_refuses_changed_embedding_provider(self):
        result = self.worker(changed_provider=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('embedding_provider_unavailable_or_changed', result.stderr)


if __name__ == '__main__': unittest.main()
