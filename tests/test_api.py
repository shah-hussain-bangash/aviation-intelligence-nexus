"""Local service checks with isolated temporary databases."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from auth_helpers import authenticated_client as TestClient
from services.api.main import create_app, initialize


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "test.sqlite3"

    def tearDown(self):
        self.directory.cleanup()

    def test_empty_database_is_truthful_and_read_only(self):
        with TestClient(create_app(self.database)) as client:
            self.assertEqual(client.get("/health/live").status_code, 200)
            self.assertEqual(client.get("/health/ready").status_code, 200)
            status = client.get("/api/v1/status").json()
            self.assertEqual(status["flight_records"], 0)
            self.assertEqual(status["data_status"], "not_imported")
            self.assertFalse(status["production_ready"])
            self.assertEqual(client.post("/api/v1/status", json={}).status_code, 405)
            self.assertEqual(client.get("/openapi.json").status_code, 200)

    def test_restart_preserves_records_and_migration(self):
        initialize(self.database)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("""INSERT INTO flights
                (source, source_record_id, flight_date, carrier, origin, destination)
                VALUES ('synthetic_test', '1', '2025-01-01', 'TEST', 'AAA', 'BBB')""")
        with TestClient(create_app(self.database)) as client:
            self.assertEqual(client.get("/api/v1/status").json()["flight_records"], 1)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 4)

    def test_database_failure_is_not_reported_as_ready(self):
        with TestClient(create_app(self.database)) as client:
            with closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute("DROP TABLE flights")
            self.assertEqual(client.get("/health/live").status_code, 200)
            self.assertEqual(client.get("/health/ready").status_code, 503)
            self.assertEqual(client.get("/api/v1/status").status_code, 503)
            self.assertEqual(client.get("/api/v1/research/summary").status_code, 503)

    def test_future_schema_is_rejected(self):
        initialize(self.database)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO schema_migrations(version) VALUES (99)")
        with self.assertRaises(RuntimeError):
            initialize(self.database)

    def test_missing_model_is_not_claimed_as_available(self):
        with TestClient(create_app(self.database, Path(self.directory.name) / "missing")) as client:
            self.assertEqual(client.get("/api/v1/model/report").status_code, 404)
            status = client.get("/api/v1/status").json()
            self.assertEqual(status["model_status"], "not_available")
            self.assertFalse(status["prediction_serving"])
            self.assertEqual(client.get("/api/v1/models/unknown/report").status_code, 422)

    def test_research_summary_excludes_synthetic_records_and_handles_absent_model(self):
        with TestClient(create_app(self.database, research_model_directory=Path(self.directory.name) / "missing")) as client:
            with closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute("INSERT INTO flights (source, source_record_id, flight_date, carrier, origin, destination, cancelled, diverted) "
                    "VALUES ('BTS_REPORTING_CARRIER', '1', '2025-01-01', 'AA', 'JFK', 'LAX', 0, 0)")
                connection.execute("INSERT INTO flights (source, source_record_id, flight_date, carrier, origin, destination) "
                    "VALUES ('synthetic', '2', '2025-01-01', 'TEST', 'AAA', 'BBB')")
            response = client.get("/api/v1/research/summary")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["dataset"]["records"], 1)
            self.assertEqual(payload["dataset"]["monthly"][0]["records"], 1)
            self.assertIsNone(payload["model"])
            self.assertFalse(payload["prediction_serving"])


if __name__ == "__main__":
    unittest.main()
