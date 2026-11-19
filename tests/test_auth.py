from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from services.api.auth import COOKIE
from services.api.history import ResearchHistory, IdempotencyConflict
from services.api.main import create_app

ORIGIN = {"Origin": "http://127.0.0.1:8080"}
PASSWORD = "isolated-fixture-password-123"


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "auth.sqlite3"
        self.app = create_app(self.db, research_model_directory=Path(self.temp.name) / "missing")
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def accounts(self):
        for username, role in [("admin", "admin"), ("analyst", "researcher"), ("reader", "viewer")]:
            self.app.state.auth_store.create_user(username, PASSWORD, role)

    def login(self, username="admin", client=None):
        client = client or self.client
        response = client.post("/api/v1/auth/login", json={"username":username,"password":PASSWORD}, headers=ORIGIN)
        self.assertEqual(response.status_code, 200)
        client.headers.update({**ORIGIN,"X-CSRF-Token":response.json()["csrf_token"]})
        return response

    def test_anonymous_data_is_denied_and_first_enrollment_is_explicit(self):
        for path in ["/api/v1/status", "/api/v1/research/summary", "/api/v1/research/history", "/api/v1/model/report"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/research/predict",json={},headers=ORIGIN).status_code,401)
        self.assertTrue(self.client.get("/api/v1/auth/session").json()["enrollment_required"])
        self.assertEqual(self.client.get("/health/live").status_code,200)

    def test_password_hash_and_session_cookie_protection(self):
        self.accounts()
        response=self.login()
        cookie=response.headers["set-cookie"]
        self.assertIn("HttpOnly",cookie);self.assertIn("SameSite=strict",cookie);self.assertIn("Path=/api",cookie)
        with closing(sqlite3.connect(self.db)) as db:
            encoded=db.execute("SELECT password_hash FROM auth_users WHERE username='admin'").fetchone()[0]
            self.assertTrue(encoded.startswith("$argon2id$"));self.assertNotIn(PASSWORD,encoded)
            stored=db.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]
            self.assertNotEqual(stored,self.client.cookies.get(COOKIE))

    def test_viewer_reads_but_cannot_calculate(self):
        self.accounts();self.login("reader")
        self.assertEqual(self.client.get("/api/v1/research/summary").status_code,200)
        self.assertEqual(self.client.post("/api/v1/research/predict",json={}).status_code,403)
        self.assertEqual(self.client.get("/api/v1/research/history").json()["runs"],[])

    def test_researcher_reaches_model_service_with_valid_request(self):
        self.accounts();self.login("analyst")
        response=self.client.post("/api/v1/research/predict",json={"carrier":"AA","origin":"JFK","destination":"LAX",
            "flight_date":"2025-05-15","scheduled_departure":"09:00"})
        self.assertEqual(response.status_code,503)  # Authorized, but this isolated fixture has no model file.
        self.assertEqual(response.json()["error"],"research_model_unavailable")

    def test_origin_and_csrf_are_required_for_mutations(self):
        self.accounts()
        self.assertEqual(self.client.post("/api/v1/auth/login",json={"username":"admin","password":PASSWORD},headers={"Origin":"https://untrusted.example"}).status_code,403)
        self.login()
        self.assertEqual(self.client.post("/api/v1/auth/logout",json={},headers={"X-CSRF-Token":"wrong"}).status_code,403)
        self.assertEqual(self.client.post("/api/v1/auth/logout",json={},headers={"Origin":"https://untrusted.example"}).status_code,403)
        self.assertEqual(self.client.post("/api/v1/auth/logout",json={}).status_code,200)
        self.assertEqual(self.client.get("/api/v1/research/history").status_code,401)

    def test_repeated_invalid_logins_are_throttled(self):
        self.accounts()
        for _ in range(5):
            response=self.client.post("/api/v1/auth/login",json={"username":"admin","password":"wrong"},headers=ORIGIN)
            self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.post("/api/v1/auth/login",json={"username":"admin","password":"wrong"},headers=ORIGIN).status_code,429)

    def test_session_survives_restart_and_expires(self):
        self.accounts();self.login()
        with TestClient(create_app(self.db)) as restarted:
            restarted.cookies.update(self.client.cookies)
            self.assertTrue(restarted.get("/api/v1/auth/session").json()["authenticated"])
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute("UPDATE auth_sessions SET expires_at=?",(time.time()-1,))
        self.assertEqual(self.client.get("/api/v1/research/history").status_code,401)

    def test_access_changes_revoke_sessions_and_preserve_last_admin(self):
        self.accounts();self.login("analyst")
        self.app.state.auth_store.set_access("analyst","viewer")
        self.assertEqual(self.client.get("/api/v1/research/history").status_code,401)
        with self.assertRaises(ValueError):self.app.state.auth_store.set_access("admin",disable=True)

    def test_owner_scoping_and_legacy_admin_visibility(self):
        self.accounts();login=self.login("analyst");analyst=login.json()["user"]
        history=ResearchHistory(self.db)
        payload={"carrier":"AA"};result={"model_version":"test","artifact_sha256":"fixture","scenario":payload,"arrival_delay_15_probability":.2}
        history.save("legacy",payload,result)
        saved=history.save("owned",payload,result,analyst)
        self.assertEqual([r["run_id"] for r in self.client.get("/api/v1/research/history").json()["runs"]],[saved["run_id"]])
        self.login("reader")
        self.assertEqual(self.client.get("/api/v1/research/history").json()["runs"],[])
        self.login("admin")
        self.assertEqual(len(self.client.get("/api/v1/research/history").json()["runs"]),2)
        with self.assertRaises(IdempotencyConflict):history.lookup("owned",payload,"another-account")

    def test_account_policy_rejects_weak_password_and_nonadmin_bootstrap(self):
        with self.assertRaises(ValueError):self.app.state.auth_store.create_user("first",PASSWORD,"viewer")
        with self.assertRaises(ValueError):self.app.state.auth_store.create_user("first","short","admin")

    def test_identity_store_failure_does_not_allow_anonymous_access(self):
        with closing(sqlite3.connect(self.db)) as db,db:db.execute("DROP TABLE auth_users")
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code,503)
        self.assertEqual(self.client.post("/api/v1/auth/login",json={"username":"admin","password":PASSWORD},headers=ORIGIN).status_code,503)
