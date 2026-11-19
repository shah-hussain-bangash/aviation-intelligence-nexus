from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.api.history import IdempotencyConflict, ResearchHistory
from services.api.main import initialize


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "history.sqlite3"
        initialize(self.db)
        self.history = ResearchHistory(self.db)
        self.payload = {"carrier": "AA", "origin": "JFK", "destination": "LAX"}
        self.result = {"scenario": self.payload, "model_version": "synthetic_test",
                       "artifact_sha256": "test-digest", "arrival_delay_15_probability": .2}

    def tearDown(self):
        self.temp.cleanup()

    def test_persistence_idempotency_and_conflict(self):
        first = self.history.save("key", self.payload, self.result)
        initialize(self.db)
        reopened = ResearchHistory(self.db)
        replay = reopened.lookup("key", self.payload)
        self.assertEqual(first["run_id"], replay["run_id"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(reopened.recent()), 1)
        with self.assertRaises(IdempotencyConflict):
            reopened.save("key", {"carrier": "OTHER"}, self.result)

    def test_concurrent_retries_save_one_record(self):
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.history.save("same-key", self.payload, self.result), range(8)))
        self.assertEqual(len({result["run_id"] for result in results}), 1)
        self.assertEqual(len(self.history.recent()), 1)

    def test_history_is_bounded_and_newest_first(self):
        results = [self.history.save(str(n), self.payload, self.result) for n in range(12)]
        recent = self.history.recent()
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent[0]["run_id"], results[-1]["run_id"])

    def test_upgrade_from_version_two_keeps_existing_flights(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("DROP TABLE research_runs")
            for table in ("auth_sessions", "auth_users", "auth_limits", "gate_runs"):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("DELETE FROM schema_migrations WHERE version>=3")
            connection.execute("INSERT INTO flights (source,source_record_id,flight_date,carrier,origin,destination) "
                "VALUES ('test','1','2025-01-01','TEST','AAA','BBB')")
        initialize(self.db)
        self.assertEqual(self.history.recent(), [])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM flights").fetchone()[0], 1)
