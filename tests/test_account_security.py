from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.account_security import account_sessions,SessionInvalid
from services.api.auth import AuthStore,COOKIE
from services.api.main import initialize,create_app

PASSWORD='temporary-security-fixture-123'
ORIGIN={'Origin':'http://127.0.0.1:8080'}


class AccountSecurityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'state.sqlite3';initialize(self.db);self.auth=AuthStore(self.db)
        self.auth.create_user('security-admin',PASSWORD,'admin');self.auth.create_user('security-viewer',PASSWORD,'viewer')
        self.current=self.auth.login('security-admin',PASSWORD);self.other=self.auth.login('security-admin',PASSWORD);self.foreign=self.auth.login('security-viewer',PASSWORD)

    def tearDown(self):self.folder.cleanup()

    def test_snapshot_is_private_read_only_and_excludes_expired_and_foreign_sessions(self):
        expired=self.auth.login('security-admin',PASSWORD)
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute('UPDATE auth_sessions SET expires_at=? WHERE token_hash=?',(time.time()-1,hashlib.sha256(expired.encode()).hexdigest()))
            before=db.execute('SELECT * FROM auth_sessions ORDER BY token_hash').fetchall()
        result=account_sessions(self.db,self.current);self.assertEqual((result['active_sessions'],result['other_active_sessions']),(2,1))
        self.assertEqual(set(result),{'active_sessions','other_active_sessions','checked_at','current_expires_at','scope','production_ready'})
        self.assertNotIn(self.current,str(result));self.assertNotIn('security-admin',str(result))
        with closing(sqlite3.connect(self.db)) as db:self.assertEqual(before,db.execute('SELECT * FROM auth_sessions ORDER BY token_hash').fetchall())

    def test_revocation_preserves_current_foreign_password_and_expiry(self):
        with closing(sqlite3.connect(self.db)) as db:before=db.execute('SELECT * FROM auth_users ORDER BY id').fetchall()
        expiry=account_sessions(self.db,self.current)['current_expires_at'];result=account_sessions(self.db,self.current,True)
        self.assertEqual(result['revoked_other_sessions'],1);self.assertTrue(result['current_session_preserved']);self.assertEqual(result['current_expires_at'],expiry)
        self.assertIsNotNone(self.auth.session(self.current));self.assertIsNone(self.auth.session(self.other));self.assertIsNotNone(self.auth.session(self.foreign))
        with closing(sqlite3.connect(self.db)) as db:self.assertEqual(before,db.execute('SELECT * FROM auth_users ORDER BY id').fetchall())

    def test_concurrent_retry_does_not_revoke_current_or_double_count(self):
        self.auth.login('security-admin',PASSWORD)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:account_sessions(self.db,self.current,True),range(2)))
        self.assertEqual(sorted(r['revoked_other_sessions'] for r in results),[0,2]);self.assertIsNotNone(self.auth.session(self.current))

    def test_revoked_disabled_or_expired_current_session_cannot_delete_others(self):
        self.auth.logout(self.current)
        with self.assertRaises(SessionInvalid):account_sessions(self.db,self.current,True)
        self.assertIsNotNone(self.auth.session(self.other))
        self.auth.set_access('security-viewer',disable=True)
        with self.assertRaises(SessionInvalid):account_sessions(self.db,self.foreign,True)
        with closing(sqlite3.connect(self.db)) as db,db:db.execute('UPDATE auth_sessions SET expires_at=? WHERE token_hash=?',(time.time()-1,hashlib.sha256(self.other.encode()).hexdigest()))
        with self.assertRaises(SessionInvalid):account_sessions(self.db,self.other,True)

    def test_missing_busy_and_deadline_failures_do_not_change_sessions(self):
        missing=Path(self.folder.name)/'missing.sqlite3'
        for write in (False,True):
            with self.assertRaises(sqlite3.Error):account_sessions(missing,self.current,write)
        self.assertFalse(missing.exists())
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):account_sessions(self.db,self.current,True)
            db.rollback()
        with patch('services.api.account_security.time.monotonic',side_effect=[0,4,4,4]):
            with self.assertRaises((TimeoutError,sqlite3.OperationalError)):account_sessions(self.db,self.current,True)
        self.assertIsNotNone(self.auth.session(self.other))

    def test_http_viewer_self_control_requires_origin_csrf_and_explicit_boolean(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            path='/api/v1/auth/revoke-other-sessions';self.assertEqual(client.get('/api/v1/auth/security').status_code,401)
            login=client.post('/api/v1/auth/login',json={'username':'security-viewer','password':PASSWORD},headers=ORIGIN)
            headers={**ORIGIN,'X-CSRF-Token':login.json()['csrf_token']}
            self.assertEqual(client.get('/api/v1/auth/security').json()['other_active_sessions'],1)
            self.assertEqual(client.post(path,json={'acknowledged':True}).status_code,403)
            self.assertEqual(client.post(path,json={'acknowledged':True},headers=ORIGIN).status_code,403)
            for body in [{},{'acknowledged':False},{'acknowledged':'true'},{'acknowledged':True,'user_id':'foreign'}]:self.assertEqual(client.post(path,json=body,headers=headers).status_code,422)
            response=client.post(path,json={'acknowledged':True},headers=headers);self.assertEqual(response.status_code,200);self.assertEqual(response.json()['revoked_other_sessions'],1)
            self.assertEqual(client.get('/api/v1/auth/session').status_code,200);self.assertIsNotNone(self.auth.session(self.current));self.assertIsNone(self.auth.session(self.foreign))

    def test_mid_request_revocation_and_storage_errors_return_no_private_diagnostics(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            login=client.post('/api/v1/auth/login',json={'username':'security-admin','password':PASSWORD},headers=ORIGIN)
            headers={**ORIGIN,'X-CSRF-Token':login.json()['csrf_token']}
            with patch('services.api.main.account_sessions',side_effect=SessionInvalid('private-token')):
                self.assertEqual(client.post('/api/v1/auth/revoke-other-sessions',json={'acknowledged':True},headers=headers).status_code,401)
            with patch('services.api.main.account_sessions',side_effect=sqlite3.OperationalError('private-db-path')):
                for method,path,kwargs in [('get','/api/v1/auth/security',{}),('post','/api/v1/auth/revoke-other-sessions',{'json':{'acknowledged':True},'headers':headers})]:
                    response=getattr(client,method)(path,**kwargs);self.assertEqual(response.status_code,503);self.assertNotIn('private-db',response.text)
