"""Synthetic accounts/providers exercise the actual background runtime and store."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from agents import tools
from agents.jobs import JobQueue
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore
from rag import ollama
from services.api.auth import AuthStore
from services.api.main import initialize


class BackgroundOwnerAccessTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database = Path(folder.name) / 'synthetic.sqlite3'
        initialize(self.database)
        self.auth = AuthStore(self.database)
        self.auth.create_user('fixture-admin', 'temporary-access-fixture', 'admin')
        self.auth.create_user('fixture-owner', 'temporary-access-fixture', 'researcher')
        with closing(self.auth.connect()) as db:
            self.user = dict(db.execute("SELECT id,username,role FROM auth_users WHERE username='fixture-owner'").fetchone())
        self.store = AgentStore(self.database)
        self.queue = JobQueue(self.store)
        self.runtime = Investigator(self.database, Mock(), self.store)
        self.request = Investigation(objective='SYNTHETIC access-boundary review of recorded model limitations.',
                                    include_model_evidence=True, required_tools=['model_evidence'])

    def claim(self):
        self.queue.enqueue(self.user, str(uuid4()), self.request)
        return self.queue.claim()

    def revoke(self, kind='disabled'):
        statements = {'disabled': 'UPDATE auth_users SET active=0 WHERE id=?',
                      'viewer': "UPDATE auth_users SET role='viewer' WHERE id=?",
                      'missing': 'DELETE FROM auth_users WHERE id=?'}
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(statements[kind], (self.user['id'],))

    def exercise(self, stage):
        user, key, claimed = self.claim()
        entered, release = Event(), Event()
        actual_execute = tools.execute
        calls = [0]
        def planner(*args):
            calls[0] += 1
            if calls[0] > 1: return []
            if stage == 'planner': entered.set(); release.wait(5)
            return [{'function': {'name': 'model_evidence', 'arguments': {}}}]
        def execute(*args):
            if stage == 'tool': entered.set(); release.wait(5)
            return actual_execute(*args)
        def generate(*args, **kwargs):
            if stage == 'summary': entered.set(); release.wait(5)
            return {'claims': []}
        with patch.object(ollama, 'models', return_value={ollama.CHAT_MODEL: 'synthetic-digest'}), \
             patch('agents.runtime.select_tools', side_effect=planner), \
             patch.object(tools, 'execute', side_effect=execute) as tool, \
             patch.object(ollama, 'generate', side_effect=generate) as summary:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.runtime.run, user, key, self.request, queued_result=claimed)
                try:
                    self.assertTrue(entered.wait(5), 'Expected controlled call boundary')
                    self.revoke()
                    self.assertFalse(future.done(), 'Revocation is cooperative, not forced interruption')
                finally: release.set()
                result = future.result(timeout=5)
            self.assertEqual(tool.call_count, 0 if stage == 'planner' else 1)
            self.assertEqual(summary.call_count, 1 if stage == 'summary' else 0)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['claims'], [])
        self.assertNotIn('report_sha256', result)
        if stage != 'planner':
            self.assertEqual(result['steps'][0]['state'], 'completed')
            self.assertIn('observation', result['steps'][0])
        self.assertEqual(self.queue.get(user, result['run_id'])['state'], 'cancelled')
        self.assertIsNone(self.queue.claim())

    def test_disabled_during_planner_skips_tool(self): self.exercise('planner')
    def test_disabled_during_tool_retains_completed_evidence_without_summary(self): self.exercise('tool')
    def test_disabled_during_summary_withholds_draft(self): self.exercise('summary')

    def test_revocation_before_execution_skips_all_provider_calls(self):
        user, key, result = self.claim()
        self.revoke('viewer')
        with patch.object(ollama, 'models') as models:
            saved = self.runtime.run(user, key, self.request, queued_result=result)
        models.assert_not_called()
        self.assertEqual(saved['state'], 'cancelled')

    def test_missing_owner_is_a_stop_request(self):
        _, _, result = self.claim()
        self.revoke('missing')
        self.assertTrue(self.store.stop_requested(result['run_id']))

    def test_final_write_rechecks_revocation_and_clears_reviewable_fields(self):
        _, _, result = self.claim()
        self.assertFalse(self.store.stop_requested(result['run_id']))
        self.revoke('viewer')
        result.update(state='awaiting_review', claims=[{'text': 'SYNTHETIC draft'}],
                      report_sha256='a'*64, quality={'passed': True}, report_status='coverage_passed')
        self.store.checkpoint(result)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['claims'], [])
        for name in ('report_sha256', 'quality', 'report_status'): self.assertNotIn(name, result)

    def test_failure_and_conflict_requeue_cannot_escape_revocation(self):
        for state in ('failed', 'queued'):
            with self.subTest(state=state):
                # A distinct running row exercises each terminal-write path.
                self.revoke('viewer')
                with closing(sqlite3.connect(self.database)) as db, db:
                    db.execute("UPDATE auth_users SET role='researcher' WHERE id=?", (self.user['id'],))
                _, _, result = self.claim()
                self.revoke()
                result['state'] = state
                self.store.checkpoint(result)
                self.assertEqual(result['state'], 'cancelled')
                with closing(sqlite3.connect(self.database)) as db, db:
                    db.execute('UPDATE auth_users SET active=1 WHERE id=?', (self.user['id'],))

    def test_completed_report_is_not_rewritten_by_later_revocation(self):
        _, _, result = self.claim()
        result.update(state='awaiting_review', claims=[], report_sha256='a'*64)
        self.store.checkpoint(result)
        before = copy.deepcopy(self.queue.get(self.user, result['run_id']))
        self.revoke()
        self.assertEqual(self.queue.get(self.user, result['run_id']), before)

    def test_logout_alone_does_not_cancel_account_owned_background_job(self):
        _, _, result = self.claim()
        token = self.auth.login('fixture-owner', 'temporary-access-fixture')
        self.assertIsNotNone(self.auth.session(token))
        self.auth.logout(token)
        self.assertFalse(self.store.stop_requested(result['run_id']))
