from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from threadpoolctl import threadpool_limits
from ml.duration import FEATURES,TARGET,read_frame,metrics,evaluate_frame,build_model,fit_evaluate,load_protocol,run,digest
from services.api.main import create_app
from services.api.paths import ROOT
from services.api.duration import load_duration,validate_report,REPORT


class MeanDurationModel:
    def fit(self,x,y):self.constant=float(np.mean(y));return self
    def predict(self,x):return np.full(len(x),self.constant)


def frame(month,values):
    return pd.DataFrame({'record_key':[f'{month}-{i}' for i in range(len(values))],'flight_date':[f'2025-{month}-15']*len(values),
        'carrier':['AA']*len(values),'origin':['JFK']*len(values),'destination':['LAX']*len(values),'scheduled_departure_hour':[9]*len(values),
        'scheduled_departure_minute':[0]*len(values),'day_of_week':[3]*len(values),TARGET:values})


class DurationTests(unittest.TestCase):
    def test_fixed_protocol_no_leaky_features_and_unknown_schedule_vocabulary(self):
        p=load_protocol();self.assertFalse(p['model']['early_stopping']);self.assertEqual(p['features'],FEATURES)
        p['model'].update(max_iter=2,min_samples_leaf=2);training=frame('01',[0,10,0,30]*10)
        model=build_model(p)
        with threadpool_limits(limits=2):
            model.fit(training[FEATURES],training[TARGET]);unknown=training[FEATURES].copy();unknown['carrier']='ZZ';prediction=model.predict(unknown)
        self.assertTrue(np.isfinite(prediction).all());p['features']=[*FEATURES,'arrival_delay_minutes']
        with self.assertRaises(ValueError):build_model(p)

    def test_readonly_sql_target_exclusions_midnight_and_temporal_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.sqlite3'
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('CREATE TABLE flights(source_record_id TEXT,flight_date TEXT,carrier TEXT,origin TEXT,destination TEXT,scheduled_departure TEXT,arrival_delay_minutes REAL,source TEXT,cancelled INT,diverted INT)')
                base=['key','2025-01-15','AA','JFK','LAX','2400',-5,'BTS_REPORTING_CARRIER',0,0]
                rows=[base,[*base[:6],20,*base[7:]]];rows[1][0]='late'
                for key,position,value in [('cancelled',8,1),('diverted',9,1),('missing',6,None),('future',1,'2025-05-15'),('foreign',7,'OTHER')]:
                    row=list(base);row[0]=key;row[position]=value;rows.append(row)
                db.executemany('INSERT INTO flights VALUES(?,?,?,?,?,?,?,?,?,?)',rows)
            before=digest(path)
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
                db.execute('PRAGMA query_only=ON');f=read_frame(db,['2025-01-01','2025-04-01'],'BTS_REPORTING_CARRIER')
            self.assertEqual(f[TARGET].tolist(),[0,20]);self.assertEqual(f.scheduled_departure_hour.tolist(),[24,24]);self.assertNotIn('arrival_delay_minutes',f);self.assertEqual(before,digest(path))

    def test_regression_arithmetic_zero_targets_negative_r2_and_invalid_values(self):
        m=metrics([0,10],[5,5]);self.assertEqual(m['mae'],5);self.assertEqual(m['rmse'],5);self.assertEqual(m['r2'],0);self.assertEqual(m['mean_error'],0)
        self.assertIsNone(metrics([0,0],[1,1])['r2']);self.assertLess(metrics([0,10],[100,100])['r2'],0)
        for y,p in [([],[]),([0,1],[0]),([0,np.nan],[0,1]),([0,1],[-1,0]),([-1,0],[0,1]),([0,1],[0,np.inf])]:
            with self.assertRaises(ValueError):metrics(y,p)
        model=MeanDurationModel().fit(None,[0,10]);r=evaluate_frame(model,frame('04',[0,10,100]),{'mean':5,'median':0});self.assertEqual(sum(r['residual_histogram']['counts']),3);self.assertEqual(r['observed_60_plus']['records'],1);self.assertEqual(r['observed_60_plus']['model_mean_error'],-95)

    def test_artifact_and_april_are_frozen_before_test_rows_and_not_refitted(self):
        p=load_protocol();p['expected_records']={k:4 for k in p['expected_records']};events=[]
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            def obtain(db,bounds,source):
                key=next(k for k,v in p['periods'].items() if v==bounds);events.append(key)
                if key=='test':
                    frozen=json.loads((out/'freeze.json').read_text(encoding='utf-8'));self.assertFalse(frozen['may_rows_read']);self.assertEqual(set(frozen['datasets']),{'train','validation'});self.assertEqual(frozen['artifact_sha256'],digest(out/'model.joblib'))
                return frame('05' if key=='test' else '04' if key=='validation' else '01',[0,0,10,1000] if key=='test' else [0,0,10,20])
            with patch('ml.duration.read_frame',side_effect=obtain),patch('ml.duration.build_model',return_value=MeanDurationModel()) as build:
                result=fit_evaluate(None,p,out)
            self.assertEqual(events,['train','validation','test']);self.assertEqual(build.call_count,1);self.assertEqual(result['baselines']['mean'],7.5);self.assertFalse(result['research_check']['passed']);self.assertFalse(result['production_ready'])

    def test_output_missing_database_and_protocol_guards_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);existing=root/'.local/exists';existing.mkdir(parents=True);(existing/'receipt').write_text('preserve',encoding='utf-8')
            with patch('ml.duration.ROOT',root):
                for out in [root/'outside',existing]:
                    with self.assertRaises(ValueError):run(root/'missing.sqlite3',out)
                with self.assertRaises(sqlite3.Error):run(root/'missing.sqlite3',root/'.local/new')
                self.assertFalse((root/'missing.sqlite3').exists());self.assertFalse((root/'.local/new').exists())
            self.assertEqual((existing/'receipt').read_text(encoding='utf-8'),'preserve');invalid=root/'changed.json';invalid.write_text('{}',encoding='utf-8')
            with patch('ml.duration.PROTOCOL',invalid),self.assertRaises(ValueError):load_protocol()

    def test_real_aggregate_preserves_failed_check_and_rejects_false_success(self):
        r=load_duration();self.assertFalse(r['research_check']['passed']);self.assertEqual(r['datasets']['train']['records'],1611046);self.assertAlmostEqual(r['test']['model']['rmse'],55.6693189635)
        for case in ['pass','metric','histogram','tail','identity']:
            bad=copy.deepcopy(r)
            if case=='pass':bad['research_check']['passed']=True
            if case=='metric':bad['test']['model']['mae']=0
            if case=='histogram':bad['validation']['residual_histogram']['counts'][0]+=1
            if case=='tail':bad['test']['observed_60_plus']['model_mae']=-1
            if case=='identity':bad['datasets']['test']['records']=1
            with self.assertRaises(ValueError):validate_report(bad)

    def test_missing_tampered_evidence_and_cross_platform_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(OSError):load_duration(root)
            for name in [REPORT,'ml/duration_protocol.json']:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_text(encoding='utf-8').replace('\n','\r\n').encode())
            self.assertFalse(load_duration(root)['research_check']['passed']);(root/REPORT).write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):load_duration(root)

    def test_authenticated_read_only_api_and_sanitized_failure(self):
        with tempfile.TemporaryDirectory() as folder,TestClient(create_app(Path(folder)/'state.sqlite3')) as client:
            path='/api/v1/research/duration-evaluation';self.assertEqual(client.get(path).status_code,401)
            for name,role in [('fixture-admin','admin'),('fixture-viewer','viewer'),('fixture-researcher','researcher')]:
                client.app.state.auth_store.create_user(name,'temporary-duration-password',role);login=client.post('/api/v1/auth/login',json={'username':name,'password':'temporary-duration-password'},headers={'Origin':'http://127.0.0.1:8080'});self.assertEqual(login.status_code,200)
                response=client.get(path);self.assertEqual(response.status_code,200);self.assertFalse(response.json()['research_check']['passed'])
            self.assertEqual(client.get(path+'?target=departure_delay').status_code,422)
            with patch('services.api.main.load_duration',side_effect=ValueError('PRIVATE LOCAL PATH')):
                response=client.get(path);self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE',response.text)
