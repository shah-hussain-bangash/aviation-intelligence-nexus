import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from services.api.main import create_app
from services.api.paths import ROOT
from services.api.explanations import load_explanations,validate_report,REPORT,PROTOCOL_SHA256
from ml.permutation import permutation_results,scores,evaluate,PROTOCOL
from ml.prepare_dataset import FEATURES,TARGET


class CarrierModel:
    def fit(self,*args):
        raise AssertionError('Frozen model must never be fitted')

    def predict_proba(self,frame):
        # Hour/minute pairing must survive grouped shuffling.
        assert all(int(m)==int(h)+10 for h,m in zip(frame['scheduled_departure_hour'],frame['scheduled_departure_minute']))
        p=np.where(frame['carrier']=='AA',.8,.2)
        return np.column_stack([1-p,p])


class PermutationTests(unittest.TestCase):
    def test_frozen_group_shuffle_is_deterministic_preserves_pairs_and_input(self):
        frame=pd.DataFrame({key:['1']*100 for key in FEATURES})
        frame['carrier']=['AA','BB']*50;frame[TARGET]=[1,0]*50
        frame['scheduled_departure_hour']=[str(i%10) for i in range(100)]
        frame['scheduled_departure_minute']=[str(i%10+10) for i in range(100)]
        original=frame.copy(deep=True)
        groups={'carrier':['carrier'],'departure_time':['scheduled_departure_hour','scheduled_departure_minute']}
        first=permutation_results(CarrierModel(),frame,groups)
        self.assertEqual(first,permutation_results(CarrierModel(),frame,groups))
        self.assertGreater(first['groups'][0]['mean']['log_loss_increase'],0)
        self.assertEqual(first['groups'][1]['mean']['log_loss_increase'],0)
        pd.testing.assert_frame_equal(frame,original)

    def test_invalid_probabilities_and_unsafe_groups_fail(self):
        for values in [[float('nan'),.5],[1.1,.1],[[.3],[.2]]]:
            with self.assertRaises(ValueError):scores([0,1],values)
        frame=pd.DataFrame({TARGET:[0,1]})
        for groups in [{'target':[TARGET]},{'a':['carrier'],'b':['carrier']},{}]:
            with self.assertRaises(ValueError):permutation_results(None,frame,groups)

    def test_protocol_source_hash_and_output_guards_precede_deserialization(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);private=root/'.local';private.mkdir()
            public=root/'docs/reports/Delay_v2.json';public.parent.mkdir(parents=True)
            public.write_bytes((ROOT/'docs/reports/Delay_v2.json').read_bytes())
            model=private/'model';model.mkdir();(model/'model.joblib').write_bytes(b'wrong frozen model')
            out=private/'result'
            with patch('ml.permutation.ROOT',root),patch('ml.permutation.load_diagnostics'),patch('ml.permutation.joblib.load') as deserialize:
                with self.assertRaises(ValueError):evaluate(private,model,root/'outside')
                out.mkdir();(out/'receipt').write_text('preserve')
                with self.assertRaises(ValueError):evaluate(private,model,out)
                self.assertEqual((out/'receipt').read_text(),'preserve')
                with self.assertRaises(ValueError):evaluate(private,model,private/'new')
                self.assertFalse((private/'new').exists());deserialize.assert_not_called()
                invalid=private/'changed.json';invalid.write_text('{}')
                with patch('ml.permutation.PROTOCOL',invalid):
                    with self.assertRaises(ValueError):evaluate(private,model,private/'changed')

    def test_public_experiment_scope_and_protocol_are_fixed(self):
        r=load_explanations()
        self.assertEqual(r['sample_records'],10000)
        self.assertEqual(hashlib.sha256(PROTOCOL.read_text().encode()).hexdigest(),PROTOCOL_SHA256)
        self.assertEqual(max(r['groups'],key=lambda row:row['mean']['log_loss_increase'])['group'],'departure_time')
        self.assertAlmostEqual(r['baseline']['log_loss'],.46579173831009113)
        self.assertFalse(r['production_ready'])
        self.assertNotIn('record_key',r)

    def test_missing_changed_and_cross_platform_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(OSError):load_explanations(root)
            p=root/REPORT;p.parent.mkdir(parents=True)
            text=(ROOT/REPORT).read_text(encoding='utf-8');p.write_bytes(text.replace('\n','\r\n').encode())
            self.assertTrue(load_explanations(root)['integrity_verified'])
            p.write_text(text+' ',encoding='utf-8')
            with self.assertRaises(ValueError):load_explanations(root)

    def test_scope_arithmetic_and_negative_importance(self):
        original=load_explanations()
        for mutate in [lambda r:r['protocol'].__setitem__('period','2025-05'),
                       lambda r:r['groups'][0]['mean'].__setitem__('log_loss_increase',10),
                       lambda r:r['groups'][0].__setitem__('columns',['arrival_delay_minutes']),
                       lambda r:r['groups'][0]['repeats'][0].__setitem__('brier_increase',float('nan'))]:
            r=json.loads(json.dumps(original));mutate(r)
            with self.assertRaises(ValueError):validate_report(r)
        r=json.loads(json.dumps(original));row=r['groups'][0]
        for repeat in row['repeats']:repeat['log_loss_increase']=-.01
        row['mean']['log_loss_increase']=-.01;row['repeat_std']['log_loss_increase']=0
        self.assertIs(validate_report(r),r)

    def test_viewer_read_only_safe_failure_and_anonymous_denial(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app(Path(folder)/'fixture.sqlite3')
            with TestClient(app) as client:
                path='/api/v1/research/model-explanations'
                self.assertEqual(client.get(path).status_code,401)
                password='temporary-permutation-fixture-123';origin={'Origin':'http://127.0.0.1:8080'}
                app.state.auth_store.create_user('fixture-admin',password,'admin')
                app.state.auth_store.create_user('fixture-viewer',password,'viewer')
                login=client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':password},headers=origin)
                self.assertEqual(login.status_code,200)
                self.assertEqual(client.get(path).status_code,200)
                self.assertEqual(client.get(path).headers['cache-control'],'no-store')
                client.headers.update({**origin,'X-CSRF-Token':login.json()['csrf_token']})
                self.assertEqual(client.post(path,json={}).status_code,405)
                self.assertEqual(client.get(path+'/arbitrary').status_code,404)
                with patch('services.api.main.load_explanations',side_effect=ValueError('private path')):
                    result=client.get(path)
                self.assertEqual(result.status_code,503)
                self.assertNotIn('groups',result.json());self.assertNotIn('private path',result.text)
