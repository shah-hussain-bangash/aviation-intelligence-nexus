from contextlib import closing
import csv
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from pipelines.import_bts import import_archive


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "test.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, invalid=False, conflict=False):
        fields = ["FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
                  "Origin", "Dest", "CRSDepTime", "DepDelay", "ArrDelay", "Cancelled", "Diverted"]
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(fields)
        writer.writerow(["2025-01-01", "AA", "1", "JFK", "LAX", "0900", "", "", "1", "0"])
        if invalid or conflict:
            writer.writerow(["2025-02-01" if invalid else "2025-01-01", "AA", "1",
                             "JFK", "LAX", "0900", "3", "5", "0", "0"])
        archive = self.root / "input.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("data.csv", text.getvalue())
        return archive

    def test_repeat_import_does_not_duplicate_and_missing_delays_stay_null(self):
        archive = self.archive()
        self.assertEqual(import_archive(archive, self.db, 2025, 1)["rows_inserted"], 1)
        self.assertEqual(import_archive(archive, self.db, 2025, 1)["status"], "already_imported")
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*), departure_delay_minutes, cancelled FROM flights").fetchone(), (1, None, 1))

    def test_invalid_row_rolls_back_entire_import(self):
        with self.assertRaises(ValueError):
            import_archive(self.archive(invalid=True), self.db, 2025, 1)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM flights").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM imports").fetchone()[0], 0)

    def test_conflicting_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            import_archive(self.archive(conflict=True), self.db, 2025, 1)

    def test_wrong_schema_is_rejected(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("bad.csv", "wrong\n1\n")
        with self.assertRaisesRegex(ValueError, "Missing required"):
            import_archive(archive, self.db, 2025, 1)
