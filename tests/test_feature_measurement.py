import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from pipelines.measure_feature_pipeline import SCALES, inputs, measure, recipe, records_hash, sample_agreement
from pipelines.decision_times import MAX_FLIGHTS, decision_queries
from pipelines.time_safe_features import MAX_EVENTS, MAX_QUERIES, weather_features
from services.api.paths import ROOT


class FeatureMeasurementTests(unittest.TestCase):
    def test_capacity_recipe_uses_current_admission_bounds(self):
        spec = recipe('capacity')
        self.assertEqual(spec['schedules'], min(MAX_FLIGHTS, MAX_QUERIES))
        self.assertEqual(spec['events'], MAX_EVENTS)
        self.assertEqual(SCALES['capacity'], (50_000, 200_000))
        for scale in ('unknown', None, []):
            with self.assertRaises(ValueError):
                recipe(scale)

    def test_recipe_generation_and_stream_fingerprints_are_reproducible(self):
        first = inputs(recipe('smoke'))
        second = inputs(recipe('smoke'))
        self.assertEqual(first, second)
        self.assertEqual((len(first[0]), len(first[2])), (500, 2000))
        self.assertTrue(all(row['source_scope'] == 'synthetic' for rows in (first[0], first[2]) for row in rows))
        self.assertEqual(records_hash(first[0]), records_hash(iter(second[0])))
        changed = [dict(first[0][0], flight_id='changed')]
        self.assertNotEqual(records_hash(changed), records_hash(first[0][:1]))

    def test_independent_scan_detects_wrong_selected_event_and_feature(self):
        schedules, mappings, events = inputs(recipe('smoke'))
        queries = decision_queries(schedules, mappings, scope='synthetic')['queries']
        features = weather_features(queries, events, scope='synthetic')
        self.assertEqual(sample_agreement(queries, events, features), (True, 8))
        self.assertEqual(sample_agreement([], events, []), (False, 0))
        features[0]['event_id'] = 'incorrect'
        self.assertFalse(sample_agreement(queries, events, features)[0])
        features = weather_features(queries, events, scope='synthetic')
        features[0]['temperature_c'] += 1
        self.assertFalse(sample_agreement(queries, events, features)[0])

    def test_measured_smoke_reconciles_and_retains_private_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)/'case'
            result = measure(case)
            self.assertTrue(result['passed'])
            self.assertEqual(len(result['checks']), 7)
            self.assertEqual(result['counts'], dict(schedules=500, events=2000, ready=500, excluded=0, matched=500))
            self.assertEqual(result['independent_sample_size'], 8)
            self.assertEqual(result['recipe_sha256'], hashlib.sha256((case/'recipe.json').read_bytes()).hexdigest())
            self.assertEqual(set(result['record_stream_sha256']), {'schedules', 'mappings', 'weather', 'decisions', 'queries', 'features'})
            self.assertEqual(set(result['phases']), {'generation', 'utc_decisions', 'weather_join', 'verification'})
            self.assertGreater(result['measurement']['python_traced_peak_bytes'], 0)
            self.assertGreaterEqual(result['measurement']['python_traced_peak_bytes'], result['measurement']['python_traced_current_bytes'])
            self.assertGreater(result['measurement']['wall_seconds'], 0)
            self.assertFalse(result['measurement']['whole_process_rss_measured'])
            self.assertTrue(result['measurement']['instrumentation_overhead_included'])
            self.assertFalse(result['primary_database_accessed'])
            self.assertNotIn(str(temporary), json.dumps(result))
            self.assertFalse(tracemalloc.is_tracing())
            self.assertEqual({p.name for p in case.iterdir()}, {'started.json', 'recipe.json', 'report.json'})
            before = (case/'report.json').read_bytes()
            with self.assertRaises(FileExistsError):
                measure(case)
            self.assertEqual((case/'report.json').read_bytes(), before)

    def test_failure_retains_recipe_and_stops_only_owned_tracker(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary)/'failed'
            with patch('pipelines.measure_feature_pipeline.weather_features', side_effect=ValueError('PRIVATE DETAIL')):
                report = measure(case)
            self.assertFalse(report['passed'])
            self.assertEqual(report['failed_stage'], 'weather_join')
            self.assertEqual(report['error'], 'synthetic_resource_measurement_failed')
            self.assertNotIn('PRIVATE DETAIL', (case/'report.json').read_text(encoding='utf-8'))
            self.assertTrue((case/'recipe.json').exists())
            self.assertFalse(tracemalloc.is_tracing())
            tracemalloc.start()
            try:
                with self.assertRaisesRegex(ValueError, '^independent_memory_tracker_required$'):
                    measure(Path(temporary)/'other-tracker')
                self.assertTrue(tracemalloc.is_tracing())
                self.assertFalse((Path(temporary)/'other-tracker').exists())
            finally:
                tracemalloc.stop()

    def test_jobs_and_invalid_scale_refused_before_case_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'refused'
            with patch.dict(os.environ, {'AIN_AGENT_JOBS': '1'}), self.assertRaises(ValueError):
                measure(path)
            self.assertFalse(path.exists())
            with self.assertRaises(ValueError):
                measure(path, scale='huge')
            self.assertFalse(path.exists())

    def test_actual_smoke_cli_and_rejected_database_argument(self):
        command = [sys.executable, '-m', 'pipelines.measure_feature_pipeline']
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        invalid = subprocess.run([*command, '--database', 'PRIVATE_PATH'], cwd=ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(invalid.returncode, 2)


if __name__ == '__main__':
    unittest.main()
