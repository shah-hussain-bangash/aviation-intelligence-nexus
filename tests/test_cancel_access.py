from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from agents.jobs import JobQueue
from agents.runtime import Investigation
from agents.store import AgentStore
from services.api.auth import AuthStore
from services.api.main import create_app, initialize


class CancelAccessTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / 'synthetic.sqlite3'; initialize(self.database)
        self.auth = AuthStore(self.database)
        for name, role in [('admin','admin'), ('owner','researcher'), ('peer','researcher')]:
            self.auth.create_user(name, 'synthetic-cancellation-password', role)
        with closing(self.auth.connect()) as db:
            self.users = {r['username']: dict(r) for r in db.execute('SELECT id,username,role FROM auth_users')}
        self.store = AgentStore(self.database); self.queue = JobQueue(self.store)
        self.run = self.queue.enqueue(self.users['owner'], str(uuid4()), Investigation(objective='SYNTHETIC cancellation access check.'))

    def saved(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT result_json FROM agent_runs WHERE id=?', (self.run['run_id'],)).fetchone()[0]

    def change(self, sql, username='owner'):
        with closing(sqlite3.connect(self.database)) as db, db: db.execute(sql, (self.users[username]['id'],))

    def test_disabled_missing_or_downgraded_owner_cannot_change_saved_job(self):
        original = self.saved()
        for sql in ('UPDATE auth_users SET active=0 WHERE id=?', "UPDATE auth_users SET role='viewer' WHERE id=?", 'DELETE FROM auth_users WHERE id=?'):
            with self.subTest(sql=sql):
                self.change(sql)
                with self.assertRaises(PermissionError): self.queue.cancel(self.users['owner'], self.run['run_id'])
                self.assertEqual(self.saved(), original)
                if not sql.startswith('DELETE'): self.change("UPDATE auth_users SET active=1,role='researcher' WHERE id=?")

    def test_revoked_expired_empty_and_other_owner_session_are_rejected(self):
        original = self.saved(); owner = self.users['owner']
        token = self.auth.login('owner', 'synthetic-cancellation-password'); self.auth.logout(token)
        other = self.auth.login('peer', 'synthetic-cancellation-password')
        expired = self.auth.login('owner', 'synthetic-cancellation-password')
        self.change('UPDATE auth_sessions SET expires_at=0 WHERE user_id=?')
        for candidate in (token, expired, other, ''):
            with self.subTest(candidate_kind='revoked/expired/wrong-owner/empty'):
                with self.assertRaises(PermissionError): self.queue.cancel(owner, self.run['run_id'], session_token=candidate)
                self.assertEqual(self.saved(), original)

    def test_stale_admin_cannot_stop_other_owners_work(self):
        original = self.saved()
        self.change("UPDATE auth_users SET role='researcher' WHERE id=?", 'admin')
        with self.assertRaises(PermissionError): self.queue.cancel(self.users['admin'], self.run['run_id'])
        self.assertEqual(self.saved(), original)
        with self.assertRaises(KeyError): self.queue.cancel(self.users['peer'], self.run['run_id'])

    def test_valid_session_stops_queued_work_and_revoked_retry_is_denied(self):
        token = self.auth.login('owner', 'synthetic-cancellation-password')
        cancelled = self.queue.cancel(self.users['owner'], self.run['run_id'], session_token=token)
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertEqual(self.queue.cancel(self.users['owner'], self.run['run_id'], session_token=token), cancelled)
        original = self.saved(); self.auth.logout(token)
        with self.assertRaises(PermissionError): self.queue.cancel(self.users['owner'], self.run['run_id'], session_token=token)
        self.assertEqual(self.saved(), original)

    def test_current_admin_and_owner_can_request_cooperative_stop(self):
        self.queue.claim()
        token = self.auth.login('admin', 'synthetic-cancellation-password')
        result = self.queue.cancel(self.users['admin'], self.run['run_id'], session_token=token)
        self.assertEqual(result['state'], 'running'); self.assertEqual(result['cancel_requested_by'], 'admin')
        original = self.saved()
        self.change("UPDATE auth_users SET role='viewer' WHERE id=?")
        with self.assertRaises(PermissionError): self.queue.cancel(self.users['owner'], self.run['run_id'])
        self.assertEqual(self.saved(), original)

    def test_http_logout_after_authentication_before_write_returns_403(self):
        app = create_app(self.database); original_cancel = JobQueue.cancel
        original = self.saved(); observed = []
        def revoke_then_cancel(queue, user, run_id, session_token=None):
            observed.append(bool(session_token)); self.auth.logout(session_token)
            return original_cancel(queue, user, run_id, session_token=session_token)
        with TestClient(app) as client:
            response = client.post('/api/v1/auth/login', headers={'Origin':'http://localhost:8080'},
                json={'username':'owner','password':'synthetic-cancellation-password'})
            headers = {'Origin':'http://localhost:8080','X-CSRF-Token':response.json()['csrf_token']}
            with patch.object(JobQueue, 'cancel', new=revoke_then_cancel):
                response = client.post('/api/v1/research/agent-cancel', headers=headers, json={'run_id':self.run['run_id']})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(observed, [True]); self.assertEqual(self.saved(), original)
