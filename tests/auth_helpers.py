"""Real authenticated sessions for temporary API fixtures; no production bypass."""

from fastapi.testclient import TestClient


class authenticated_client(TestClient):
    def __enter__(self):
        super().__enter__()
        if self.app.state.auth_store.enrollment_required():
            self.app.state.auth_store.create_user("test-admin", "temporary-test-fixture-123", "admin")
        response = self.post("/api/v1/auth/login", json={"username": "test-admin", "password": "temporary-test-fixture-123"},
                             headers={"Origin": "http://127.0.0.1:8080"})
        assert response.status_code == 200
        self.headers.update({"X-CSRF-Token": response.json()["csrf_token"], "Origin": "http://127.0.0.1:8080"})
        return self
