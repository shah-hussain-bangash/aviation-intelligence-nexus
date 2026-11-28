from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from agents.jobs import JobQueue
from agents.runtime import Investigation
from agents.store import AgentStore
from services.api.auth import AuthStore
from services.api.main import create_app, initialize


class EnqueueAccessTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.database=Path(folder.name)/'synthetic.sqlite3';initialize(self.database)
        self.auth=AuthStore(self.database)
        for name,role in [('admin','admin'),('owner','researcher'),('peer','researcher')]:
            self.auth.create_user(name,'synthetic-enqueue-password',role)
        with closing(self.auth.connect()) as db:
            self.users={r['username']:dict(r) for r in db.execute('SELECT id,username,role FROM auth_users')}
        self.queue=JobQueue(AgentStore(self.database))
        self.request=Investigation(objective='SYNTHETIC queue submission access check.')

    def saved(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT id,owner_id,request_key,input_hash,result_json,updated_at FROM agent_runs ORDER BY id').fetchall()

    def change(self,statement):
        with closing(sqlite3.connect(self.database)) as db,db:db.execute(statement,(self.users['owner']['id'],))

    def login(self,name='owner'):return self.auth.login(name,'synthetic-enqueue-password')

    def submit(self,token,key=None):
        return self.queue.enqueue(self.users['owner'],key or str(uuid4()),self.request,session_token=token)

    def test_revoked_session_cannot_create_new_job(self):
        token=self.login();self.auth.logout(token)
        with self.assertRaises(PermissionError):self.submit(token)
        self.assertEqual(self.saved(),[])

    def test_revoked_replay_and_duplicate_alias_leave_saved_job_unchanged(self):
        token=self.login();key=str(uuid4());self.submit(token,key);before=self.saved();self.auth.logout(token)
        for candidate in (key,str(uuid4())):
            with self.assertRaises(PermissionError):self.submit(token,candidate)
            self.assertEqual(self.saved(),before)

    def test_expired_wrong_owner_and_empty_sessions_cannot_enqueue(self):
        expired=self.login();self.change('UPDATE auth_sessions SET expires_at=0 WHERE user_id=?')
        for token in (expired,self.login('peer'),''):
            with self.assertRaises(PermissionError):self.submit(token)
            self.assertEqual(self.saved(),[])

    def test_disabled_downgraded_and_missing_account_cannot_enqueue(self):
        token=self.login()
        for statement in ('UPDATE auth_users SET active=0 WHERE id=?',"UPDATE auth_users SET role='viewer' WHERE id=?",'DELETE FROM auth_users WHERE id=?'):
            self.change(statement)
            with self.assertRaises(PermissionError):self.submit(token)
            self.assertEqual(self.saved(),[])
            if not statement.startswith('DELETE'):self.change("UPDATE auth_users SET active=1,role='researcher' WHERE id=?")

    def test_valid_current_account_and_retry_behavior_are_preserved(self):
        token=self.login();self.change("UPDATE auth_users SET username='owner-renamed' WHERE id=?")
        key=str(uuid4());first=self.submit(token,key)
        self.assertEqual(first['actor'],'owner-renamed');self.assertEqual(first['state'],'queued')
        replay=self.submit(token,key);alias=self.submit(token)
        self.assertEqual(replay['run_id'],first['run_id']);self.assertTrue(replay['replayed'])
        self.assertEqual(alias['run_id'],first['run_id']);self.assertTrue(alias['replayed'])
        self.assertEqual(len(self.saved()),1)

    def test_http_revocation_between_authentication_and_queue_transaction(self):
        with patch.dict('os.environ',{'AIN_AGENT_JOBS':'1'}):app=create_app(self.database)
        worker=app.state.job_worker;original=JobQueue.enqueue
        for change in ('logout','disable','viewer'):
            self.change("UPDATE auth_users SET active=1,role='researcher' WHERE id=?")
            def revoke(queue,user,key,request,context=None,session_token=None):
                self.assertTrue(session_token)
                if change=='logout':self.auth.logout(session_token)
                elif change=='disable':self.change('UPDATE auth_users SET active=0 WHERE id=?')
                else:self.change("UPDATE auth_users SET role='viewer' WHERE id=?")
                return original(queue,user,key,request,context=context,session_token=session_token)
            with self.subTest(change=change),patch.object(worker,'start'),patch.object(worker,'stop',new=AsyncMock()),TestClient(app) as client:
                worker.task=SimpleNamespace(done=lambda:False)
                login=client.post('/api/v1/auth/login',headers={'Origin':'http://localhost:8080'},json={'username':'owner','password':'synthetic-enqueue-password'})
                headers={'Origin':'http://localhost:8080','X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':str(uuid4())}
                with patch.object(JobQueue,'enqueue',new=revoke):
                    response=client.post('/api/v1/research/agent-jobs',headers=headers,json=self.request.model_dump())
                self.assertEqual(response.status_code,403);self.assertEqual(self.saved(),[])

    def test_trusted_sessionless_fixture_remains_supported(self):
        user={'id':'synthetic-fixture','username':'SYNTHETIC fixture','role':'researcher'}
        result=self.queue.enqueue(user,str(uuid4()),self.request)
        self.assertEqual(result['state'],'queued');self.assertEqual(result['actor'],user['username'])
