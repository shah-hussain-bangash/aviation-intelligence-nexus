from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from ml.route_segments import aggregate, experiment, fit, load_protocol, PROTOCOL_PATH


def database(path, later_delay=20):
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('CREATE TABLE flights(source TEXT,flight_date TEXT,origin TEXT,destination TEXT,cancelled INTEGER,diverted INTEGER,arrival_delay_minutes REAL)')
        connection.execute('CREATE TABLE imports(period TEXT,sha256 TEXT,rows_inserted INTEGER)')
        rows = []
        for i in range(60):
            origin = chr(65 + i // 26) + chr(65 + i % 26) + 'A'
            for month, count in [('01', 240), ('05', 80)]:
                for j in range(count):
                    cancelled = int(j % (70 if i < 30 else 10) == 0)
                    delay = 90 if j % (50 if i < 30 else 5) == 0 else 20 if j % ((10 if i < 30 else 2) + i % 3) == 0 else -5
                    if month == '05':
                        delay = later_delay
                    rows.append(('BTS_REPORTING_CARRIER', f'2025-{month}-15', origin, 'ZZZ', cancelled, 0, delay))
        # April is deliberately excluded from both defined periods.
        rows.append(('BTS_REPORTING_CARRIER', '2025-04-15', 'AAA', 'ZZZ', 0, 0, 9999))
        connection.executemany('INSERT INTO flights VALUES(?,?,?,?,?,?,?)', rows)


class RouteSegmentTests(unittest.TestCase):
    def test_protocol_fingerprint_rejects_changed_experiment(self):
        self.assertEqual(load_protocol()['evaluation'], ['2025-05-01', '2025-06-01'])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'changed.json'
            target.write_text(PROTOCOL_PATH.read_text() + ' ')
            with patch('ml.route_segments.PROTOCOL_PATH', target), self.assertRaises(ValueError):
                load_protocol()

    def test_sql_denominators_clipping_direction_and_exclusion(self):
        with closing(sqlite3.connect(':memory:')) as connection:
            connection.execute('CREATE TABLE flights(source TEXT,flight_date TEXT,origin TEXT,destination TEXT,cancelled INTEGER,diverted INTEGER,arrival_delay_minutes REAL)')
            rows = [('BTS_REPORTING_CARRIER', '2025-01-15', 'AAA', 'BBB', 0, 0, -10),
                    ('BTS_REPORTING_CARRIER', '2025-01-15', 'AAA', 'BBB', 0, 0, 300),
                    ('BTS_REPORTING_CARRIER', '2025-01-15', 'AAA', 'BBB', 1, 0, None),
                    ('BTS_REPORTING_CARRIER', '2025-01-15', 'AAA', 'BBB', 0, 1, 500),
                    ('BTS_REPORTING_CARRIER', '2025-01-15', 'BBB', 'AAA', 0, 0, 0),
                    ('synthetic', '2025-01-15', 'AAA', 'BBB', 0, 0, 1000),
                    ('BTS_REPORTING_CARRIER', '2025-05-15', 'AAA', 'BBB', 0, 0, 1000)]
            connection.executemany('INSERT INTO flights VALUES(?,?,?,?,?,?,?)', rows)
            frame = aggregate(connection, ['2025-01-01', '2025-04-01'], 'BTS_REPORTING_CARRIER')
            row = frame.iloc[0]
            self.assertEqual(len(frame), 2)
            self.assertEqual(row['flights'], 4)
            self.assertEqual(row['completed'], 2)
            self.assertEqual(row['delay_15_rate'], .5)
            self.assertEqual(row['mean_positive_delay_capped_180'], 90)
            self.assertEqual(row['cancellation_rate'], .25)
            connection.execute("UPDATE flights SET cancelled=NULL WHERE origin='BBB'")
            with self.assertRaises(ValueError):
                aggregate(connection, ['2025-01-01', '2025-04-01'], 'BTS_REPORTING_CARRIER')

    def test_temporal_mutation_does_not_change_training_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            left, right = root / 'a.sqlite3', root / 'b.sqlite3'
            database(left, 0)
            database(right, 150)
            before = left.read_bytes()
            a, b = experiment(left, root / 'a'), experiment(right, root / 'b')
            self.assertEqual(left.read_bytes(), before)
            self.assertEqual(a['selected_k'], b['selected_k'])
            for first, second in zip(a['candidates'], b['candidates']):
                self.assertEqual(first['k'], second['k'])
                self.assertEqual(first['support_passed'], second['support_passed'])
                self.assertAlmostEqual(first['training_silhouette'], second['training_silhouette'], places=10)
                self.assertAlmostEqual(first['inertia'], second['inertia'], places=8)
            self.assertEqual(a['training_scaler_mean'], b['training_scaler_mean'])
            self.assertEqual(a['training_seed_stability'], b['training_seed_stability'])
            self.assertEqual(a['coverage']['train']['flights_observed'], 60 * 240)
            self.assertNotEqual(a['later_period'], b['later_period'])
            self.assertFalse(a['production_ready'])
            self.assertEqual(sum(map(sum, a['later_period']['transition_counts_training_rows_evaluation_columns'])), 60)

    def test_unsupported_degenerate_candidates_fail_closed(self):
        protocol = load_protocol()
        protocol['candidates'] = [2]
        frame = pd.DataFrame(np.ones((12, 4)), columns=protocol['features'])
        with threadpool_limits(limits=2), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with self.assertRaisesRegex(ValueError, 'No training candidate'):
                fit(frame, protocol)

    def test_existing_experiment_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'existing'
            output.mkdir()
            marker = output / 'marker.txt'
            marker.write_text('keep')
            with self.assertRaises(ValueError):
                experiment(Path(folder) / 'absent.sqlite3', output)
            self.assertEqual(marker.read_text(), 'keep')
