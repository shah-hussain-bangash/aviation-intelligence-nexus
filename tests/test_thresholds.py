import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from ml.thresholds import threshold_counts,evaluate,PROTOCOL,PROTOCOL_SHA256
from ml.prepare_dataset import FEATURES,TARGET
from services.api.main import create_app
from services.api.paths import ROOT
from services.api.thresholds import load_thresholds,validate_report,REPORT


class FrozenThresholdModel:
    def fit(self,*args):raise AssertionError('Must not train')
    def predict_proba(self,frame):return np.array([[.8,.2],[.9,.1],[.2,.8],[.1,.9]])


class ThresholdTests(unittest.TestCase):
    def test_threshold_equality_endpoints_and_direct_confusion_counts(self):
        y=np.array([0,1,0,1]);p=np.array([0,.17,.5,1]);original=p.copy();rows=threshold_counts(y,p)
        self.assertEqual(len(rows),101);self.assertEqual(rows[0],{'threshold_percent':0,'tn':0,'fp':2,'fn':0,'tp':2})
        self.assertEqual(rows[17],{'threshold_percent':17,'tn':1,'fp':1,'fn':0,'tp':2});self.assertEqual(rows[100]['tp'],1)
        for row in rows:
            alert=p>=row['threshold_percent']/100
            self.assertEqual(row['fp'],int(np.count_nonzero(alert&(y==0))));self.assertEqual(row['fn'],int(np.count_nonzero(~alert&(y==1))))
        np.testing.assert_array_equal(original,p)

    def test_invalid_labels_probabilities_and_shapes_fail(self):
        for y,p in [([0,0],[.1,.2]),([0,2],[.1,.2]),([0,1],[.1]),([0,1],[[.1],[.2]]),([0,1],[np.nan,.2]),([0,1],[-.1,.2]),([0,1],[1.1,.2]),([0,1],['.1','.2'])]:
            with self.assertRaises(ValueError):threshold_counts(y,p)

    def test_protocol_output_and_artifact_guards_precede_unpickling(self):
        self.assertEqual(hashlib.sha256(PROTOCOL.read_text(encoding='utf-8').encode()).hexdigest(),PROTOCOL_SHA256)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);model=root/'.local/model';model.mkdir(parents=True);(model/'model.joblib').write_bytes(b'not the trusted artifact')
            target=root/'docs/reports/Delay_v2.json';target.parent.mkdir(parents=True);target.write_bytes((ROOT/'docs/reports/Delay_v2.json').read_bytes())
            with patch('ml.thresholds.ROOT',root),patch('ml.thresholds.load_diagnostics'),patch('ml.thresholds.joblib.load') as deserialize:
                for out in [root/'outside',model]:
                    with self.assertRaises(ValueError):evaluate(model,model,out)
                with self.assertRaises(ValueError):evaluate(model,model,root/'.local/new')
                invalid=root/'changed.json';invalid.write_text('{}',encoding='utf-8')
                with patch('ml.thresholds.PROTOCOL',invalid):
                    with self.assertRaises(ValueError):evaluate(model,model,root/'.local/changed')
                deserialize.assert_not_called();self.assertFalse((root/'.local/new').exists())

    def test_frozen_april_population_reproduced_and_invalid_aggregate_rejected(self):
        r=load_thresholds();self.assertEqual(r['records'],577730);self.assertEqual(r['positives'],113604);self.assertEqual(r['rows'][17]['fp'],243401);self.assertEqual(r['rows'][17]['fn'],31539)
        self.assertFalse(r['production_ready']);self.assertTrue(r['frozen_counts_reproduced'])
        for change in ['count','order','monotonic','scope','confirmation']:
            bad=copy.deepcopy(r)
            if change=='count':bad['rows'][40]['fp']+=1
            if change=='order':bad['rows'][40]['threshold_percent']=41
            if change=='monotonic':bad['rows'][40]=dict(bad['rows'][0],threshold_percent=40)
            if change=='scope':bad['period']='2025-05'
            if change=='confirmation':bad['frozen_counts_reproduced']=False
            with self.assertRaises(ValueError):validate_report(bad)

    def test_pinned_reports_missing_tampered_and_cross_platform_line_endings(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(OSError):load_thresholds(root)
            for name in [REPORT,'docs/reports/Delay_v2.json','ml/threshold_protocol.json']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_text(encoding='utf-8').replace('\n','\r\n').encode())
            self.assertEqual(load_thresholds(root)['records'],577730)
            (root/REPORT).write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):load_thresholds(root)

    def test_authenticated_fixed_read_and_sanitized_outage(self):
        with tempfile.TemporaryDirectory() as folder,TestClient(create_app(Path(folder)/'state.sqlite3')) as client:
            self.assertEqual(client.get('/api/v1/research/threshold-tradeoffs').status_code,401)
            for name,role in [('fixture-admin','admin'),('fixture-viewer','viewer'),('fixture-researcher','researcher')]:
                client.app.state.auth_store.create_user(name,'temporary-threshold-password',role)
                login=client.post('/api/v1/auth/login',json={'username':name,'password':'temporary-threshold-password'},headers={'Origin':'http://127.0.0.1:8080'});self.assertEqual(login.status_code,200)
                self.assertEqual(client.get('/api/v1/research/threshold-tradeoffs').json()['records'],577730)
            self.assertEqual(client.get('/api/v1/research/threshold-tradeoffs?period=2025-05').status_code,422)
            with patch('services.api.main.load_thresholds',side_effect=ValueError('PRIVATE LOCAL PATH')):
                response=client.get('/api/v1/research/threshold-tradeoffs');self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE',response.text)

    def test_offline_pipeline_reads_validation_only_and_preserves_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);model=root/'.local/input';model.mkdir(parents=True);artifact=model/'model.joblib';artifact.write_bytes(b'trusted local fixture')
            validation=model/'validation.csv';validation.write_bytes(b'fixture validation');hash_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            report={'artifact_sha256':hash_file(artifact),'dataset_hashes':{'validation':hash_file(validation)},'validation':{'model':{'records':4,'confusion_matrix_labels_0_1':[[1,1],[0,2]]}},'threshold':.17,'protocol':{'scope':'fixture'}}
            public=root/'docs/reports/Delay_v2.json';public.parent.mkdir(parents=True);public.write_text(json.dumps(report),encoding='utf-8')
            frame=pd.DataFrame({k:['fixture']*4 for k in FEATURES});frame[TARGET]=[0,0,1,1]
            with patch('ml.thresholds.ROOT',root),patch('ml.thresholds.load_diagnostics'),patch('ml.thresholds.load_split',return_value=frame) as split,patch('ml.thresholds.joblib.load',return_value=FrozenThresholdModel()):
                r=evaluate(model,model,root/'.local/result');self.assertTrue(r['frozen_counts_reproduced']);self.assertEqual(split.call_args.args[1],'validation');self.assertFalse((model/'test.csv').exists())
                self.assertEqual(r['rows'],evaluate(model,model,root/'.local/repeated')['rows'])
                with patch('ml.thresholds.load_split',side_effect=ValueError('Invalid frozen CSV')):
                    with self.assertRaises(ValueError):evaluate(model,model,root/'.local/failed')
                self.assertTrue((root/'.local/failed/started.json').is_file());self.assertFalse((root/'.local/failed/report.json').exists())
