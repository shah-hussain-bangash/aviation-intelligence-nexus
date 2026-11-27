"""Synthetic rows/classifier exercise the real evaluator; no actual June rows are opened."""
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from ml import evaluate_june as evaluation,admit_evaluation_archive as admission,register_evaluation as registration
from ml.june_metrics import uncertainty,summarize
from ml.prepare_dataset import FEATURES
from pipelines import journey_prediction as registered
from services.api.paths import ROOT

FIELDS=['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime','DepDelay','ArrDelay','Cancelled','Diverted']


class JuneEvaluationTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix='june-evaluation-test-',dir=ROOT/'.local')
        self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        source=self.root/'.local/models/delay-v2';source.mkdir(parents=True)
        model=DummyClassifier(strategy='prior').fit(pd.DataFrame([['AA','JFK','LAX','1','6','1','7','9','0']]*10,columns=FEATURES),[0,1]*5)
        stream=io.BytesIO();joblib.dump(model,stream);raw=stream.getvalue();self.model_pin=hashlib.sha256(raw).hexdigest()
        (source/'model.joblib').write_bytes(raw)
        self.report=json.loads((ROOT/'docs/reports/Delay_v2.json').read_text(encoding='utf-8'))
        self.report.update(artifact_sha256=self.model_pin,fixture='SYNTHETIC JUNE UNIT CLASSIFIER AND ROWS')
        public=self.root/'docs/reports/Delay_v2.json';public.parent.mkdir(parents=True)
        raw=json.dumps(self.report).encode();public.write_bytes(raw);(source/'report.json').write_bytes(raw)
        plan=self.root/'ml/june_evaluation_plan.json';plan.parent.mkdir();plan.write_bytes((ROOT/'ml/june_evaluation_plan.json').read_bytes())
        for module in (evaluation,admission,registration,registered):self.enterContext(patch.object(module,'ROOT',self.root))
        registration.prepare(self.root/'.local/plan',self.model_pin)
        self.record=self.root/'.local/plan/registration.json';self.record_pin=hashlib.sha256(self.record.read_bytes()).hexdigest()

    def rows(self):
        rows=[[f'2025-06-{i//4+1:02d}','AA',str(i+1),'JFK','LAX','0900','3',str(20 if i%2 else 0),'0','0'] for i in range(12)]
        rows[9][7]='';rows[9][8]='1';rows[10][7]='';rows[10][9]='1';rows[11][7]=''
        return rows+[rows[0].copy()]

    def admit(self,rows=None,name='admitted',header=None):
        text=io.StringIO(newline='');writer=csv.writer(text);writer.writerow(header or FIELDS);writer.writerows(self.rows() if rows is None else rows)
        archive=self.root/'.local'/f'{name}.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as output:output.writestr(admission.CSV_NAME,text.getvalue())
        pin=hashlib.sha256(archive.read_bytes()).hexdigest();target=self.root/'.local'/name
        admission.stage(self.record,self.record_pin,archive,pin,target)
        path=target/'admission.json';return path,hashlib.sha256(path.read_bytes()).hexdigest()

    def run_eval(self,inputs,output='result',trusted=True):
        return evaluation.evaluate(*inputs,self.root/'.local'/output,trusted_registered_model=trusted)

    def test_real_evaluator_claims_before_opening_rows_and_never_refits(self):
        inputs=self.admit();original_open=zipfile.ZipFile.open;original_load=joblib.load
        def opened(*args,**kwargs):
            self.assertTrue((self.root/'.local/evaluation-attempts/2025-06.json').is_file())
            return original_open(*args,**kwargs)
        def loaded(*args,**kwargs):
            self.assertTrue((self.root/'.local/evaluation-attempts/2025-06.json').is_file())
            return original_load(*args,**kwargs)
        with (patch.object(zipfile.ZipFile,'open',new=opened),patch('joblib.load',side_effect=loaded) as load,
              patch.object(DummyClassifier,'fit',side_effect=AssertionError('Evaluation must never refit'))):
            result=self.run_eval(inputs)
        self.assertEqual(result['state'],'evaluated',result);self.assertEqual(load.call_count,1)
        self.assertEqual(result['data_counts'],dict(rows_read=13,unique_identities=12,identical_duplicates=1,
          eligible_records=9,excluded_cancelled=1,excluded_diverted=1,excluded_missing_target=1))
        self.assertTrue(result['csv_crc_verified']);self.assertTrue(result['bootstrap_executed'])
        self.assertEqual(result['evaluation']['frozen_threshold'],self.report['threshold'])
        self.assertEqual(result['evaluation']['constant_probability'],self.report['training_delay_prevalence'])
        self.assertFalse(result['evaluation']['research_comparison']['passed']);self.assertFalse(result['model_refitted'])
        self.assertFalse(result['production_ready']);self.assertFalse(result['global_single_use_enforced'])

    def test_alternate_output_and_cloned_admission_cannot_repeat_same_month(self):
        inputs=self.admit();self.assertEqual(self.run_eval(inputs)['state'],'evaluated')
        clone=self.root/'.local/clone';shutil.copytree(inputs[0].parent,clone)
        with patch.object(zipfile.ZipFile,'open') as opened:
            result=self.run_eval((clone/'admission.json',inputs[1]),'different-output')
        opened.assert_not_called();self.assertEqual(result['state'],'refused');self.assertFalse(result['attempt_consumed'])
        self.assertFalse((self.root/'.local/different-output').exists())

    def test_concurrent_attempts_claim_only_once(self):
        inputs=self.admit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.run_eval,inputs,f'result-{i}') for i in range(2)]
            results=[future.result() for future in futures]
        self.assertEqual(sorted(r['state'] for r in results),['evaluated','refused'])

    def test_missing_trust_or_changed_archive_refuses_before_claim(self):
        inputs=self.admit();result=self.run_eval(inputs,trusted=False)
        self.assertEqual(result['state'],'refused');self.assertFalse(result['attempt_consumed'])
        archive=inputs[0].parent/'archive.zip';archive.write_bytes(archive.read_bytes()+b'changed')
        result=self.run_eval(inputs);self.assertEqual(result['state'],'refused')
        self.assertFalse((self.root/'.local/evaluation-attempts/2025-06.json').exists())

    def test_wrong_row_month_consumes_claim_and_withholds_model_execution(self):
        rows=self.rows();rows[0][0]='2025-05-01';inputs=self.admit(rows)
        with patch('joblib.load') as load:result=self.run_eval(inputs)
        load.assert_not_called();self.assertEqual(result['state'],'failed');self.assertTrue(result['attempt_consumed'])
        self.assertEqual(result['failure_code'],'candidate_record_invalid')
        self.assertFalse(result['rows_validated']);self.assertEqual(self.run_eval(inputs,'retry')['state'],'refused')

    def test_conflicting_identity_or_bad_schema_is_not_silently_dropped(self):
        rows=self.rows();rows[-1][7]='99';inputs=self.admit(rows)
        result=self.run_eval(inputs);self.assertEqual(result['state'],'failed');self.assertFalse(result['metrics_computed'])

    def test_bad_schema_consumes_claim_before_reading_targets(self):
        inputs=self.admit(rows=[['SYNTHETIC']],header=['unsupported'])
        with patch('joblib.load') as load:result=self.run_eval(inputs)
        load.assert_not_called();self.assertEqual(result['state'],'failed');self.assertTrue(result['attempt_consumed'])
        self.assertEqual(result['data_counts']['rows_read'],0)
        self.assertEqual(result['failure_code'],'csv_schema_invalid')

    def test_claim_write_failure_remains_consumed_and_never_opens_rows(self):
        inputs=self.admit()
        with patch('ml.evaluate_june.os.fsync',side_effect=OSError('synthetic failure')),patch.object(zipfile.ZipFile,'open') as opened:
            result=self.run_eval(inputs)
        opened.assert_not_called();self.assertTrue(result['attempt_consumed']);self.assertEqual(result['state'],'failed')
        self.assertTrue((self.root/'.local/evaluation-attempts/2025-06.json').exists())

    def test_model_receives_only_registered_schedule_features(self):
        inputs=self.admit();original=DummyClassifier.predict_proba
        def predict(model,frame):
            self.assertEqual(list(frame.columns),FEATURES)
            self.assertNotIn('arrival_delay_minutes',frame.columns);return original(model,frame)
        with patch.object(DummyClassifier,'predict_proba',new=predict):result=self.run_eval(inputs)
        self.assertEqual(result['state'],'evaluated')

    def test_day_bootstrap_is_seeded_and_zero_for_equal_probabilities(self):
        plan=json.loads((self.root/'ml/june_evaluation_plan.json').read_bytes())['uncertainty_plan']
        y=np.array([0,1,0,1]);p=np.full(4,.25);dates=['2025-06-01']*3+['2025-06-02']
        first=uncertainty(y,p,.25,dates,plan);self.assertEqual(first,uncertainty(y,p,.25,dates,plan))
        for row in first['statistics'].values():self.assertEqual(row,{'point_estimate':0.0,'lower':0.0,'upper':0.0})

    def test_bootstrap_point_is_flight_weighted_not_mean_of_daily_means(self):
        plan=json.loads((self.root/'ml/june_evaluation_plan.json').read_bytes())['uncertainty_plan']
        y=np.array([0,0,0,1]);p=np.array([.1,.1,.1,.9]);dates=['2025-06-01']*3+['2025-06-02']
        result=uncertainty(y,p,.2,dates,plan)
        expected=float(np.mean((p-y)**2-(.2-y)**2))
        self.assertAlmostEqual(result['statistics']['mean_brier_difference_model_minus_prior']['point_estimate'],expected)

    def test_predeclared_cohort_minimum_controls_metrics_without_model_selection(self):
        frame=pd.DataFrame({'carrier':['AA']*500+['BB']*2,'origin':['JFK']*502})
        y=np.array([0,1]*251);p=np.full(502,.5);r=json.loads(self.record.read_bytes())
        result=summarize(frame,y,p,['2025-06-01']*250+['2025-06-02']*252,r)
        rows=result['cohort_diagnostics']['carrier'];self.assertEqual(rows[0]['state'],'reported')
        self.assertEqual(rows[1]['state'],'insufficient_for_predeclared_cohort_metrics')
