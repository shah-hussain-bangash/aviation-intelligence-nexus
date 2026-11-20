from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from services.api.main import create_app, initialize
from services.api.route_history import lookup, proportion, LookupBusy, LookupUnavailable, RouteNotObserved


def seed(database):
    initialize(database)
    rows = [('BTS_REPORTING_CARRIER','1','2025-01-15','AA','JFK','LAX',0,0,-10),
            ('BTS_REPORTING_CARRIER','2','2025-03-15','AA','JFK','LAX',0,0,300),
            ('BTS_REPORTING_CARRIER','3','2025-01-15','AA','JFK','LAX',1,0,None),
            ('BTS_REPORTING_CARRIER','4','2025-01-15','AA','JFK','LAX',0,1,900),
            ('BTS_REPORTING_CARRIER','5','2025-01-15','AA','JFK','LAX',0,0,None),
            ('BTS_REPORTING_CARRIER','6','2025-05-15','AA','JFK','LAX',0,0,20),
            ('BTS_REPORTING_CARRIER','7','2025-04-15','AA','JFK','LAX',0,0,1000),
            ('synthetic','8','2025-01-15','AA','JFK','LAX',0,0,1000),
            ('BTS_REPORTING_CARRIER','9','2025-01-15','AA','LAX','JFK',0,0,1000)]
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executemany('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,cancelled,diverted,arrival_delay_minutes) VALUES(?,?,?,?,?,?,?,?,?)',rows)


class RouteHistoryTests(unittest.TestCase):
    def test_wilson_reference_zero_all_and_invalid_counts(self):
        result = proportion(50, 100)
        self.assertAlmostEqual(result['wilson_95'][0], .4038315303659956)
        self.assertAlmostEqual(result['wilson_95'][1], .5961684696340044)
        self.assertEqual(proportion(0, 10)['wilson_95'][0], 0)
        self.assertGreater(proportion(0, 10)['wilson_95'][1], .27)
        self.assertEqual(proportion(10, 10)['wilson_95'][1], 1)
        self.assertIsNone(proportion(0, 0)['rate'])
        for pair in [(-1,10),(11,10),(0,-1),(True,1)]:
            with self.assertRaises(ValueError):
                proportion(*pair)

    def test_readonly_counts_denominators_clipping_and_fixed_periods(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'history.sqlite3'
            seed(database)
            before = database.read_bytes()
            data = lookup(database, 'JFK', 'LAX')
            self.assertEqual(database.read_bytes(), before)
            first, later = data['periods']
            self.assertEqual(first['flights'], 5)
            self.assertEqual(first['completed'], 2)
            self.assertEqual(first['delay_15']['rate'], .5)
            self.assertEqual(first['cancellation']['rate'], .2)
            self.assertEqual(first['mean_positive_delay_capped_180'], 90)
            self.assertEqual(first['missing_arrival'], 1)
            self.assertEqual(later['flights'], 1)
            self.assertFalse(data['comparison_support_met'])
            self.assertIsNone(data['delay_15_change_percentage_points'])
            self.assertIsNone(data['group_assignment'])
            self.assertFalse(data['production_ready'])

    def test_missing_period_unknown_route_and_invalid_source_fail_safely(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'history.sqlite3'
            seed(database)
            reverse = lookup(database, 'LAX', 'JFK')
            self.assertFalse(reverse['periods'][1]['available'])
            self.assertIsNone(reverse['periods'][1]['delay_15']['rate'])
            with self.assertRaises(RouteNotObserved):
                lookup(database, 'AAA', 'BBB')
            for pair in [('JFK','JFK'),('jfk','LAX'),("JFK';--",'LAX')]:
                with self.assertRaises(ValueError):lookup(database,*pair)
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute("UPDATE flights SET cancelled=NULL WHERE source_record_id='1'")
            with self.assertRaises(LookupUnavailable):lookup(database,'JFK','LAX')

    def test_busy_deadline_and_release_after_failures(self):
        lock = Mock()
        lock.acquire.return_value = False
        with patch('services.api.route_history._SLOT',lock), self.assertRaises(LookupBusy):
            lookup(Path('unused.sqlite3'),'JFK','LAX')
        lock.release.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'history.sqlite3'
            seed(database)
            with patch('services.api.route_history.time.monotonic',side_effect=[0,100]), self.assertRaises(LookupUnavailable):
                lookup(database,'JFK','LAX')
            # Timed-out requests release the slot; a later valid read succeeds.
            self.assertEqual(lookup(database,'JFK','LAX')['periods'][0]['flights'],5)

    def test_authenticated_viewer_reads_and_invalid_queries_never_reach_sql(self):
        with tempfile.TemporaryDirectory() as folder:
            database=Path(folder)/'api.sqlite3'
            seed(database)
            app=create_app(database)
            with TestClient(app) as client:
                base='/api/v1/research/route-profile'
                self.assertEqual(client.get(base+'?origin=JFK&destination=LAX').status_code,401)
                password='isolated-route-fixture-123'
                app.state.auth_store.create_user('fixture-admin',password,'admin')
                app.state.auth_store.create_user('fixture-viewer',password,'viewer')
                origin={'Origin':'http://127.0.0.1:8080'}
                login=client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':password},headers=origin)
                client.headers.update({**origin,'X-CSRF-Token':login.json()['csrf_token']})
                response=client.get(base+'?origin=JFK&destination=LAX')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['cache-control'],'no-store')
                self.assertEqual(client.post(base,json={}).status_code,405)
                with patch('services.api.main.lookup_route') as query:
                    for suffix in ['', '?origin=JFK', '?origin=JFK&origin=LAX&destination=LAX','?origin=JFK&destination=LAX&limit=100']:
                        self.assertEqual(client.get(base+suffix).status_code,422)
                    query.assert_not_called()

    def test_api_failure_classes_do_not_expose_internal_details(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app(Path(folder)/'api.sqlite3')
            with TestClient(app) as client:
                app.state.auth_store.create_user('fixture-admin','isolated-route-fixture-123','admin')
                client.post('/api/v1/auth/login',json={'username':'fixture-admin','password':'isolated-route-fixture-123'},headers={'Origin':'http://127.0.0.1:8080'})
                for exception,status in [(LookupBusy,429),(LookupUnavailable,503),(RouteNotObserved,404)]:
                    with patch('services.api.main.lookup_route',side_effect=exception('private database details')):
                        response=client.get('/api/v1/research/route-profile?origin=JFK&destination=LAX')
                    self.assertEqual(response.status_code,status)
                    self.assertNotIn('private database',response.text)
                    self.assertNotIn('periods',response.json())
