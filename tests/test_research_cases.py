from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
from tests.auth_helpers import authenticated_client
from services.api.main import create_app
from services.api.history import ResearchHistory
from services.api.research_cases import ResearchCaseService, ChangeCase, CaseConflict

BASE='/api/v1/research/cases'


class ResearchCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.database=self.root/'auth.sqlite3'; self.sidecar=self.root/'cases.sqlite3'
        self.service=ResearchCaseService(self.database,self.sidecar)
        self.app=create_app(self.database,research_cases=self.service)

    def seed(self, username='test-admin'):
        with closing(sqlite3.connect(self.database)) as db:
            identity=db.execute('SELECT id,username,role FROM auth_users WHERE username=?',(username,)).fetchone()
        self.user=dict(zip(('id','username','role'),identity))
        result={'model_version':'delay-v2','artifact_sha256':'a'*64,'research_only':True,'operational_serving_approved':False,
                'arrival_delay_15_probability':0.2,'limitations':['SYNTHETIC UNIT FIXTURE; no actual inference']}
        return ResearchHistory(self.database).save(str(uuid4()),{'scope':'synthetic fixture'},result,self.user)

    def body(self, client):
        source=self.seed()
        rows=client.get('/api/v1/research/case-sources').json()['sources']
        self.assertEqual(rows[0]['run_id'],source['run_id'])
        return {'source_run_id':source['run_id'],'source_sha256':rows[0]['source_sha256'],'title':'SYNTHETIC research investigation'}

    def open_case(self, client, body=None, key=None):
        return client.post(BASE,json=body or self.body(client),headers={'Idempotency-Key':key or str(uuid4())})

    def test_persisted_prediction_note_outcome_journey_and_snapshot_after_source_deleted(self):
        with authenticated_client(self.app) as client:
            opened=self.open_case(client); self.assertEqual(opened.status_code,200,opened.text)
            case=opened.json(); self.assertFalse(case['operational_approval'])
            path=BASE+'/'+case['id']
            note=client.post(path+'/events',json={'expected_version':1,'action':'note','note':'Investigated fixture evidence'})
            self.assertEqual(note.json()['version'],2)
            closed=client.post(path+'/events',json={'expected_version':2,'action':'close','note':'Research follow-up documented; no airline action'})
            self.assertEqual(closed.json()['status'],'closed'); self.assertEqual(len(closed.json()['events']),3)
            with closing(sqlite3.connect(self.database)) as db,db: db.execute('DELETE FROM research_runs')
            self.assertEqual(client.get(path).json()['source_sha256'],case['source_sha256'])
        service=ResearchCaseService(self.database,self.sidecar)
        with authenticated_client(create_app(self.database,research_cases=service)) as client:
            loaded=client.get(path).json(); self.assertEqual(loaded['outcome'],closed.json()['outcome'])
            self.assertEqual(loaded['version'],3); self.assertEqual(loaded['source_snapshot'],case['source_snapshot'])

    def test_create_replay_conflict_and_stale_or_closed_changes(self):
        with authenticated_client(self.app) as client:
            body=self.body(client); key=str(uuid4()); first=self.open_case(client,body,key).json()
            replay=self.open_case(client,body,key).json(); self.assertTrue(replay['replayed']); self.assertEqual(first['id'],replay['id'])
            self.assertEqual(self.open_case(client,{**body,'title':'different'},key).status_code,409)
            path=BASE+'/'+first['id']+'/events'
            self.assertEqual(client.post(path,json={'expected_version':2,'action':'note','note':'stale'}).status_code,409)
            self.assertEqual(client.post(path,json={'expected_version':1,'action':'close','note':'closed research fixture'}).status_code,200)
            self.assertEqual(client.post(path,json={'expected_version':2,'action':'note','note':'after close'}).status_code,409)
            self.assertEqual(len(client.get(BASE+'/'+first['id']).json()['events']),2)

    def test_owner_isolation_and_viewer_denial(self):
        with authenticated_client(self.app) as client:
            body=self.body(client); case=self.open_case(client,body).json()
            for role in ('researcher','viewer'):
                self.app.state.auth_store.create_user('peer-'+role,'synthetic-peer-password',role)
                login=client.post('/api/v1/auth/login',json={'username':'peer-'+role,'password':'synthetic-peer-password'})
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.get(BASE).json()['cases'],[])
                self.assertEqual(client.get(BASE+'/'+case['id']).status_code,404)
                self.assertEqual(self.open_case(client,body).status_code,403 if role=='viewer' else 404)
                self.assertEqual(client.post(BASE+'/'+case['id']+'/events',json={'expected_version':1,'action':'note','note':'unauthorized'}).status_code,403 if role=='viewer' else 404)

    def test_anonymous_csrf_extra_authority_and_bounds_rejected(self):
        with TestClient(self.app) as anonymous:
            self.assertEqual(anonymous.get(BASE).status_code,401)
        with authenticated_client(self.app) as client:
            body=self.body(client)
            self.assertEqual(self.open_case(client,{**body,'operational_approval':True}).status_code,422)
            self.assertEqual(self.open_case(client,{**body,'title':' '*5}).status_code,422)
            self.assertEqual(client.post(BASE,json=body,headers={'Idempotency-Key':str(uuid4()),'X-CSRF-Token':'wrong'}).status_code,403)
            self.assertEqual(client.get(BASE+'?owner_id=other').status_code,422)
            case=self.open_case(client,body).json()
            self.assertEqual(client.post(BASE+'/'+case['id']+'/events',json={'expected_version':True,'action':'note','note':'invalid'}).status_code,422)

    def test_changed_source_pin_and_corrupted_snapshot_fail_closed(self):
        with authenticated_client(self.app) as client:
            body=self.body(client)
            self.assertEqual(self.open_case(client,{**body,'source_sha256':'0'*64}).status_code,409)
            case=self.open_case(client,body).json()
            with closing(sqlite3.connect(self.sidecar)) as db,db: db.execute("UPDATE cases SET source_json='{}'")
            self.assertEqual(client.get(BASE+'/'+case['id']).status_code,503)
            self.assertEqual(client.post(BASE+'/'+case['id']+'/events',json={'expected_version':1,'action':'note','note':'blocked'}).status_code,503)

    def test_concurrent_notes_accept_exactly_one_expected_version(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json()
            def write(value):
                try:
                    self.service.change(self.user,case['id'],ChangeCase(expected_version=1,action='note',note=value)); return 'saved'
                except CaseConflict: return 'conflict'
            with ThreadPoolExecutor(max_workers=2) as workers:
                self.assertEqual(sorted(workers.map(write,('first fixture','second fixture'))),['conflict','saved'])
            self.assertEqual(self.service.get(self.user,case['id'])['version'],2)

    def test_default_disabled_and_auth_database_binding(self):
        with authenticated_client(create_app(self.database)) as client:
            self.assertEqual(client.get(BASE).status_code,503)
        with self.assertRaises(ValueError): create_app(self.root/'other.sqlite3',research_cases=self.service)
        with self.assertRaises(ValueError): ResearchCaseService(self.database,self.database)


if __name__=='__main__': unittest.main()
