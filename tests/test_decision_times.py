import copy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import tzdata

from pipelines.decision_times import decision_queries, packaged_zone
from pipelines.verify_decision_times import fixture, verify
from pipelines.time_safe_features import weather_features
from services.api.paths import ROOT


class DecisionTimeTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def convert(self, **options):
        return decision_queries(self.data['flights'], self.data['mappings'], scope='synthetic', **options)

    def test_schedule_to_weather_trace_and_exclusion_accounting(self):
        before = copy.deepcopy(self.data)
        result = self.convert(lead_minutes=30)
        self.assertEqual(len(result['decisions']), 7)
        self.assertEqual(len(result['queries']), 3)
        rows = {r['flight_id']: r for r in result['decisions']}
        self.assertEqual(rows['dubai-illustration']['scheduled_departure_utc'], '2025-01-01T06:00:00Z')
        self.assertEqual(rows['midnight']['local_departure'], '2025-01-02T00:00:00')
        self.assertEqual(rows['midnight']['decision_at'], '2025-01-02T04:30:00Z')
        self.assertEqual(rows['spring-gap']['status'], 'excluded_nonexistent_local_time')
        self.assertEqual(rows['fall-fold']['status'], 'excluded_ambiguous_local_time')
        self.assertEqual(rows['unknown-airport']['status'], 'excluded_missing_mapping')
        self.assertEqual(rows['expired-reference']['status'], 'excluded_mapping_period')
        self.assertIsNone(rows['fall-fold']['decision_at'])
        features = weather_features(result['queries'], self.data['events'], scope='synthetic')
        self.assertEqual([r['event_id'] for r in features], ['available-dubai', 'available-midnight', 'available-spring'])
        self.assertTrue(all(r['source_scope'] == 'synthetic' for r in features))
        self.assertEqual(self.data, before)

    def test_decision_lead_is_subtracted_in_utc_across_dst(self):
        self.data['flights'] = [dict(self.data['flights'][4]), dict(self.data['flights'][3], flight_id='after-fall', scheduled_departure='0230')]
        result = self.convert(lead_minutes=120)
        self.assertEqual([r['decision_at'] for r in result['queries']], ['2025-03-09T05:30:00Z', '2025-11-02T05:30:00Z'])

    def test_midnight_rollover_mapping_validity_and_year_boundary(self):
        self.data['flights'] = [dict(self.data['flights'][1])]
        self.data['mappings']['BBB']['valid_until'] = '2025-01-02'
        self.assertEqual(self.convert()['decisions'][0]['status'], 'excluded_mapping_period')
        self.data['mappings']['BBB']['valid_until'] = '2026-01-02'
        self.data['flights'][0]['flight_date'] = '2025-12-31'
        result = self.convert(lead_minutes=0)['decisions'][0]
        self.assertEqual(result['scheduled_departure_utc'], '2026-01-01T05:00:00Z')

    def test_mapping_start_inclusive_end_exclusive_and_no_fallback(self):
        self.data['flights'] = [dict(self.data['flights'][0])]
        mapping = self.data['mappings']['AAA']
        mapping['valid_from'] = '2025-01-02'
        self.assertEqual(self.convert()['decisions'][0]['status'], 'excluded_mapping_period')
        mapping['valid_from'] = '2025-01-01'
        self.assertEqual(self.convert()['decisions'][0]['status'], 'ready')
        self.data['mappings'] = {}
        self.assertEqual(self.convert()['queries'], [])

    def test_pinned_package_bytes_and_reference_provenance(self):
        result = self.convert()['decisions'][0]
        data = files('tzdata.zoneinfo').joinpath('Asia', 'Dubai').read_bytes()
        self.assertEqual(result['timezone_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(result['tzdata_version'], tzdata.__version__)
        self.assertEqual(result['mapping_reference'], 'synthetic-dubai-reference')
        self.assertEqual(result['mapping_valid_from'], '2025-01-01')
        # Loading from bytes does not depend on the host's ZoneInfo search path.
        with patch('zoneinfo.TZPATH', ()):
            self.assertEqual(self.convert()['decisions'][0], result)

    def test_invalid_timezone_resources_and_mapping_fields_are_refused(self):
        for name in ('../private', '/etc/passwd', 'America//New_York', 'Missing/Zone', [], 'Asia/Dubai/../../x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                packaged_zone(name)
        for mutate in (lambda m: m.update(timezone=[]), lambda m: m.update(reference_id='../x'),
                       lambda m: m.update(valid_until='2024-01-01'), lambda m: m.update(unapproved='extra')):
            data = copy.deepcopy(self.data)
            mutate(data['mappings']['AAA'])
            with self.assertRaises(ValueError):
                decision_queries(data['flights'], data['mappings'], scope='synthetic')

    def test_invalid_dates_times_ids_and_outcome_fields_fail(self):
        for field, value in [('flight_date', '2025-02-30'), ('flight_date', '20250101'),
                             ('scheduled_departure', '2460'), ('scheduled_departure', '24:00'),
                             ('scheduled_departure', '090'), ('scheduled_departure', 900),
                             ('flight_id', '../private'), ('origin', 'aaa')]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.data)
                data['flights'][0][field] = value
                with self.assertRaises(ValueError):
                    decision_queries(data['flights'], data['mappings'], scope='synthetic')
        self.data['flights'][0]['arrival_delay'] = 5
        with self.assertRaisesRegex(ValueError, '^invalid_schedule_fields$'):
            self.convert()
        self.data = fixture()
        self.data['flights'][0].update(flight_date='9999-12-31', scheduled_departure='2400')
        with self.assertRaises(ValueError):
            self.convert()

    def test_scope_limits_duplicates_and_lead_policy(self):
        for lead in (-1, 1441, True, 1.5):
            with self.assertRaises(ValueError):
                self.convert(lead_minutes=lead)
        for scope in (None, [], 'live'):
            with self.assertRaises(ValueError):
                decision_queries([], {}, scope=scope)
        self.assertEqual(decision_queries([], {}, scope='synthetic'), dict(queries=[], decisions=[]))
        with patch('pipelines.decision_times.MAX_FLIGHTS', 2), self.assertRaisesRegex(ValueError, '^flight_limit_exceeded$'):
            self.convert()
        with patch('pipelines.decision_times.MAX_MAPPINGS', 2), self.assertRaises(ValueError):
            self.convert()
        self.data['flights'].append(dict(self.data['flights'][0]))
        with self.assertRaisesRegex(ValueError, '^duplicate_flight_identity$'):
            self.convert()
        self.data = fixture()
        self.data['mappings']['AAA']['source_scope'] = 'historical_research'
        with self.assertRaisesRegex(ValueError, '^source_scope_mismatch$'):
            self.convert()
        self.data = fixture()
        self.data['flights'][0]['source_scope'] = 'historical_research'
        with self.assertRaisesRegex(ValueError, '^source_scope_mismatch$'):
            self.convert()

    def test_drill_retains_hashed_synthetic_trace_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)/'case'
            report = verify(case)
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['checks']), 13)
            self.assertEqual(report['counts'], dict(schedules=7, ready=3, excluded=4, weather_matched=3))
            for name, field in [('synthetic-input.json', 'fixture_sha256'), ('joined-results.json', 'results_sha256')]:
                self.assertEqual(hashlib.sha256((case/name).read_bytes()).hexdigest(), report[field])
            result = json.loads((case/'joined-results.json').read_text(encoding='utf-8'))
            self.assertEqual(len(result['decisions']), 7)
            self.assertEqual(len(result['features']), 3)
            self.assertFalse(report['primary_database_accessed'])
            self.assertNotIn(str(temporary), json.dumps(report))
            with self.assertRaises(FileExistsError):
                verify(case)

    def test_failed_drill_retains_inputs_and_redacts_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)/'failed'
            with patch('pipelines.verify_decision_times.decision_queries', side_effect=ValueError('PRIVATE ERROR')):
                report = verify(case)
            self.assertFalse(report['passed'])
            self.assertEqual(report['error'], 'synthetic_decision_time_check_failed')
            self.assertTrue((case/'synthetic-input.json').exists())
            self.assertNotIn('PRIVATE ERROR', (case/'report.json').read_text(encoding='utf-8'))
            with patch.dict(os.environ, {'AIN_AGENT_JOBS': '1'}), self.assertRaises(ValueError):
                verify(Path(temporary)/'refused')
            self.assertFalse((Path(temporary)/'refused').exists())

    def test_actual_cli_passes_and_existing_database_argument_is_refused(self):
        command = [sys.executable, '-m', 'pipelines.verify_decision_times']
        positive = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(positive.returncode, 0, positive.stderr)
        self.assertTrue(json.loads(positive.stdout)['passed'])
        negative = subprocess.run([*command, '--database', 'PRIVATE_PATH'], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(negative.returncode, 2)


if __name__ == '__main__':
    unittest.main()
