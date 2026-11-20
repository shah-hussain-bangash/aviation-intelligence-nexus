from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from services.api.index_routes import ensure_index
from services.api.main import initialize
from services.api.route_history import lookup


class RouteIndexTests(unittest.TestCase):
    def test_index_setup_preserves_rows_schema_and_lookup_semantics_and_replays(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite3';initialize(path)
            with closing(sqlite3.connect(path)) as connection,connection:
                connection.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,cancelled,diverted,arrival_delay_minutes) VALUES('BTS_REPORTING_CARRIER','1','2025-01-01','AA','JFK','LAX',0,0,20)")
            before=lookup(path,'JFK','LAX')
            first=ensure_index(path);second=ensure_index(path)
            self.assertTrue(first['created']);self.assertFalse(second['created'])
            self.assertEqual(first['flight_records'],1)
            after=lookup(path,'JFK','LAX')
            self.assertEqual(before['periods'],after['periods'])
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0],7)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0],0)

    def test_missing_database_and_wrong_existing_definition_fail_without_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite3'
            with self.assertRaises(ValueError):ensure_index(path)
            self.assertFalse(path.exists())
            initialize(path)
            with closing(sqlite3.connect(path)) as connection,connection:
                connection.execute('CREATE INDEX flights_route_history_v1 ON flights(carrier)')
            with self.assertRaises(ValueError):ensure_index(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual([row[2] for row in connection.execute("PRAGMA index_info('flights_route_history_v1')")],['carrier'])
