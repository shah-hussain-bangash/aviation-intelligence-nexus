import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.jobs import JobQueue, JobWorker, QueueFull
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore, Conflict
from infra.recovery import backup, restore
from services.api.main import create_app, initialize
from services.api.auth import AuthStore
from rag import ollama


class JobTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.db = self.root / 'ain.sqlite3'
        initialize(self.db)
        auth = AuthStore(self.db)
        for name, role in [('admin', 'admin'), ('analyst', 'researcher'), ('other', 'researcher'), ('reader', 'viewer')]:
            auth.create_user(name, 'isolated-job-fixture-123', role)
        with closing(sqlite3.connect(self.db)) as db:
            self.users = {name: {'id': identifier, 'username': name, 'role': role}
                          for identifier, name, role in db.execute('SELECT id,username,role FROM auth_users')}
        self.store = AgentStore(self.db)
        self.queue = JobQueue(self.store)

    def tearDown(self):
        self.folder.cleanup()

    def request(self, suffix='A'):
        return Investigation(objective='Fixture background investigation ' + suffix)

    def add(self, suffix='A', name='analyst', key=None):
        return self.queue.enqueue(self.users[name], key or str(uuid4()), self.request(suffix))

    def test_idempotency_conflict_and_active_duplicate_do_not_add_runs(self):
        key = str(uuid4())
        first = self.add(key=key)
        self.assertEqual(self.add(key=key)['run_id'], first['run_id'])
        with self.assertRaises(Conflict):
            self.add('changed', key=key)
        _, _, claimed = self.queue.claim()
        alias = str(uuid4())
        self.assertEqual(self.add(key=alias)['run_id'], first['run_id'])
        # A stale worker checkpoint must preserve retry keys added during execution.
        claimed.update(state='failed')
        self.store.checkpoint(claimed)
        self.assertEqual(self.add(key=alias)['run_id'], first['run_id'])
        with self.assertRaises(Conflict):
            self.add('changed', key=alias)
        self.assertEqual(len(self.store.recent(self.users['analyst'])), 1)

    def test_fifo_claim_is_atomic_across_competing_workers(self):
        first = self.add('A'); self.add('B')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: JobQueue(AgentStore(self.db)).claim(), range(2)))
        claimed = [r for r in results if r]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0][2]['run_id'], first['run_id'])
        self.assertIsNone(self.queue.claim())

    def test_waiting_limits_apply_per_owner_and_globally(self):
        self.add('A'); self.add('B')
        with self.assertRaises(QueueFull): self.add('C')
        self.add('C', 'other'); self.add('D', 'other'); self.add('E', 'admin')
        with self.assertRaises(QueueFull): self.add('F', 'admin')

    def test_cancellation_is_owner_checked_and_running_stop_is_requested_cooperatively(self):
        first = self.add()
        with self.assertRaises(KeyError): self.queue.cancel(self.users['other'], first['run_id'])
        self.assertEqual(self.queue.cancel(self.users['analyst'], first['run_id'])['state'], 'cancelled')
        self.assertEqual(self.queue.cancel(self.users['analyst'], first['run_id'])['state'], 'cancelled')
        second = self.add('B')
        self.queue.claim()
        stopped=self.queue.cancel(self.users['admin'],second['run_id'])
        self.assertEqual(stopped['state'],'running');self.assertTrue(stopped['cancel_requested_at'])
        self.assertEqual(self.queue.cancel(self.users['admin'],second['run_id'])['cancel_requested_at'],stopped['cancel_requested_at'])

    def test_restart_keeps_waiting_work_but_interrupts_claimed_work(self):
        first = self.add('A'); second = self.add('B')
        self.queue.claim()
        self.store.recover()
        self.assertEqual(self.queue.get(self.users['analyst'], first['run_id'])['state'], 'interrupted')
        self.assertEqual(self.queue.get(self.users['analyst'], second['run_id'])['state'], 'queued')
        self.assertEqual(self.queue.claim()[2]['run_id'], second['run_id'])

    def test_restoration_cancels_waiting_work_without_replaying_it(self):
        first = self.add()
        backup(self.root, self.root / 'snapshot')
        restore(self.root / 'snapshot', self.root / 'restored')
        restored = JobQueue(AgentStore(self.root / 'restored/ain.sqlite3'))
        self.assertEqual(restored.get(self.users['analyst'], first['run_id'])['state'], 'cancelled')
        self.assertIsNone(restored.claim())
        self.assertEqual(self.queue.get(self.users['analyst'], first['run_id'])['state'], 'queued')

    def test_permission_changes_are_rechecked_before_claim(self):
        first = self.add()
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE auth_users SET role='viewer' WHERE id=?", (self.users['analyst']['id'],))
        self.assertIsNone(self.queue.claim())
        self.assertEqual(self.queue.get(self.users['admin'], first['run_id'])['state'], 'cancelled')

    def test_real_runtime_reuses_claimed_run_and_saves_terminal_state(self):
        first = self.add()
        investigator = Investigator(self.db, Mock(), self.store)
        worker = JobWorker(self.queue, investigator)
        with patch('agents.runtime.ollama.models', return_value={ollama.CHAT_MODEL: 'fixture-digest'}), patch('agents.runtime.select_tools', return_value=[]):
            self.assertTrue(worker.tick())
        saved = self.queue.get(self.users['analyst'], first['run_id'])
        self.assertEqual(saved['state'], 'failed')
        self.assertEqual(len(self.store.recent(self.users['analyst'])), 1)
        self.assertFalse(worker.tick())

    def test_background_worker_failure_is_sanitized_and_not_retried(self):
        first = self.add()
        worker = JobWorker(self.queue, SimpleNamespace(run=Mock(side_effect=RuntimeError('DO-NOT-EXPOSE'))), enabled=True)
        async def exercise():
            worker.start()
            for _ in range(200):
                if self.queue.get(self.users['analyst'], first['run_id'])['state'] == 'failed': break
                await asyncio.sleep(.01)
            await worker.stop()
        asyncio.run(exercise())
        saved = self.queue.get(self.users['analyst'], first['run_id'])
        self.assertEqual(saved['state'], 'failed')
        self.assertNotIn('DO-NOT-EXPOSE', json.dumps(saved))
        self.assertEqual(worker.investigator.run.call_count, 1)

    def test_authenticated_queue_api_acknowledges_and_scopes_saved_jobs(self):
        with patch.dict('os.environ', {'AIN_AGENT_JOBS': '1'}):
            app = create_app(self.db)
        worker = app.state.job_worker
        with patch.object(worker, 'start'), patch.object(worker, 'stop', new=AsyncMock()):
            with TestClient(app) as client:
                worker.task = SimpleNamespace(done=lambda: False)
                self.assertEqual(client.post('/api/v1/research/agent-jobs', headers={'Origin': 'http://localhost:8080'}).status_code, 401)
                def login(name):
                    response = client.post('/api/v1/auth/login', headers={'Origin': 'http://localhost:8080'}, json={'username': name, 'password': 'isolated-job-fixture-123'})
                    return {'Origin': 'http://localhost:8080', 'X-CSRF-Token': response.json()['csrf_token'], 'Idempotency-Key': str(uuid4())}
                headers = login('analyst')
                response = client.post('/api/v1/research/agent-jobs', headers=headers, json=self.request().model_dump())
                self.assertEqual(response.status_code, 202)
                run_id = response.json()['run_id']
                replay = client.post('/api/v1/research/agent-jobs', headers=headers, json=self.request().model_dump())
                self.assertEqual(replay.json()['run_id'], run_id)
                self.assertEqual(client.get('/api/v1/research/agent-jobs/' + run_id).status_code, 200)
                headers = login('other')
                self.assertEqual(client.get('/api/v1/research/agent-jobs/' + run_id).status_code, 404)
                self.assertEqual(client.post('/api/v1/research/agent-cancel', headers=headers, json={'run_id': run_id}).status_code, 404)
                headers = login('reader')
                self.assertEqual(client.post('/api/v1/research/agent-jobs', headers=headers, json=self.request().model_dump()).status_code, 403)
                headers = login('admin')
                self.assertEqual(client.post('/api/v1/research/agent-cancel', headers=headers, json={'run_id': run_id}).json()['state'], 'cancelled')
                worker.enabled = False
                self.assertEqual(client.post('/api/v1/research/agent-jobs', headers=headers, json=self.request('disabled').model_dump()).status_code, 503)
