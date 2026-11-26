from contextlib import closing
import io
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from infra import case_recovery as paired,recovery,sealed_case_recovery as sealed
from infra.sealed_recovery import create_key,load_key
from infra.recovery_state import RESTORE_MARKER,RestoreIncompleteError
from services.api.case_workspace import create_case_app
from services.api.research_cases import ResearchCaseService
from services.api.auth import AuthStore
from tests.test_case_recovery import seed_workspace


class SealedCaseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.state=self.root/'state';self.fixture=seed_workspace(self.state);self.bundle=self.root/'bundle'
        self.pin=paired.backup(self.state,self.bundle,offline_acknowledged=True)['manifest_sha256']
        self.key=os.urandom(16);self.encrypted=self.root/'case-backup.aincase';self.target=self.root/'restored'

    def seal(self):return sealed.seal(self.bundle,self.encrypted,self.key,self.pin,offline_acknowledged=True)
    def restore(self,key=None,pin=None):return sealed.restore_sealed(self.encrypted,self.target,self.key if key is None else key,self.pin if pin is None else pin,offline_acknowledged=True)

    def test_roundtrip_preserves_closed_case_all_attachments_and_original_sessions(self):
        originals={name:recovery.checksum(self.state/name) for name in ('ain.sqlite3',paired.CASE_FILE)}
        saved=self.seal();receipt=self.restore()
        self.assertTrue(receipt['encrypted_source_authenticated']);self.assertFalse(receipt['restored_workspace_encrypted'])
        self.assertEqual(saved['encryption'],'AES-128-GCM');self.assertEqual(saved['ciphertext_sha256'],receipt['ciphertext_sha256'])
        self.assertNotIn(b'SQLite format 3',self.encrypted.read_bytes())
        restored=ResearchCaseService(self.target/'ain.sqlite3',self.target/paired.CASE_FILE)
        self.assertEqual(restored.get(self.fixture['user'],self.fixture['case_id']),self.fixture['record'])
        self.assertEqual(receipt['cases']['row_counts'],{'cases':1,'case_events':6,'case_evidence':1,'case_agents':1,'case_gates':1})
        self.assertIsNotNone(AuthStore(self.state/'ain.sqlite3').session(self.fixture['token']))
        self.assertIsNone(AuthStore(self.target/'ain.sqlite3').session(self.fixture['token']))
        self.assertEqual(originals,{name:recovery.checksum(self.state/name) for name in originals})
        self.assertEqual(list(self.root.glob('.ain-case-unseal-*')),[])

    def test_wrong_key_and_changed_truncated_appended_ciphertext_fail_before_parsing(self):
        self.seal();original=self.encrypted.read_bytes()
        for value,key in [(original,os.urandom(16)),(original[:-1],self.key),(original+b'append',self.key),
                (original[:60]+bytes([original[60]^1])+original[61:],self.key)]:
            self.encrypted.write_bytes(value)
            with patch.object(sealed.tarfile,'open',side_effect=AssertionError('No unauthenticated archive parsing')),self.assertRaises(paired.CaseRecoveryError):self.restore(key)
            self.assertFalse(self.target.exists());self.assertEqual(list(self.root.glob('.ain-case-unseal-*')),[])

    def test_header_nonce_and_tag_changes_are_rejected(self):
        self.seal();original=self.encrypted.read_bytes()
        for index in (0,len(sealed.MAGIC),len(original)-1):
            changed=bytearray(original);changed[index]^=1;self.encrypted.write_bytes(changed)
            with self.assertRaises(paired.CaseRecoveryError):self.restore()
            self.assertFalse(self.target.exists())

    def archive(self,entries):
        compressed=io.BytesIO()
        with tarfile.open(fileobj=compressed,mode='w:gz') as archive:
            for name,kind in entries:
                info=tarfile.TarInfo(name);info.type=kind;info.size=1 if kind==tarfile.REGTYPE else 0
                info.linkname='application/ain.sqlite3' if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE) else ''
                archive.addfile(info,io.BytesIO(b'x') if info.size else None)
        header=sealed.MAGIC+os.urandom(12);encryptor=Cipher(algorithms.AES(self.key),modes.GCM(header[-12:])).encryptor();encryptor.authenticate_additional_data(header)
        self.encrypted.write_bytes(header+encryptor.update(compressed.getvalue())+encryptor.finalize()+encryptor.tag)

    def test_authenticated_archive_rejects_traversal_links_duplicates_and_unknown_files(self):
        for entries in [[('../outside',tarfile.REGTYPE)],[(paired.CASE_FILE,tarfile.SYMTYPE)],[(paired.CASE_FILE,tarfile.LNKTYPE)],
                [(paired.CASE_FILE,tarfile.REGTYPE),(paired.CASE_FILE,tarfile.REGTYPE)],[('unexpected.json',tarfile.REGTYPE)]]:
            self.archive(entries)
            with self.assertRaises(paired.CaseRecoveryError):self.restore()
            self.assertFalse(self.target.exists());self.assertFalse((self.root/'outside').exists())

    def test_authentication_does_not_replace_manifest_pin_or_case_checks(self):
        self.seal()
        with self.assertRaises(paired.CaseRecoveryError):self.restore(pin='0'*64)
        self.assertFalse(self.target.exists())
        self.archive([(paired.CASE_FILE,tarfile.REGTYPE)])
        with self.assertRaises((ValueError,OSError)):self.restore()
        self.assertFalse(self.target.exists())

    def test_existing_output_and_restore_directory_are_preserved(self):
        self.seal();original=recovery.checksum(self.encrypted)
        with self.assertRaises(paired.CaseRecoveryError):self.seal()
        self.assertEqual(recovery.checksum(self.encrypted),original)
        self.target.mkdir();(self.target/'keep.txt').write_text('preserve existing work')
        with self.assertRaises(paired.CaseRecoveryError):self.restore()
        self.assertEqual((self.target/'keep.txt').read_text(),'preserve existing work')

    def test_offline_ack_key_length_pin_and_size_bounds_precede_output(self):
        for key,pin,ack in [(self.key,self.pin,False),(b'short',self.pin,True),(self.key,'0'*64,True)]:
            with self.assertRaises(paired.CaseRecoveryError):sealed.seal(self.bundle,self.encrypted,key,pin,offline_acknowledged=ack)
            self.assertFalse(self.encrypted.exists())
        with patch.object(sealed,'MAX_BYTES',1),self.assertRaises(paired.CaseRecoveryError):self.seal()
        self.assertFalse(self.encrypted.exists())

    def test_fresh_nonces_and_failed_publication_cleanup_do_not_replace_output(self):
        self.seal();second=self.root/'second.aincase';sealed.seal(self.bundle,second,self.key,self.pin,offline_acknowledged=True)
        self.assertNotEqual(self.encrypted.read_bytes()[len(sealed.MAGIC):len(sealed.MAGIC)+12],second.read_bytes()[len(sealed.MAGIC):len(sealed.MAGIC)+12])
        failed=self.root/'failed.aincase'
        with patch.object(sealed.os,'link',side_effect=OSError('Synthetic publication failure')),self.assertRaises(OSError):sealed.seal(self.bundle,failed,self.key,self.pin,offline_acknowledged=True)
        self.assertFalse(failed.exists());self.assertEqual(list(self.root.glob('.*.partial-*')),[])

    def test_expanded_archive_bounds_are_checked_after_authentication(self):
        info=tarfile.TarInfo(paired.CASE_FILE);info.size=sealed.MAX_BYTES+1
        compressed=gzip.compress(info.tobuf(format=tarfile.GNU_FORMAT)+b'\0'*1024)
        header=sealed.MAGIC+os.urandom(12);encryptor=Cipher(algorithms.AES(self.key),modes.GCM(header[-12:])).encryptor();encryptor.authenticate_additional_data(header)
        self.encrypted.write_bytes(header+encryptor.update(compressed)+encryptor.finalize()+encryptor.tag)
        with self.assertRaisesRegex(paired.CaseRecoveryError,'archive_exceeds_local_bound'):self.restore()
        self.assertFalse(self.target.exists())

    def test_encrypted_receipt_failure_reinstates_startup_interlock(self):
        self.seal();original=paired.write_new
        def fail(path,value):
            if path.name=='case-encrypted-restore.json':raise OSError('Synthetic receipt write failure')
            return original(path,value)
        with patch.object(paired,'write_new',side_effect=fail),self.assertRaises(OSError):self.restore()
        self.assertTrue((self.target/RESTORE_MARKER).exists())
        with patch.dict(os.environ,{'AIN_ENV':'test','AIN_STATE_ROOT':str(self.target),'AIN_DB_PATH':str(self.target/'ain.sqlite3')},clear=True),self.assertRaises(RestoreIncompleteError):create_case_app()

    def test_cli_errors_do_not_print_key_paths_or_contents(self):
        result=subprocess.run([sys.executable,'-m','infra.sealed_case_recovery','restore','--source',str(self.encrypted),'--destination',str(self.target),'--key-file',str(self.root/'PRIVATE-KEY.dpapi'),'--manifest-sha256',self.pin],cwd=recovery.ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,2);self.assertNotIn(str(self.root),result.stdout+result.stderr);self.assertNotIn('PRIVATE-KEY',result.stdout+result.stderr)

    @unittest.skipUnless(os.name=='nt','Windows CurrentUser DPAPI provider')
    def test_windows_protected_dedicated_key_and_actual_cli_roundtrip(self):
        key=self.root/'dedicated-key.dpapi';create_key(key);self.assertEqual(len(load_key(key)),16)
        (recovery.ROOT/'.local').mkdir(exist_ok=True)
        folder=tempfile.TemporaryDirectory(dir=recovery.ROOT/'.local');self.addCleanup(folder.cleanup);target=Path(folder.name)
        command=[sys.executable,'-m','infra.sealed_case_recovery'];env={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'}
        common=['--key-file',str(key),'--manifest-sha256',self.pin,'--offline-acknowledged']
        encrypted=target/'bundle.aincase'
        for action,source,destination in [('seal',self.bundle,encrypted),('restore',encrypted,target/'restored')]:
            result=subprocess.run(command+[action,'--source',str(source),'--destination',str(destination),*common],cwd=recovery.ROOT,env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertNotIn(str(key),result.stdout)
        self.assertTrue(json.loads(result.stdout)['encrypted_source_authenticated'])
