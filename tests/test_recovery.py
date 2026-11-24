from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from infra.recovery import backup,restore,verify,private_target,database_facts
from infra.status import restore_status
from services.api.main import initialize
from services.api.auth import AuthStore
from agents.store import AgentStore
from services.api.main import create_app
from fastapi.testclient import TestClient


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name);self.state=self.root/'state';self.state.mkdir()
        initialize(self.state/'ain.sqlite3')
        self.auth=AuthStore(self.state/'ain.sqlite3');self.auth.create_user('recovery-admin','temporary-recovery-fixture-123','admin')
        self.auth.login('recovery-admin','temporary-recovery-fixture-123')
        with closing(sqlite3.connect(self.state/'ain.sqlite3')) as db,db:
            db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic_test','1','2025-05-01','TEST','AAA','BBB')")
        model=self.state/'models/delay-v2';model.mkdir(parents=True)
        (model/'model.joblib').write_bytes(b'fixture artifact is never deserialized')
        (model/'report.json').write_text(json.dumps({'artifact_sha256':hashlib.sha256((model/'model.joblib').read_bytes()).hexdigest()}))
        knowledge=self.state/'knowledge';knowledge.mkdir();payload={'version':1,'fixture':True}
        (knowledge/'index.json').write_text(json.dumps({'payload':payload,'sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()}))
        self.backup=self.root/'backup'

    def tearDown(self):self.folder.cleanup()

    def test_online_backup_captures_committed_state_and_preserves_source(self):
        with closing(sqlite3.connect(self.state/'ain.sqlite3')) as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic_test','2','2025-05-02','TEST','AAA','BBB')")
            manifest=backup(self.state,self.backup)
            self.assertEqual(manifest['database']['row_counts']['flights'],1)
            writer.rollback()
        self.assertEqual(database_facts(self.state/'ain.sqlite3')['row_counts']['auth_sessions'],1)

    def test_restore_verifies_artifacts_accounts_and_revokes_only_restored_sessions(self):
        backup(self.state,self.backup);receipt=restore(self.backup,self.root/'restored')
        self.assertTrue(receipt['checksums_verified']);self.assertEqual(receipt['flight_records'],1)
        self.assertTrue(receipt['active_model_restored']);self.assertTrue(receipt['knowledge_index_restored'])
        restored=AuthStore(self.root/'restored/ain.sqlite3')
        self.assertIsNotNone(restored.login('recovery-admin','temporary-recovery-fixture-123'))
        self.assertEqual(database_facts(self.state/'ain.sqlite3')['row_counts']['auth_sessions'],1)
        self.assertTrue(restore_status(self.root/'restored')['recorded'])

    def test_restore_never_overwrites_existing_target(self):
        backup(self.state,self.backup);target=self.root/'existing';target.mkdir();(target/'keep.txt').write_text('keep')
        with self.assertRaises(FileExistsError):restore(self.backup,target)
        self.assertEqual((target/'keep.txt').read_text(),'keep')

    def test_security_events_survive_snapshot_restore_and_are_in_inventory(self):
        from services.api.security_audit import latest_events
        before=latest_events(self.state/'ain.sqlite3')['events']
        manifest=backup(self.state,self.backup)
        self.assertEqual(manifest['database']['row_counts']['security_audit'],len(before))
        receipt=restore(self.backup,self.root/'audit-restored')
        events=latest_events(self.root/'audit-restored/ain.sqlite3')['events']
        self.assertEqual(events[1:],before)
        self.assertEqual(events[0]['event_id'],receipt['session_revocation_event_id'])
        self.assertEqual(events[0]['action'],'sign_out')

    def test_corrupt_backup_is_rejected_before_target_creation(self):
        backup(self.state,self.backup);(self.backup/'models/delay-v2/model.joblib').write_bytes(b'corrupt')
        target=self.root/'restored'
        with self.assertRaises(ValueError):restore(self.backup,target)
        self.assertFalse(target.exists())

    def test_manifest_path_traversal_and_future_schema_are_rejected(self):
        backup(self.state,self.backup);path=self.backup/'manifest.json';manifest=json.loads(path.read_text())
        manifest['files'][0]['path']='../outside.sqlite3';path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):verify(self.backup)
        with closing(sqlite3.connect(self.state/'ain.sqlite3')) as db,db:db.execute('INSERT INTO schema_migrations(version) VALUES(9999)')
        with self.assertRaises(ValueError):database_facts(self.state/'ain.sqlite3')

    def test_gapped_history_cannot_qualify_as_a_valid_backup(self):
        with closing(sqlite3.connect(self.state/'ain.sqlite3')) as db,db:
            db.execute('DELETE FROM schema_migrations WHERE version=4')
        with self.assertRaisesRegex(ValueError,'migration history'):
            database_facts(self.state/'ain.sqlite3')

    def test_restore_marks_inflight_agent_interrupted_without_replaying_tools(self):
        store=AgentStore(self.state/'ain.sqlite3');user={'id':'fixture','username':'fixture','role':'admin'}
        run=store.begin(user,'fixture-key',{'objective':'Fixture research request','month':'2025-05','include_simulation':False})
        backup(self.state,self.backup);restore(self.backup,self.root/'restored')
        saved=AgentStore(self.root/'restored/ain.sqlite3').recent(user)[0]
        self.assertEqual(saved['run_id'],run['run_id']);self.assertEqual(saved['state'],'interrupted')

    def test_missing_or_unverified_receipt_is_not_reported_as_success(self):
        self.assertFalse(restore_status(self.state)['recorded'])
        (self.state/'recovery-receipt.json').write_text(json.dumps({'format':'ain-restore-receipt-v1','checksums_verified':True}))
        self.assertFalse(restore_status(self.state)['recorded'])
        with self.assertRaises(ValueError):private_target(self.root/'outside-project')

    def test_missing_model_pair_never_qualifies_as_a_valid_backup(self):
        (self.state/'models/delay-v2/report.json').unlink()
        with self.assertRaises(ValueError):backup(self.state,self.backup)

    def test_restored_instance_exposes_only_sanitized_authenticated_receipt(self):
        backup(self.state,self.backup);target=self.root/'restored';restore(self.backup,target)
        with patch('services.api.main.ollama.models',return_value={}),TestClient(create_app(target/'ain.sqlite3',research_model_directory=target/'models/delay-v2')) as client:
            self.assertEqual(client.get('/api/v1/research/platform-status').status_code,401)
            login=client.post('/api/v1/auth/login',json={'username':'recovery-admin','password':'temporary-recovery-fixture-123'},headers={'Origin':'http://127.0.0.1:8080'})
            self.assertEqual(login.status_code,200)
            result=client.get('/api/v1/research/platform-status').json()
            self.assertTrue(result['recovery']['recorded']);self.assertEqual(result['recovery']['flight_records'],1)
            self.assertFalse(result['production_ready']);self.assertNotIn(str(self.root),json.dumps(result))
