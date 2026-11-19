from contextlib import closing
import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ml.prepare_dataset import FEATURES, PERIODS, prepare
from pipelines.import_bts import SOURCE
from services.api.main import initialize


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "test.sqlite3"
        initialize(self.db)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for period in PERIODS.values():
                connection.execute("INSERT INTO imports VALUES (?, ?, ?, 4, 4, 0, CURRENT_TIMESTAMP)",
                                   (period, "https://example.org/synthetic-test", period))
                for n, (cancelled, diverted, target) in enumerate([(0, 0, 15), (1, 0, None), (0, 1, 30), (0, 0, None)]):
                    connection.execute("INSERT INTO flights (source, source_record_id, flight_date, carrier, "
                        "origin, destination, flight_number, scheduled_departure, arrival_delay_minutes, cancelled, diverted) "
                        "VALUES (?, ?, ?, 'TEST', 'AAA', 'BBB', '1', '0900', ?, ?, ?)",
                        (SOURCE, period + str(n), period + "-01", target, cancelled, diverted))

    def tearDown(self):
        self.temp.cleanup()

    def test_temporal_splits_exclusions_and_feature_allowlist(self):
        report = prepare(self.db, self.root / "dataset")
        self.assertNotIn("arrival_delay_minutes", FEATURES)
        self.assertNotIn("departure_delay_minutes", FEATURES)
        for name, period in PERIODS.items():
            info = report["splits"][name]
            self.assertEqual(info["eligible_records"], 1)
            self.assertEqual(info["excluded_cancelled"], 1)
            self.assertEqual(info["excluded_diverted"], 1)
            self.assertEqual(info["excluded_missing_or_invalid"], 1)
            with (self.root / "dataset" / f"{name}.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["flight_date"], period + "-01")
            self.assertEqual(rows[0]["arrival_delayed_15"], "1")

    def test_missing_period_leaves_no_partial_dataset(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("DELETE FROM imports WHERE period='2025-03'")
        with self.assertRaisesRegex(ValueError, "Required imported period"):
            prepare(self.db, self.root / "dataset")
        self.assertFalse((self.root / "dataset").exists())
        self.assertEqual(list(self.root.glob("dataset-*")), [])

    def test_reproducible_output_and_existing_version_protection(self):
        first = prepare(self.db, self.root / "one")
        second = prepare(self.db, self.root / "two")
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.db, self.root / "one")
