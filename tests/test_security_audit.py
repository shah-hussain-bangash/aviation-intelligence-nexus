from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from services.api.main import create_app, initialize
from services.api.auth import AuthStore, LoginDenied, LoginLimited
from services.api.account_security import account_sessions
from services.api.security_audit import append_event, latest_events


class SecurityAuditTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(); self.path = Path(self.folder.name) / 'synthetic.sqlite3'
        initialize(self.path); self.auth = AuthStore(self.path)
        self.password = 'synthetic-private-password-123'
        self.auth.create_user('synthetic-admin', self.password, 'admin')

    def tearDown(self):
        self.folder.cleanup()

    def rows(self):
        return latest_events(self.path)['events']

    def execute(self, sql):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(sql)

    def test_success_denial_and_limit_events_are_committed_without_credentials(self):
        request_id = str(uuid4()); token = self.auth.login('synthetic-admin', self.password, request_id=request_id)
        self.auth.logout(token, request_id=str(uuid4()))
        for _ in range(5):
            with self.assertRaises(LoginDenied):
                self.auth.login('unknown-private-name', 'PRIVATE-BAD-PASSWORD')
        with self.assertRaises(LoginLimited):
            self.auth.login('unknown-private-name', 'PRIVATE-BAD-PASSWORD')
        rows = self.rows(); text = json.dumps(rows)
        self.assertEqual(sum(r['outcome'] == 'denied' for r in rows), 5)
        self.assertEqual(sum(r['outcome'] == 'limited' for r in rows), 1)
        self.assertEqual(next(r for r in rows if r['request_id'] == request_id)['outcome'], 'success')
        for secret in (self.password, 'PRIVATE-BAD-PASSWORD', 'unknown-private-name', 'synthetic-admin', token, hashlib.sha256(token.encode()).hexdigest()):
            self.assertNotIn(secret, text)
        self.assertTrue(all(r['actor_id'] is None and r['subject_id'] is None for r in rows if r['outcome'] in ('denied', 'limited')))

    def test_audit_failure_rolls_back_success_failure_creation_and_access_changes(self):
        token = self.auth.login('synthetic-admin', self.password)
        before = self.rows()
        with patch('services.api.auth.append_event', side_effect=sqlite3.OperationalError('PRIVATE-FAILURE')):
            for action in (lambda:self.auth.login('synthetic-admin', self.password),
                           lambda:self.auth.login('unknown-private-name', 'bad'),
                           lambda:self.auth.logout(token),
                           lambda:self.auth.create_user('new-private-name', self.password, 'viewer')):
                with self.assertRaises(sqlite3.Error):action()
        self.assertIsNotNone(self.auth.session(token)); self.assertEqual(before, self.rows())
        self.auth.create_user('other-admin', self.password, 'admin')
        with patch('services.api.auth.append_event', side_effect=sqlite3.OperationalError('PRIVATE-FAILURE')):
            with self.assertRaises(sqlite3.Error):self.auth.set_access('synthetic-admin', role='viewer')
        self.assertEqual(self.auth.session(token)['role'], 'admin')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM auth_users WHERE username='new-private-name'").fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM auth_limits').fetchone()[0], 0)

    def test_session_revocation_event_is_atomic_and_identifies_account_without_token(self):
        first = self.auth.login('synthetic-admin', self.password); other = self.auth.login('synthetic-admin', self.password)
        with patch('services.api.account_security.append_event', side_effect=sqlite3.OperationalError('unavailable')):
            with self.assertRaises(sqlite3.Error):account_sessions(self.path, first, revoke_others=True)
        self.assertIsNotNone(self.auth.session(other))
        request_id = str(uuid4()); result = account_sessions(self.path, first, revoke_others=True, request_id=request_id)
        self.assertEqual(result['revoked_other_sessions'], 1); self.assertIsNone(self.auth.session(other))
        event = self.rows()[0]; self.assertEqual(event['action'], 'other_sessions_revoked')
        self.assertEqual(event['request_id'], request_id); self.assertEqual(event['subject_id'], self.auth.session(first)['id'])
        self.assertNotIn(first, json.dumps(event)); self.assertNotIn(other, json.dumps(event))

    def test_version_seven_upgrade_preserves_accounts_sessions_and_flights(self):
        token = self.auth.login('synthetic-admin', self.password)
        # Reconstruct a pre-audit synthetic v7 fixture; never edit real history this way.
        self.execute('DROP TABLE security_audit'); self.execute('DELETE FROM schema_migrations WHERE version=8')
        self.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES ('synthetic','1','2025-01-01','XX','AAA','BBB')")
        with closing(sqlite3.connect(self.path)) as db:
            users = db.execute('SELECT * FROM auth_users').fetchall(); sessions = db.execute('SELECT * FROM auth_sessions').fetchall()
        initialize(self.path); self.assertEqual(self.rows(), [])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(users, db.execute('SELECT * FROM auth_users').fetchall())
            self.assertEqual(sessions, db.execute('SELECT * FROM auth_sessions').fetchall())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM flights').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0], 8)
        self.assertIsNotNone(self.auth.session(token))
        initialize(self.path); self.assertEqual(self.rows(), [])

    def test_local_append_guards_bounded_page_and_identifier_filter(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            for _ in range(105):append_event(db, 'sign_in', 'denied', request_id='PRIVATE-HEADER')
        report = latest_events(self.path)
        self.assertEqual(len(report['events']), 100); self.assertTrue(report['has_older_events'])
        self.assertFalse(report['protected_external_storage']); self.assertFalse(report['production_ready'])
        self.assertTrue(all(r['request_id'] is None for r in report['events']))
        with self.assertRaises(sqlite3.IntegrityError):self.execute('DELETE FROM security_audit')
        with self.assertRaises(sqlite3.IntegrityError):self.execute("UPDATE security_audit SET outcome='success'")
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(RuntimeError):append_event(db, 'sign_in', 'success')

    def test_failed_version_eight_migration_rolls_back_table_and_history(self):
        self.execute('DROP TABLE security_audit'); self.execute('DELETE FROM schema_migrations WHERE version=8')
        with closing(sqlite3.connect(self.path)) as db:
            before='\n'.join(db.iterdump())
        db=sqlite3.connect(self.path)
        db.set_authorizer(lambda action,arg1,arg2,database,trigger:
            sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_CREATE_TRIGGER else sqlite3.SQLITE_OK)
        with patch('services.api.main.connect',return_value=db):
            with self.assertRaises(sqlite3.DatabaseError):initialize(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(before,'\n'.join(db.iterdump()))

    def test_concurrent_logins_have_unique_monotonic_events_and_sessions(self):
        with ThreadPoolExecutor(max_workers=3) as workers:
            tokens = list(workers.map(lambda _:AuthStore(self.path).login('synthetic-admin', self.password), range(6)))
        rows = self.rows(); self.assertEqual(len(rows), 7)
        self.assertEqual(len({r['event_id'] for r in rows}), 7)
        self.assertEqual([r['sequence'] for r in rows], list(range(7, 0, -1)))
        self.assertTrue(all(self.auth.session(token) for token in tokens))

    def test_api_role_method_query_boundaries_server_request_id_and_audit_outage(self):
        self.auth.create_user('synthetic-viewer', self.password, 'viewer')
        self.auth.create_user('synthetic-researcher', self.password, 'researcher')
        with TestClient(create_app(self.path)) as client:
            path = '/api/v1/research/security-audit'
            self.assertEqual(client.get(path).status_code, 401)
            for name in ('synthetic-viewer', 'synthetic-researcher', 'synthetic-admin'):
                client.cookies.clear()
                response = client.post('/api/v1/auth/login', json={'username':name, 'password':self.password}, headers={'Origin':'http://127.0.0.1:8080','X-Request-ID':'PRIVATE-SPOOF'})
                self.assertEqual(response.status_code, 200)
                audit = client.get(path)
                self.assertEqual(audit.status_code, 200 if name == 'synthetic-admin' else 403)
            self.assertEqual(audit.json()['events'][0]['request_id'], response.headers['X-Request-ID'])
            self.assertEqual(client.get(path+'?limit=1').status_code, 422)
            headers = {'Origin':'http://127.0.0.1:8080','X-CSRF-Token':response.json()['csrf_token']}
            self.assertEqual(client.post(path,json={},headers=headers).status_code, 405)
            self.execute('DROP TABLE security_audit')
            self.assertEqual(client.get(path).status_code, 503)
            logout = client.post('/api/v1/auth/logout',json={},headers=headers)
            self.assertEqual(logout.status_code, 503)
            self.assertTrue(client.get('/api/v1/auth/session').json()['authenticated'])
            failed = client.post('/api/v1/auth/login', json={'username':'synthetic-admin','password':self.password}, headers={'Origin':'http://127.0.0.1:8080'})
            self.assertEqual(failed.status_code, 503)
            self.assertNotIn(self.password, failed.text)
