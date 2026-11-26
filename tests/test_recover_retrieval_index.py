"""Synthetic index/crash fixtures; no model service or flight database is needed."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from infra import recover_retrieval_index as repair
from rag import index, ollama


class RecoverRetrievalIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.case = self.root / '.local/restored-api' / ('a' * 32)
        self.target = self.case / 'state/knowledge/index.json'; self.target.parent.mkdir(parents=True)
        self.retained = self.case / 'retained-knowledge-index.json'
        chunks, sources = [], []
        for name in index.SOURCES:
            raw = (index.ROOT / name).read_bytes()
            chunks.extend(index.chunks_for(name, raw.decode('utf-8')))
            sources.append({'path': name, 'sha256': index.digest(raw)})
        self.payload = {'version': 1, 'revision': 'b' * 40, 'embedding_model': ollama.EMBED_MODEL,
                        'embedding_digest': 'a' * 64, 'sources': sources, 'chunks': chunks,
                        'vectors': [[1.] * 768 for _ in chunks]}
        self.retained.write_text(json.dumps({'payload': self.payload,
            'sha256': index.digest(json.dumps(self.payload, sort_keys=True).encode())}))
        self.plan = {'with_retrieval': True, 'with_retrieval_recovery': True, 'with_prediction': False,
                     'files': {'knowledge/index.json': repair.checksum(self.retained)}}
        self.refresh_plan()

    def refresh_plan(self):
        self.plan_path = self.case / 'plan.json'
        self.plan_path.write_text(json.dumps(self.plan))
        self.pin = repair.checksum(self.plan_path)

    def run_repair(self):
        with patch.object(repair, 'ROOT', self.root):
            return repair.run_repair(self.case, self.pin, offline=True)

    def test_offline_and_exact_plan_pin_required_before_file_access(self):
        with patch.object(repair, 'ordinary') as read:
            with self.assertRaisesRegex(ValueError, 'offline_declaration'):
                repair.admit(self.case, self.pin)
            read.assert_not_called()
        with patch.object(repair, 'ROOT', self.root), self.assertRaisesRegex(ValueError, 'plan_pin_mismatch'):
            repair.admit(self.case, '0' * 64, offline=True)
        self.assertFalse(self.target.exists())

    def test_repair_preserves_source_and_never_contacts_database_or_provider(self):
        original = self.retained.read_bytes()
        with patch.object(sqlite3, 'connect') as db, patch.object(ollama, 'models') as models, patch.object(ollama, 'embed') as embed:
            report, path = self.run_repair()
        db.assert_not_called(); models.assert_not_called(); embed.assert_not_called()
        self.assertTrue(report['passed']); self.assertTrue(path.is_file())
        self.assertFalse(report['service_shutdown_verified']); self.assertFalse(report['production_ready'])
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.retained.read_bytes(), original)
        self.target.write_bytes(b'later rebuild')
        self.assertEqual(self.retained.read_bytes(), original)  # Independent copy, not a hardlink.
        with self.assertRaisesRegex(ValueError, 'missing_index_destination'):
            self.run_repair()
        self.assertEqual(self.target.read_bytes(), b'later rebuild')

    def test_forged_corpus_cannot_be_admitted_by_repinning_envelope_and_plan(self):
        self.payload['chunks'][0]['text'] += ' invented text'
        self.retained.write_text(json.dumps({'payload': self.payload,
            'sha256': index.digest(json.dumps(self.payload, sort_keys=True).encode())}))
        self.plan['files']['knowledge/index.json'] = repair.checksum(self.retained); self.refresh_plan()
        with self.assertRaisesRegex(ValueError, 'corpus_binding'):
            self.run_repair()
        self.assertFalse(self.target.exists())

    def test_wrong_mode_changed_retained_bytes_and_nonowned_case_refused(self):
        with patch.object(repair, 'ROOT', self.root), self.assertRaisesRegex(ValueError, 'owned_retrieval_case'):
            repair.admit(self.root, self.pin, offline=True)
        self.plan['with_retrieval_recovery'] = False; self.refresh_plan()
        with self.assertRaisesRegex(ValueError, 'recovery_plan'):
            self.run_repair()
        self.plan['with_retrieval_recovery'] = True; self.refresh_plan()
        self.retained.write_bytes(self.retained.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'retained_index_pin'):
            self.run_repair()
        self.assertFalse(self.target.exists())

    def test_invalid_model_identity_cannot_be_admitted_by_repinning(self):
        self.payload['embedding_model'] = 'unapproved-model'
        self.retained.write_text(json.dumps({'payload': self.payload,
            'sha256': index.digest(json.dumps(self.payload, sort_keys=True).encode())}))
        self.plan['files']['knowledge/index.json'] = repair.checksum(self.retained); self.refresh_plan()
        with self.assertRaisesRegex(ValueError, 'index_identity_invalid'):
            self.run_repair()
        self.assertFalse(self.target.exists())

    def test_destination_race_is_refused_without_overwriting_either_file(self):
        actual = repair.admit
        def admit_then_create(*args, **kwargs):
            admitted = actual(*args, **kwargs)
            self.target.write_bytes(b'unexpected destination')
            return admitted
        original = self.retained.read_bytes()
        with patch.object(repair, 'admit', side_effect=admit_then_create):
            report, path = self.run_repair()
        self.assertFalse(report['passed']); self.assertEqual(report['error'], 'index_repair_unverified')
        self.assertTrue(path.is_file())
        self.assertEqual(self.target.read_bytes(), b'unexpected destination')
        self.assertEqual(self.retained.read_bytes(), original)

    def test_real_abrupt_exit_leaves_retained_index_then_offline_repair_succeeds(self):
        self.retained.rename(self.target)
        code = """import os,sys
from pathlib import Path
from infra import restored_data_api as probe
probe.ROOT=Path(sys.argv[1])
with probe.missing_owned_index(Path(sys.argv[2]),sys.argv[3]):
    os._exit(23)
"""
        process = subprocess.run([sys.executable, '-c', code, str(self.root), str(self.case),
                                  self.plan['files']['knowledge/index.json']], capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 23)
        self.assertFalse(self.target.exists()); self.assertTrue(self.retained.is_file())
        report, _ = self.run_repair()
        self.assertTrue(report['passed'])
        self.assertEqual(repair.checksum(self.target), self.plan['files']['knowledge/index.json'])
        self.assertEqual(repair.checksum(self.retained), self.plan['files']['knowledge/index.json'])

    def test_cli_refuses_missing_offline_declaration(self):
        result = subprocess.run([sys.executable, '-m', 'infra.recover_retrieval_index', '--case', str(self.case),
                                 '--plan-sha256', self.pin], cwd=repair.ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['error'], 'index_repair_admission_refused')


if __name__ == '__main__': unittest.main()
