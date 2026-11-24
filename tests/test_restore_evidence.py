from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from infra.recovery import backup, restore, FILES as RECOVERY_FILES
from infra.recovery_state import RESTORE_MARKER
from infra.verify_restore_evidence import FILES, verify_evidence
from services.api.main import initialize
from services.api.auth import AuthStore
from services.api.security_audit import AUDIT_TRIGGER_SQL
from agents.store import AgentStore


class RestoreEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.root=Path(self.folder.name)
        self.password='synthetic-evidence-password-123'
        self.snapshot,self.restored=self.case(self.root)

    def tearDown(self):self.folder.cleanup()

    def case(self,root,active=False):
        root.mkdir(exist_ok=True);state=root/'source';state.mkdir();db=state/'ain.sqlite3';initialize(db)
        auth=AuthStore(db);auth.create_user('synthetic-admin',self.password,'admin');token=auth.login('synthetic-admin',self.password)
        if active:AgentStore(db).begin(auth.session(token),'synthetic-key',{'objective':'Synthetic research only','month':'2025-05','include_simulation':False})
        with closing(sqlite3.connect(db)) as connection,connection:
            connection.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic','1','2025-01-01','XX','AAA','BBB')")
        # Prepare a genuinely standalone, quiescent test fixture before taking its backup.
        with closing(sqlite3.connect(db)) as connection:connection.execute('PRAGMA journal_mode=DELETE')
        model=state/'models/delay-v2';model.mkdir(parents=True);blob=b'SYNTHETIC NONEXECUTABLE PLACEHOLDER'
        (model/'model.joblib').write_bytes(blob)
        (model/'report.json').write_text(json.dumps({'artifact_sha256':hashlib.sha256(blob).hexdigest()}),encoding='utf-8')
        knowledge=state/'knowledge';knowledge.mkdir();payload={'version':1,'synthetic':True}
        (knowledge/'index.json').write_text(json.dumps({'payload':payload,'sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}),encoding='utf-8')
        snapshot=root/'backup';restored=root/'restored';backup(state,snapshot);restore(snapshot,restored)
        return snapshot,restored

    def verify(self):return verify_evidence(self.snapshot,self.restored,offline_copy=True)

    def change(self,path,sql):
        with closing(sqlite3.connect(path)) as db,db:db.execute(sql)

    def test_complete_consistency_check_changes_no_bytes_or_directory_entries(self):
        self.assertEqual(FILES,RECOVERY_FILES)
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.verify();self.assertTrue(result['consistency_verified'],result)
        self.assertTrue(all(result['checks'].values()));self.assertEqual(result['flight_records'],1)
        self.assertFalse(result['receipt_authenticated']);self.assertFalse(result['backup_origin_authenticated'])
        self.assertFalse(result['historical_audit_authenticated']);self.assertFalse(result['production_ready'])
        after={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        for secret in (self.password,'synthetic-admin',str(self.root)):
            self.assertNotIn(secret,json.dumps(result))

    def test_acknowledgement_required_before_any_database_open(self):
        with patch('sqlite3.connect',side_effect=AssertionError('must not open')):
            result=verify_evidence(self.root/'missing',self.root/'missing2')
        self.assertEqual(result['errors'],['offline_copy_acknowledgement_required'])

    def test_receipt_edits_cannot_hide_binding_or_count_errors(self):
        path=self.restored/'recovery-receipt.json';original=json.loads(path.read_text(encoding='utf-8'))
        cases=[('snapshot_id',str(uuid4())),('session_revocation_event_id',str(uuid4())),('revoked_session_rows',True),
               ('revoked_session_rows',2),('flight_records',2),('session_revocation_scope','PRIVATE-SCOPE'),
               ('expected_row_changes',{'auth_sessions':-1,'security_audit':True}),('sessions_revoked',False)]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                changed={**original,key:value};path.write_text(json.dumps(changed),encoding='utf-8')
                report=self.verify();self.assertFalse(report['consistency_verified']);self.assertNotIn('PRIVATE-SCOPE',json.dumps(report))
        path.write_text(json.dumps(original),encoding='utf-8')

    def test_backup_bytes_and_restored_artifacts_are_both_checked(self):
        source=self.snapshot/'models/delay-v2/model.joblib';original=source.read_bytes();source.write_bytes(b'changed')
        self.assertEqual(self.verify()['errors'],['backup_file_mismatch']);source.write_bytes(original)
        target=self.restored/'models/delay-v2/model.joblib';target.write_bytes(b'changed')
        self.assertEqual(self.verify()['errors'],['restored_artifact_mismatch'])

    def test_known_backup_artifact_omitted_from_manifest_is_not_silently_ignored(self):
        path=self.snapshot/'manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
        manifest['files']=[entry for entry in manifest['files'] if entry['path']!='knowledge/index.json']
        path.write_text(json.dumps(manifest),encoding='utf-8')
        (self.restored/'knowledge/index.json').unlink()
        receipt_path=self.restored/'recovery-receipt.json';receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt['knowledge_index_restored']=False;receipt_path.write_text(json.dumps(receipt),encoding='utf-8')
        self.assertEqual(self.verify()['errors'],['backup_inventory_mismatch'])

    def test_same_count_row_edit_and_owner_edited_audit_history_are_rejected(self):
        db=self.restored/'ain.sqlite3'
        self.change(db,"UPDATE flights SET carrier='PRIVATE-CHANGED'")
        report=self.verify();self.assertEqual(report['errors'],['retained_rows_mismatch']);self.assertNotIn('PRIVATE-CHANGED',json.dumps(report))
        self.change(db,"UPDATE flights SET carrier='XX'")
        self.change(db,'DROP TRIGGER security_audit_no_update')
        self.change(db,"UPDATE security_audit SET outcome='denied' WHERE sequence=1")
        self.change(db,AUDIT_TRIGGER_SQL['security_audit_no_update'])
        self.assertEqual(self.verify()['errors'],['historical_audit_mismatch'])

    def test_markers_sidecars_and_redirects_are_refused_before_sqlite_connect(self):
        marker=self.restored/RESTORE_MARKER;marker.write_text('PRIVATE-MARKER')
        with patch('sqlite3.connect',side_effect=AssertionError('must not open')):
            report=self.verify();self.assertFalse(report['consistency_verified'])
        marker.unlink();sidecar=self.restored/'ain.sqlite3-wal';sidecar.write_bytes(b'')
        with patch('sqlite3.connect',side_effect=AssertionError('must not open')):
            self.assertEqual(self.verify()['errors'],['sqlite_sidecar_present'])
        sidecar.unlink()
        with patch('pathlib.Path.is_symlink',return_value=True):
            self.assertEqual(self.verify()['errors'],['unredirected_paths_required'])

    def test_legal_active_agent_recovery_is_outside_this_verifier_scope(self):
        snapshot,restored=self.case(self.root/'active',active=True)
        report=verify_evidence(snapshot,restored,offline_copy=True)
        self.assertFalse(report['consistency_verified'])
        self.assertEqual(report['errors'],['nonquiescent_agent_scope_not_supported'])

    def test_budget_and_duplicate_json_fail_without_echoing_content(self):
        with patch('infra.verify_restore_evidence.SECONDS',0):
            self.assertEqual(self.verify()['errors'],['verification_budget_exceeded'])
        path=self.restored/'recovery-receipt.json';text=path.read_text(encoding='utf-8')
        path.write_text('{"PRIVATE-DUP":1,"PRIVATE-DUP":2,'+text[1:],encoding='utf-8')
        result=self.verify();self.assertEqual(result['errors'],['duplicate_json_key']);self.assertNotIn('PRIVATE-DUP',json.dumps(result))

    def test_real_cli_exit_codes_report_consistency_without_claiming_authentication(self):
        command=[sys.executable,'-m','infra.verify_restore_evidence','--backup',str(self.snapshot),'--restored',str(self.restored)]
        failed=subprocess.run(command,capture_output=True,text=True,timeout=15)
        self.assertEqual(failed.returncode,2);self.assertFalse(json.loads(failed.stdout)['consistency_verified'])
        passed=subprocess.run(command+['--offline-copy'],capture_output=True,text=True,timeout=30)
        self.assertEqual(passed.returncode,0,passed.stdout+passed.stderr)
        report=json.loads(passed.stdout);self.assertTrue(report['consistency_verified']);self.assertFalse(report['receipt_authenticated'])

    def test_observed_input_change_and_oversized_inventory_cannot_pass(self):
        original=sqlite3.connect;calls=[0];receipt=self.restored/'recovery-receipt.json'
        def concurrent_writer(*args,**kwargs):
            calls[0]+=1
            if calls[0]==2:receipt.write_text(receipt.read_text(encoding='utf-8')+'\n',encoding='utf-8')
            return original(*args,**kwargs)
        with patch('sqlite3.connect',side_effect=concurrent_writer):
            self.assertEqual(self.verify()['errors'],['file_changed'])
        with patch('infra.verify_restore_evidence.MAX_BYTES',1),patch('sqlite3.connect',side_effect=AssertionError('must not open')):
            self.assertFalse(self.verify()['consistency_verified'])
