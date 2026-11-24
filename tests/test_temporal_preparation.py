import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ml.temporal_preparation import prepare_splits
from ml.verify_temporal_preparation import BOUNDARIES,fixture,verify
from services.api.paths import ROOT


class TemporalPreparationTests(unittest.TestCase):
    def setUp(self):self.data=fixture()

    def prepare(self,**options):return prepare_splits(**self.data,**{**BOUNDARIES,**options},scope='synthetic')

    def test_chronology_maturity_counts_and_target_feature_separation(self):
        original=copy.deepcopy(self.data);result=self.prepare()
        self.assertEqual(result['counts'],dict(train=1,validation=1,test=1,excluded=4,input_features=7,input_labels=6))
        self.assertEqual([r['query_id'] for r in result['partitions']['train']],['train-ready'])
        self.assertEqual(set(result['partitions']['train'][0]['X']),{'origin','temperature_c','wind_knots'})
        self.assertEqual(self.data,original)
        self.assertFalse(result['training_performed'])

    def test_decision_boundary_is_half_open_and_label_boundary_inclusive(self):
        self.data['features']=[dict(self.data['features'][0],decision_at=BOUNDARIES['train_end'],observed_at='2025-06-30T23:30:00Z',available_at='2025-06-30T23:35:00Z')]
        self.data['labels']=[dict(self.data['labels'][0],label_available_at=BOUNDARIES['validation_end'])]
        result=self.prepare()
        self.assertEqual(result['counts']['validation'],1)
        self.assertEqual(result['counts']['train'],0)
        self.data['features'][0]['decision_at']=BOUNDARIES['test_end']
        self.data['features'][0].update(observed_at='2025-08-31T23:30:00Z',available_at='2025-08-31T23:35:00Z')
        self.data['labels'][0]['label_available_at']='2025-09-02T00:00:00Z'
        self.assertEqual(self.prepare()['excluded'][0]['reason'],'outside_experiment_window')

    def test_future_target_mutation_does_not_change_train_or_validation(self):
        first=self.prepare()
        for label in self.data['labels']:
            if label['query_id']=='test-ready':label['arrival_delay_minutes']=-500
        second=self.prepare()
        self.assertEqual(first['partitions']['train'],second['partitions']['train'])
        self.assertEqual(first['partitions']['validation'],second['partitions']['validation'])
        self.assertNotEqual(first['partitions']['test'],second['partitions']['test'])

    def test_rejects_post_decision_weather_even_when_status_claims_matched(self):
        self.data['features'][0]['available_at']='2025-06-15T09:01:00Z'
        with self.assertRaisesRegex(ValueError,'feature_not_available_at_decision'):self.prepare()

    def test_rejects_cached_age_or_measurement_and_target_fields(self):
        for mutate in (lambda r:r.update(age_seconds=0),lambda r:r.update(temperature_c=float('inf')),
                       lambda r:r.update(wind_knots=-1),lambda r:r.update(arrival_delay_minutes=5)):
            data=fixture();mutate(data['features'][0])
            with self.assertRaises(ValueError):prepare_splits(**data,**BOUNDARIES,scope='synthetic')

    def test_invalid_labels_ids_scopes_and_predecision_outcomes(self):
        for mutate in (lambda r:r.update(arrival_delay_minutes=True),lambda r:r.update(arrival_delay_minutes=float('nan')),
                       lambda r:r.update(source_scope='historical_research'),lambda r:r.update(label_available_at='2025-06-15T08:00:00Z')):
            data=fixture();mutate(data['labels'][0])
            with self.assertRaises(ValueError):prepare_splits(**data,**BOUNDARIES,scope='synthetic')
        self.data['labels'].append(dict(self.data['labels'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate_label_identity'):self.prepare()
        self.data=fixture();self.data['labels'][0]['query_id']='orphan'
        with self.assertRaisesRegex(ValueError,'orphan_label_identity'):self.prepare()

    def test_bounds_duplicate_queries_and_unsorted_inputs(self):
        expected=self.prepare()
        self.data['features'].reverse();self.data['labels'].reverse()
        self.assertEqual(self.prepare(),expected)
        self.data['features'].append(dict(self.data['features'][0]))
        with self.assertRaisesRegex(ValueError,'duplicate_feature_identity'):self.prepare()
        self.data=fixture()
        with patch('ml.temporal_preparation.MAX_ROWS',2),self.assertRaises(ValueError):self.prepare()
        with self.assertRaisesRegex(ValueError,'strict_chronological_boundaries'):self.prepare(train_end=BOUNDARIES['train_start'])
        with self.assertRaises(ValueError):self.prepare(train_start='2025-06-01T00:00:00')

    def test_stale_and_unavailable_weather_excluded_without_imputation(self):
        row=self.data['features'][0]
        row.update(status='stale',max_age_seconds=900,temperature_c=None,wind_knots=None)
        result=self.prepare()
        self.assertEqual(result['counts']['train'],0)
        self.assertEqual(next(r for r in result['excluded'] if r['query_id']=='train-ready')['reason'],'weather_not_matched')

    def test_demo_fingerprints_and_fresh_directory_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            case=Path(temporary)/'case';result=verify(case)
            self.assertTrue(result['passed']);self.assertEqual(len(result['checks']),10)
            self.assertFalse(result['frozen_experiments_accessed'])
            self.assertEqual(hashlib.sha256((case/'synthetic-input.json').read_bytes()).hexdigest(),result['fixture_sha256'])
            self.assertEqual(hashlib.sha256((case/'prepared-splits.json').read_bytes()).hexdigest(),result['preparation_sha256'])
            with self.assertRaises(FileExistsError):verify(case)

    def test_actual_cli_and_no_existing_database_argument(self):
        command=[sys.executable,'-m','ml.verify_temporal_preparation']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['passed'])
        bad=subprocess.run([*command,'--database','PRIVATE_PATH'],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(bad.returncode,2)


if __name__=='__main__':unittest.main()
