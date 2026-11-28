from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from agents.evaluate_peer_review import seed
from agents.store import AgentStore
from services.api.auth import AuthStore
from services.api.main import create_app, initialize

NOTE = 'SYNTHETIC access regression only; no genuine human assessment.'


class ReviewCurrentAccessTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / 'synthetic.sqlite3'; initialize(self.database)
        self.auth = AuthStore(self.database)
        for name,role in [('admin','admin'),('owner','researcher'),('peer','researcher')]:
            self.auth.create_user(name,'synthetic-review-password',role)
        with closing(self.auth.connect()) as db:
            self.users = {r['username']:dict(r) for r in db.execute('SELECT id,username,role FROM auth_users')}
        self.store = AgentStore(self.database); self.run = seed(self.store,self.users['owner'],False)

    def saved(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT result_json FROM agent_runs WHERE id=?',(self.run['run_id'],)).fetchone()[0]

    def change(self,statement,name='owner'):
        with closing(sqlite3.connect(self.database)) as db,db:db.execute(statement,(self.users[name]['id'],))

    def login(self,name='owner'):return self.auth.login(name,'synthetic-review-password')

    def review(self,token,user=None):
        return self.store.review(user or self.users['owner'],self.run['run_id'],self.run['report_sha256'],'reviewed',NOTE,session_token=token)

    def test_logged_out_expired_empty_and_wrong_owner_sessions_leave_report_unchanged(self):
        before=self.saved();revoked=self.login();self.auth.logout(revoked)
        expired=self.login();self.change('UPDATE auth_sessions SET expires_at=0 WHERE user_id=?')
        other=self.login('peer')
        for token in (revoked,expired,'',other):
            with self.assertRaises(PermissionError):self.review(token)
            self.assertEqual(self.saved(),before)

    def test_disabled_downgraded_and_missing_accounts_leave_report_unchanged(self):
        before=self.saved();token=self.login()
        for statement in ('UPDATE auth_users SET active=0 WHERE id=?',"UPDATE auth_users SET role='viewer' WHERE id=?",'DELETE FROM auth_users WHERE id=?'):
            with self.subTest(statement=statement):
                self.change(statement)
                with self.assertRaises(PermissionError):self.review(token)
                self.assertEqual(self.saved(),before)
                if not statement.startswith('DELETE'):self.change("UPDATE auth_users SET active=1,role='researcher' WHERE id=?")

    def test_stale_admin_cannot_review_another_owners_private_report(self):
        token=self.login('admin');before=self.saved()
        self.change("UPDATE auth_users SET role='researcher' WHERE id=?",'admin')
        with self.assertRaises(PermissionError):self.review(token,self.users['admin'])
        self.assertEqual(self.saved(),before)

    def test_valid_owner_session_records_current_account_name(self):
        token=self.login();self.change("UPDATE auth_users SET username='owner-renamed' WHERE id=?")
        result=self.review(token)
        self.assertEqual(result['state'],'reviewed');self.assertEqual(len(result['reviews']),1)
        self.assertEqual(result['reviews'][0]['actor'],'owner-renamed')
        self.assertFalse(result['operational_approval']);self.assertFalse(result['request'].get('require_peer_review',False))

    def test_valid_admin_session_can_review_private_report(self):
        result=self.review(self.login('admin'),self.users['admin'])
        self.assertEqual(result['state'],'reviewed');self.assertEqual(result['reviews'][0]['actor'],'admin')

    def test_http_access_changes_after_authentication_are_rejected_before_save(self):
        app=create_app(self.database);original=AgentStore.review;before=self.saved()
        for change in ('logout','disable','viewer'):
            self.change("UPDATE auth_users SET active=1,role='researcher' WHERE id=?")
            def revoke(store,user,run_id,report_hash,decision,note,session_token=None):
                self.assertTrue(session_token)
                if change=='logout':self.auth.logout(session_token)
                elif change=='disable':self.change('UPDATE auth_users SET active=0 WHERE id=?')
                else:self.change("UPDATE auth_users SET role='viewer' WHERE id=?")
                return original(store,user,run_id,report_hash,decision,note,session_token=session_token)
            with self.subTest(change=change),TestClient(app) as client:
                login=client.post('/api/v1/auth/login',headers={'Origin':'http://localhost:8080'},
                    json={'username':'owner','password':'synthetic-review-password'})
                with patch.object(AgentStore,'review',new=revoke):
                    response=client.post('/api/v1/research/agent-review',headers={'Origin':'http://localhost:8080','X-CSRF-Token':login.json()['csrf_token']},
                        json={'run_id':self.run['run_id'],'report_sha256':self.run['report_sha256'],'decision':'reviewed','note':NOTE})
                self.assertEqual(response.status_code,403);self.assertEqual(self.saved(),before)

    def test_trusted_sessionless_fixture_calls_retain_legacy_behavior(self):
        fixture_user={'id':'synthetic-accountless-fixture','username':'SYNTHETIC fixture','role':'researcher'}
        run=seed(self.store,fixture_user,False)
        result=self.store.review(fixture_user,run['run_id'],run['report_sha256'],'needs_changes',NOTE)
        self.assertEqual(result['state'],'needs_changes');self.assertFalse(result['operational_approval'])
