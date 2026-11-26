"""Temporary accounts and synthetic query outputs; no provider or live state."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from auth_helpers import authenticated_client
from rag.history import EvidenceHistory
from rag.service import Knowledge
from services.api.auth import COOKIE
from services.api.main import create_app


RESULT = {'question': 'Synthetic access-boundary fixture', 'mode': 'evidence_only',
          'evidence': [{'text': 'SYNTHETIC withheld evidence'}], 'claims': [],
          'research_only': True, 'operational_approval': False}
QUESTION = {'question': 'What are the research model limitations?', 'generate': True}


class KnowledgeAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / 'accounts.sqlite3'
        self.client = self.enterContext(authenticated_client(create_app(
            self.database, knowledge_index=Path(self.directory.name) / 'missing-index.json')))
        self.auth = self.client.app.state.auth_store
        self.auth.create_user('query-researcher', 'synthetic-research-password', 'researcher')
        response = self.client.post('/api/v1/auth/login', json={
            'username': 'query-researcher', 'password': 'synthetic-research-password'})
        self.assertEqual(response.status_code, 200)
        self.client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        self.token = self.client.cookies.get(COOKIE)
        self.user = self.auth.session(self.token)

    def change(self, statement):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(statement, (self.user['id'],))

    def count(self):
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT COUNT(*) FROM knowledge_runs').fetchone()[0]

    def query_after(self, change):
        def finish(_question):
            change()
            return RESULT.copy()
        with patch.object(Knowledge, 'query', side_effect=finish) as query:
            response = self.client.post('/api/v1/research/knowledge-query', json=QUESTION)
        query.assert_called_once()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'access_changed')
        self.assertNotIn('evidence', response.json())
        self.assertNotIn('SYNTHETIC withheld evidence', response.text)
        self.assertEqual(self.count(), 0)

    def test_logout_during_query_withholds_result_and_history(self):
        self.query_after(lambda: self.auth.logout(self.token))

    def test_expiry_during_query_withholds_result_and_history(self):
        self.query_after(lambda: self.change('UPDATE auth_sessions SET expires_at=0 WHERE user_id=?'))

    def test_disabled_account_with_existing_session_is_rejected(self):
        self.query_after(lambda: self.change('UPDATE auth_users SET active=0 WHERE id=?'))

    def test_viewer_role_with_existing_session_is_rejected(self):
        self.query_after(lambda: self.change("UPDATE auth_users SET role='viewer' WHERE id=?"))

    def test_token_rebound_to_another_active_researcher_is_rejected(self):
        self.auth.create_user('different-researcher', 'synthetic-other-password', 'researcher')
        self.query_after(lambda: self.change(
            "UPDATE auth_sessions SET user_id=(SELECT id FROM auth_users WHERE username='different-researcher') WHERE user_id=?"))

    def test_revocation_at_save_boundary_is_rechecked_in_store(self):
        original = EvidenceHistory.save
        def revoke_then_save(store, user, result, **options):
            self.auth.logout(self.token)
            return original(store, user, result, **options)
        with patch.object(EvidenceHistory, 'save', new=revoke_then_save):
            self.query_after(lambda: None)

    def test_unchanged_session_saves_owned_result(self):
        with patch.object(Knowledge, 'query', return_value=RESULT.copy()):
            response = self.client.post('/api/v1/research/knowledge-query', json=QUESTION)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['actor'], 'query-researcher')
        self.assertEqual(self.count(), 1)
        history = self.client.get('/api/v1/research/knowledge-history').json()['runs']
        self.assertEqual(history, [response.json()])

    def test_explicit_missing_token_cannot_use_fixture_save_path(self):
        for token in ('', 'x' * 129, False):
            with self.subTest(token_type=type(token).__name__), self.assertRaises(PermissionError):
                EvidenceHistory(self.database).save(self.user, RESULT, session_token=token)
        self.assertEqual(self.count(), 0)
