from contextlib import closing
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from cryptography.cobblestone import Cobblestone128Encryptor
from infra.recovery import backup, checksum
from infra.sealed_recovery import seal, restore_sealed, create_key, load_key, key_path, MAGIC, CONTEXT
from services.api.main import initialize
from services.api.paths import ROOT
from infra.status import encrypted_drill_status


class SealedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        initialize(self.state / 'ain.sqlite3')
        with closing(sqlite3.connect(self.state / 'ain.sqlite3')) as db, db:
            db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic_test','1','2025-05-01','TEST','AAA','BBB')")
        self.snapshot = self.root / 'snapshot'
        backup(self.state, self.snapshot)
        self.key = Cobblestone128Encryptor.generate_key()
        self.encrypted = self.root / 'backup.ainseal'
        self.target = self.root / 'restored'

    def tearDown(self):
        self.temp.cleanup()

    def test_encrypted_roundtrip_preserves_rows_and_authenticates_receipt(self):
        source_hash = checksum(self.snapshot / 'ain.sqlite3')
        result = seal(self.snapshot, self.encrypted, self.key)
        self.assertTrue(result['encrypted'])
        self.assertNotIn(b'SQLite format 3', self.encrypted.read_bytes())
        receipt = restore_sealed(self.encrypted, self.target, self.key)
        self.assertTrue(receipt['encrypted_source_authenticated'])
        self.assertEqual(receipt['flight_records'], 1)
        self.assertTrue(receipt['sessions_revoked'])
        self.assertEqual(source_hash, checksum(self.snapshot / 'ain.sqlite3'))

    def test_wrong_key_and_modified_truncated_or_appended_ciphertext_leave_no_target(self):
        seal(self.snapshot, self.encrypted, self.key)
        original = self.encrypted.read_bytes()
        for variant, key in [(original, Cobblestone128Encryptor.generate_key()),
                             (original[:-1], self.key), (original + b'append', self.key),
                             (original[:40] + bytes([original[40] ^ 1]) + original[41:], self.key)]:
            self.encrypted.write_bytes(variant)
            with self.assertRaises(ValueError):
                restore_sealed(self.encrypted, self.target, key)
            self.assertFalse(self.target.exists())
            self.assertEqual(list(self.root.glob('.ain-unseal-*')), [])

    def test_seal_and_restore_refuse_existing_outputs(self):
        seal(self.snapshot, self.encrypted, self.key)
        digest = checksum(self.encrypted)
        with self.assertRaises(FileExistsError):
            seal(self.snapshot, self.encrypted, self.key)
        self.assertEqual(digest, checksum(self.encrypted))
        self.target.mkdir()
        marker = self.target / 'preserve.txt'
        marker.write_text('existing user work')
        with self.assertRaises(FileExistsError):
            restore_sealed(self.encrypted, self.target, self.key)
        self.assertEqual(marker.read_text(), 'existing user work')

    def archive(self, entries):
        compressed = io.BytesIO()
        with tarfile.open(fileobj=compressed, mode='w:gz') as archive:
            for name, kind in entries:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = 1 if kind == tarfile.REGTYPE else 0
                info.linkname = 'ain.sqlite3' if kind == tarfile.SYMTYPE else ''
                archive.addfile(info, io.BytesIO(b'x') if info.size else None)
        encryptor = Cobblestone128Encryptor(self.key, context=CONTEXT)
        self.encrypted.write_bytes(MAGIC + encryptor.update(compressed.getvalue()) + encryptor.finalize())

    def test_authenticated_archive_still_rejects_traversal_links_and_duplicate_entries(self):
        for entries in [[('../outside', tarfile.REGTYPE)], [('ain.sqlite3', tarfile.SYMTYPE)],
                        [('ain.sqlite3', tarfile.REGTYPE), ('ain.sqlite3', tarfile.REGTYPE)]]:
            self.archive(entries)
            with self.assertRaises(ValueError):
                restore_sealed(self.encrypted, self.target, self.key)
            self.assertFalse(self.target.exists())
        self.assertFalse((self.root / 'outside').exists())

    def test_authenticated_archive_requires_valid_snapshot_manifest(self):
        self.archive([('ain.sqlite3', tarfile.REGTYPE)])
        with self.assertRaises((OSError, ValueError)):
            restore_sealed(self.encrypted, self.target, self.key)
        self.assertFalse(self.target.exists())

    def test_corrupt_snapshot_is_rejected_before_encrypted_output(self):
        (self.snapshot / 'ain.sqlite3').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            seal(self.snapshot, self.encrypted, self.key)
        self.assertFalse(self.encrypted.exists())

    def test_key_storage_inside_checkout_is_rejected(self):
        with self.assertRaises(ValueError):
            key_path(ROOT / '.local/not-a-key.dpapi')

    def test_encrypted_drill_receipt_is_sanitized_and_never_implies_independent_recovery(self):
        self.assertFalse(encrypted_drill_status(self.state)['recorded'])
        record = {'format': 'ain-encrypted-drill-v1', 'ciphertext_authenticated': True,
                  'restored_database_verified': True, 'flight_records': 1,
                  'checked_at': '2026-11-20T00:00:00+00:00', 'encryption': 'Cobblestone-128',
                  'key_provider': 'Windows DPAPI CurrentUser', 'independent_recovery_qualified': False,
                  'private_key_path': 'DO-NOT-EXPOSE'}
        file = self.state / 'encrypted-recovery-drill.json'
        file.write_text(json.dumps(record))
        result = encrypted_drill_status(self.state)
        self.assertTrue(result['recorded'])
        self.assertFalse(result['production_qualified'])
        self.assertNotIn('DO-NOT-EXPOSE', json.dumps(result))
        record['independent_recovery_qualified'] = True
        file.write_text(json.dumps(record))
        self.assertFalse(encrypted_drill_status(self.state)['recorded'])

    @unittest.skipUnless(os.name == 'nt', 'Windows CurrentUser DPAPI provider')
    def test_windows_key_roundtrip_and_no_overwrite(self):
        path = self.root / 'key.dpapi'
        result = create_key(path)
        self.assertTrue(result['key_created'])
        key = load_key(path)
        self.assertEqual(len(key), 16)
        self.assertNotEqual(path.read_bytes(), key)
        with self.assertRaises(FileExistsError):
            create_key(path)
        seal(self.snapshot, self.encrypted, key)
        self.assertTrue(restore_sealed(self.encrypted, self.target, load_key(path))['encrypted_source_authenticated'])
