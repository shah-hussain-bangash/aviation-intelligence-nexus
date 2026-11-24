from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from infra.recovery import backup, restore
from infra.recovery_state import RESTORE_MARKER, RestoreIncompleteError, require_complete_restore
from infra.status import restore_status
from services.api.main import create_app, initialize
from services.api.auth import AuthStore
from services.api.security_audit import append_event, latest_events


class AuditedRestoreTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name)
        self.state=self.root/'source';self.state.mkdir();self.db=self.state/'ain.sqlite3';initialize(self.db)
        self.auth=AuthStore(self.db);self.password='synthetic-restore-password-123'
        self.auth.create_user('synthetic-admin',self.password,'admin');self.token=self.auth.login('synthetic-admin',self.password)
        self.snapshot=self.root/'snapshot';self.manifest=backup(self.state,self.snapshot)

    def tearDown(self):self.folder.cleanup()

    def rows(self,directory,table):
        with closing(sqlite3.connect(directory/'ain.sqlite3')) as db:return db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()

    def assert_blocked(self,directory):
        self.assertTrue((directory/RESTORE_MARKER).exists())
        self.assertFalse(restore_status(directory)['recorded'])
        with self.assertRaisesRegex(RestoreIncompleteError,'^restore_incomplete$'):
            with TestClient(create_app(directory/'ain.sqlite3')):self.fail('incomplete restore must not start')

    def test_success_links_single_aggregate_event_and_preserves_historical_events(self):
        before=self.rows(self.state,'security_audit');target=self.root/'restored'
        receipt=restore(self.snapshot,target);events=self.rows(target,'security_audit')
        self.assertEqual(events[:-1],before);self.assertEqual(len(events),len(before)+1)
        event=events[-1];self.assertEqual(event[1],receipt['session_revocation_event_id'])
        self.assertEqual(event[3:],('sign_out','success',None,None,None))
        self.assertTrue(receipt['session_revocation_audited']);self.assertEqual(receipt['revoked_session_rows'],1)
        self.assertEqual(receipt['session_revocation_scope'],'all_restored_sessions')
        self.assertEqual(receipt['expected_row_changes'],{'auth_sessions':-1,'security_audit':1})
        self.assertEqual(self.rows(target,'auth_sessions'),[]);self.assertIsNotNone(self.auth.session(self.token))
        self.assertEqual(self.rows(self.state,'security_audit'),before)
        self.assertFalse((target/RESTORE_MARKER).exists());self.assertTrue(restore_status(target)['recorded'])
        self.assertNotIn(self.password,json.dumps(receipt));self.assertNotIn(self.token,json.dumps(receipt))

    def test_audit_write_failure_rolls_back_revoke_and_never_issues_receipt(self):
        target=self.root/'failed'
        with patch('infra.recovery.append_event',side_effect=sqlite3.OperationalError('PRIVATE-DETAIL')),patch('infra.recovery.AgentStore.recover') as recover:
            with self.assertRaises(sqlite3.Error):restore(self.snapshot,target)
            recover.assert_not_called()
        self.assertEqual(self.rows(target,'auth_sessions'),self.rows(self.snapshot,'auth_sessions'))
        self.assertEqual(self.rows(target,'security_audit'),self.rows(self.snapshot,'security_audit'))
        self.assertFalse((target/'recovery-receipt.json').exists());self.assert_blocked(target)
        self.assertIsNotNone(self.auth.session(self.token))

    def test_unbound_event_result_cannot_commit_revoke(self):
        def wrong_binding(db,*args,**kwargs):
            append_event(db,*args,**kwargs)
            return str(uuid4())
        for index,action in enumerate((lambda *a,**k:None,lambda *a,**k:str(uuid4()),wrong_binding)):
            with self.subTest(index=index):
                target=self.root/('unbound-'+str(index))
                with patch('infra.recovery.append_event',side_effect=action):
                    with self.assertRaisesRegex(ValueError,'audit event'):restore(self.snapshot,target)
                self.assertEqual(self.rows(target,'auth_sessions'),self.rows(self.snapshot,'auth_sessions'))
                self.assertEqual(self.rows(target,'security_audit'),self.rows(self.snapshot,'security_audit'))
                self.assert_blocked(target)

    def test_failure_after_atomic_commit_retains_event_and_blocks_partial_target(self):
        target=self.root/'late-failure'
        with patch('infra.recovery.AgentStore.recover',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):restore(self.snapshot,target)
        self.assertEqual(self.rows(target,'auth_sessions'),[])
        self.assertEqual(len(self.rows(target,'security_audit')),len(self.rows(self.snapshot,'security_audit'))+1)
        self.assertFalse((target/'recovery-receipt.json').exists());self.assert_blocked(target)
        with self.assertRaises(RestoreIncompleteError):backup(target,self.root/'must-not-exist')
        self.assertFalse((self.root/'must-not-exist').exists())

    def test_marker_removal_failure_cannot_publish_success_through_status_or_startup(self):
        target=self.root/'not-finalized';unlink=Path.unlink
        def fail_marker(path,*args,**kwargs):
            if path.name==RESTORE_MARKER:raise OSError('synthetic finalization failure')
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_marker):
            with self.assertRaises(OSError):restore(self.snapshot,target)
        self.assertTrue((target/'recovery-receipt.json').exists())
        self.assert_blocked(target)

    def test_zero_session_restore_records_idempotent_sign_out_with_zero_count(self):
        self.auth.logout(self.token);empty=self.root/'empty-snapshot';backup(self.state,empty)
        target=self.root/'empty-restored';receipt=restore(empty,target)
        self.assertEqual(receipt['revoked_session_rows'],0)
        self.assertEqual(receipt['expected_row_changes'],{'auth_sessions':0,'security_audit':1})
        self.assertEqual(latest_events(target/'ain.sqlite3')['events'][0]['event_id'],receipt['session_revocation_event_id'])

    def test_marker_presence_blocks_startup_before_any_database_connection(self):
        (self.state/RESTORE_MARKER).write_text('PRIVATE-UNPARSED-CONTENT',encoding='utf-8')
        with patch('services.api.main.connect') as connect:
            with self.assertRaisesRegex(RestoreIncompleteError,'^restore_incomplete$'):initialize(self.db)
            connect.assert_not_called()
        with patch('infra.recovery_state.Path.lstat',side_effect=PermissionError('PRIVATE-PATH')):
            with self.assertRaisesRegex(RestoreIncompleteError,'^restore_state_unavailable$'):require_complete_restore(self.db)

    def test_incomplete_snapshot_marker_is_refused_before_creating_restore_target(self):
        (self.snapshot/RESTORE_MARKER).write_text('{}',encoding='utf-8');target=self.root/'must-not-exist'
        with self.assertRaises(RestoreIncompleteError):restore(self.snapshot,target)
        self.assertFalse(target.exists())
