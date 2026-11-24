import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipelines.time_safe_features import weather_features, timestamp
from pipelines.verify_time_safe_features import fixture, verify
from services.api.paths import ROOT


class TimeSafeFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def join(self, **kwargs):
        return weather_features(**self.data, scope='synthetic', **kwargs)

    def test_availability_cutoff_staleness_airport_and_input_order(self):
        before = copy.deepcopy(self.data)
        joined = self.join()
        self.assertEqual([r['query_id'] for r in joined], [r['query_id'] for r in self.data['queries']])
        self.assertEqual([r['status'] for r in joined], ['unavailable', 'matched', 'matched', 'matched', 'stale', 'matched', 'unavailable'])
        self.assertEqual(joined[2]['event_id'], 'initial')
        self.assertEqual(joined[2]['age_seconds'], 3600)
        self.assertEqual(joined[3]['event_id'], 'late-report')
        self.assertIsNone(joined[4]['temperature_c'])
        self.assertIsNone(joined[4]['wind_knots'])
        self.assertEqual(joined[4]['event_id'], 'late-report')
        self.assertEqual(joined[5]['event_id'], 'other-airport')
        self.assertEqual(self.data, before)
        self.data['events'].reverse()
        self.assertEqual(self.join(), joined)

    def test_future_events_do_not_change_past_features_even_if_observed_earlier(self):
        before = self.join()
        event = dict(self.data['events'][0], event_id='revision', available_at='2025-01-01T11:00:00Z', temperature_c=99)
        self.data['events'].append(event)
        self.assertEqual(self.join(), before)
        self.assertEqual(self.join(max_age_seconds=3599)[2]['status'], 'stale')

    def test_duplicate_identity_collapses_but_conflicting_or_ambiguous_revisions_fail(self):
        expected = self.join()
        self.data['events'].append(dict(self.data['events'][0]))
        self.assertEqual(self.join(), expected)
        self.data['events'][-1]['wind_knots'] = 30
        with self.assertRaisesRegex(ValueError, '^conflicting_event_identity$'):
            self.join()
        self.data['events'][-1]['event_id'] = 'other-revision'
        with self.assertRaisesRegex(ValueError, '^ambiguous_availability_revision$'):
            self.join()

    def test_observation_cannot_be_after_recorded_availability(self):
        self.data['events'][0]['observed_at'] = '2025-01-01T08:06:00Z'
        with self.assertRaisesRegex(ValueError, '^observation_after_availability$'):
            self.join()

    def test_unsorted_join_matches_independent_candidate_scan(self):
        rng = random.Random(711)
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        def stamp(seconds):
            return (base+timedelta(seconds=seconds)).strftime('%Y-%m-%dT%H:%M:%SZ')
        events = []
        for index in range(40):
            available = 300*index
            events.append(dict(event_id='event-'+str(index), airport=['AAA', 'BBB'][index % 2],
                               observed_at=stamp(available-rng.randrange(1200)), available_at=stamp(available),
                               temperature_c=index, wind_knots=0, source_scope='historical_research'))
        rng.shuffle(events)
        queries = [dict(query_id='query-'+str(index), origin=rng.choice(['AAA', 'BBB', 'CCC']),
                        decision_at=stamp(rng.randrange(15000)), source_scope='historical_research') for index in range(300)]
        results = weather_features(queries, events, scope='historical_research', max_age_seconds=1800)
        for query, result in zip(queries, results):
            candidates = [event for event in events if event['airport'] == query['origin'] and event['available_at'] <= query['decision_at']]
            if not candidates:
                self.assertEqual(result['status'], 'unavailable')
                continue
            selected = max(candidates, key=lambda event: event['available_at'])
            age = int((timestamp(query['decision_at'])-timestamp(selected['observed_at'])).total_seconds())
            self.assertEqual(result['event_id'], selected['event_id'])
            self.assertEqual(result['status'], 'matched' if age <= 1800 else 'stale')
            self.assertEqual(result['temperature_c'], selected['temperature_c'] if age <= 1800 else None)

    def test_scope_is_explicit_and_cannot_mix_or_relabel_records(self):
        for scope in (None, 'observed', [], True):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                weather_features(**self.data, scope=scope)
        with self.assertRaisesRegex(ValueError, '^source_scope_mismatch$'):
            weather_features(**self.data, scope='historical_research')
        self.data['queries'][0]['source_scope'] = 'historical_research'
        with self.assertRaisesRegex(ValueError, '^source_scope_mismatch$'):
            self.join()

    def test_canonical_utc_only_including_invalid_dates_and_local_times(self):
        for value in ('2025-01-01T08:00:00', '2025-01-01T08:00:00+04:00', '2025-02-30T08:00:00Z', '2025-01-01T24:00:00Z', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                timestamp(value)

    def test_fields_measurements_and_ids_fail_closed(self):
        for field, value in [('temperature_c', float('nan')), ('temperature_c', float('inf')),
                             ('temperature_c', True), ('temperature_c', 10**400),
                             ('wind_knots', -1), ('wind_knots', '5'), ('airport', 'aaA'),
                             ('event_id', '../private')]:
            with self.subTest(field=field, value=str(value)[:20]):
                data = copy.deepcopy(self.data)
                data['events'][0][field] = value
                with self.assertRaises(ValueError):
                    weather_features(**data, scope='synthetic')
        self.data['queries'][0]['arrival_delay'] = 5
        with self.assertRaisesRegex(ValueError, '^invalid_query_fields$'):
            self.join()
        self.data = fixture()
        self.data['events'][0]['outcome'] = 'late'
        with self.assertRaisesRegex(ValueError, '^invalid_event_fields$'):
            self.join()

    def test_limits_generators_empty_inputs_and_duplicate_queries(self):
        with patch('pipelines.time_safe_features.MAX_EVENTS', 2), self.assertRaisesRegex(ValueError, '^event_limit_exceeded$'):
            self.join()
        with patch('pipelines.time_safe_features.MAX_QUERIES', 2), self.assertRaisesRegex(ValueError, '^query_limit_exceeded$'):
            self.join()
        for value in (0, 86401, True, 1.5):
            with self.assertRaises(ValueError):
                self.join(max_age_seconds=value)
        self.assertEqual(weather_features([], [], scope='synthetic'), [])
        self.assertTrue(all(r['status'] == 'unavailable' for r in weather_features(self.data['queries'], [], scope='synthetic')))
        self.assertEqual(weather_features(iter(self.data['queries']), iter(self.data['events']), scope='synthetic'), self.join())
        self.data['queries'].append(dict(self.data['queries'][0]))
        with self.assertRaisesRegex(ValueError, '^duplicate_query_identity$'):
            self.join()

    def test_synthetic_drill_is_reproducible_and_never_overwrites_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)/'case'
            report = verify(case)
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['checks']), 10)
            self.assertTrue(all(report['checks'].values()))
            self.assertEqual(report['counts'], dict(matched=4, stale=1, unavailable=2))
            for name, field in [('synthetic-input.json', 'fixture_sha256'), ('joined-results.json', 'results_sha256')]:
                self.assertEqual(hashlib.sha256((case/name).read_bytes()).hexdigest(), report[field])
            self.assertTrue(report['synthetic_only'])
            self.assertFalse(report['primary_database_accessed'])
            self.assertNotIn(str(temporary), json.dumps(report))
            with self.assertRaises(FileExistsError):
                verify(case)

    def test_drill_failure_keeps_fixed_private_report_and_refuses_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)/'failed'
            with patch('pipelines.verify_time_safe_features.weather_features', side_effect=ValueError('PRIVATE VALUE')):
                report = verify(case)
            self.assertFalse(report['passed'])
            self.assertEqual(report['error'], 'synthetic_time_join_check_failed')
            self.assertNotIn('PRIVATE VALUE', (case/'report.json').read_text(encoding='utf-8'))
            self.assertTrue((case/'synthetic-input.json').exists())
            with patch.dict(os.environ, {'AIN_AGENT_JOBS': '1'}), self.assertRaises(ValueError):
                verify(Path(temporary)/'refused')
            self.assertFalse((Path(temporary)/'refused').exists())

    def test_actual_cli_and_rejected_external_database_argument(self):
        command = [sys.executable, '-m', 'pipelines.verify_time_safe_features']
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        rejected = subprocess.run([*command, '--database', 'PRIVATE_PATH'], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(rejected.returncode, 2)


if __name__ == '__main__':
    unittest.main()
