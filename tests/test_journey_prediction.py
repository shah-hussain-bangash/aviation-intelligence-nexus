"""Trusted-copy and real-inference contracts using an explicitly synthetic trained model."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits
from ml.train_v2 import build_model,PROTOCOL_PATH
from pipelines import journey_prediction as registered
from pipelines import verify_case_journey as journey
from services.api.paths import ROOT


class JourneyPredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model=build_model(15,json.loads(PROTOCOL_PATH.read_text(encoding='utf-8')))
        frame=pd.DataFrame({'carrier':['AA']*500,'origin':['JFK']*500,'destination':['LAX']*500,
            'scheduled_departure_hour':['9']*500,'scheduled_departure_minute':['0']*500,'day_of_week':['1']*500})
        with threadpool_limits(limits=2):model.fit(frame,[0,1]*250)
        stream=io.BytesIO();joblib.dump(model,stream);cls.model_bytes=stream.getvalue()

    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='prediction-journey-test-',dir=ROOT/'.local');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'.local/models/delay-v2';self.source.mkdir(parents=True)
        (self.source/'model.joblib').write_bytes(self.model_bytes);self.pin=hashlib.sha256(self.model_bytes).hexdigest()
        self.report={'artifact_sha256':self.pin,'model_version':'delay-v2',
            'release_assessment':{'research_gate_passed':True,'approved_for_operational_serving':False},
            'fixture':'SYNTHETIC TRAINED MODEL UNIT TEST; not heldout evaluation or production qualification'}
        self.public=self.root/'docs/reports/Delay_v2.json';self.public.parent.mkdir(parents=True)
        self.write_pair(self.report)

    def write_pair(self,value):
        (self.source/'report.json').write_text(json.dumps(value),encoding='utf-8');self.public.write_text(json.dumps(value),encoding='utf-8')

    def test_exact_registered_copy_never_deserializes_or_modifies_source(self):
        target=self.root/'.local/copy'
        with patch.object(registered,'ROOT',self.root),patch('joblib.load') as load:
            result=registered.copy_registered_model(target,self.pin);self.assertTrue(registered.source_preserved(result));load.assert_not_called()
        self.assertEqual((target/'model.joblib').read_bytes(),self.model_bytes)
        self.assertEqual(result['artifact_sha256'],self.pin);self.assertFalse(result['operational_serving_approved'])

    def test_wrong_hash_or_changed_source_cannot_be_copied(self):
        with patch.object(registered,'ROOT',self.root),patch('joblib.load') as load:
            with self.assertRaises(ValueError):registered.copy_registered_model(self.root/'.local/wrong','0'*64)
            (self.source/'model.joblib').write_bytes(self.model_bytes+b'changed')
            with self.assertRaises(ValueError):registered.copy_registered_model(self.root/'.local/changed',self.pin)
            load.assert_not_called()
        self.assertFalse((self.root/'.local/wrong').exists());self.assertFalse((self.root/'.local/changed').exists())

    def test_mismatched_or_unqualified_reports_are_rejected(self):
        with patch.object(registered,'ROOT',self.root):
            altered=copy.deepcopy(self.report);altered['fixture']='different public metadata';self.public.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):registered.copy_registered_model(self.root/'.local/mismatch',self.pin)
            for field,value in [('research_gate_passed',False),('approved_for_operational_serving',True)]:
                altered=copy.deepcopy(self.report);altered['release_assessment'][field]=value;self.write_pair(altered)
                with self.assertRaises(ValueError):registered.copy_registered_model(self.root/'.local/unqualified',self.pin)

    def test_output_must_be_fresh_private_directory(self):
        target=self.root/'.local/existing';target.mkdir();(target/'preserve.txt').write_text('preserve')
        with patch.object(registered,'ROOT',self.root):
            for path in [target,self.root/'outside',self.root/'.local'/'..'/'escape']:
                with self.assertRaises(ValueError):registered.copy_registered_model(path,self.pin)
        self.assertEqual((target/'preserve.txt').read_text(),'preserve');self.assertFalse((self.root/'outside').exists())

    def test_prediction_opt_in_and_pin_are_required_before_state_creation(self):
        target=self.root/'.local/unused'
        for options in [{'live_prediction':True},{'live_prediction':'true','model_sha256':self.pin},
                        {'model_sha256':self.pin},{'live_prediction':True,'model_sha256':'bad'}]:
            for function in [journey.exercise,journey.verify]:
                with self.assertRaises(ValueError):function(target,**options)
        self.assertFalse(target.exists())

    def test_actual_prediction_api_replay_reload_refusals_and_case_retention(self):
        target=self.root/'.local/run'
        with patch.object(registered,'ROOT',self.root),patch('joblib.load',wraps=joblib.load) as load:
            result=journey.exercise(target,live_prediction=True,model_sha256=self.pin)
        self.assertTrue(result['passed']);self.assertTrue(result['prediction_inference_executed']);self.assertFalse(result['prediction_fixture'])
        self.assertEqual(result['prediction_execution']['artifact_sha256'],self.pin)
        self.assertAlmostEqual(result['prediction_execution']['probability'],.5)
        self.assertGreaterEqual(load.call_count,2)
        for name in ['live_prediction_replay_same_saved_result','live_prediction_fresh_reload_parity',
                     'missing_prediction_artifact_denied','altered_prediction_artifact_denied',
                     'failed_predictions_not_saved','live_prediction_retained_exactly','registered_prediction_source_preserved']:
            self.assertTrue(result['checks'][name])
        self.assertFalse(result['worker_loop_executed']);self.assertFalse(result['retrieval_executed'])

    def test_failed_registered_copy_never_reports_completed_inference(self):
        def fail(directory,**kwargs):
            self.assertEqual(kwargs,{'live_prediction':True,'model_sha256':self.pin});directory.mkdir(parents=True)
            raise RuntimeError('journey_check_failed:registered_prediction_model_unavailable_or_mismatched')
        with patch.object(journey,'ROOT',self.root),patch.object(journey,'SOURCES',()),patch.object(journey,'exercise',side_effect=fail):
            report=journey.verify(self.root/'.local/failed',live_prediction=True,model_sha256=self.pin)
        self.assertFalse(report['passed']);self.assertTrue(report['live_prediction_requested'])
        self.assertFalse(report['prediction_fixture']);self.assertIsNone(report['prediction_inference_executed'])


if __name__=='__main__':unittest.main()
