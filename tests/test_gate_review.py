from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4
from unittest.mock import patch
from pydantic import ValidationError
from fastapi.testclient import TestClient
from optimization.gates import optimize
from optimization.history import GateRunStore
from optimization.reviews import GateReview,ReviewConflict,proposal_hash,status,digest
from agents.tools import gate_sample
from services.api.main import initialize,create_app

NOW=datetime(2026,11,20,12,tzinfo=timezone.utc)


class GateReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'state.sqlite3';initialize(self.db)
        self.time=NOW;self.store=GateRunStore(self.db,clock=lambda:self.time)
        self.user={'id':'fixture-owner','username':'fixture-owner','role':'researcher'}
        self.result=optimize(gate_sample());self.run=self.store.save(self.user,str(uuid4()),self.result)

    def tearDown(self):self.folder.cleanup()

    def request(self,**changes):
        return GateReview.model_validate({'run_id':self.run['run_id'],'proposal_sha256':self.run['proposal_sha256'],'review_key':str(uuid4()),'decision':'reviewed','note':'Checked synthetic assignments and constraints.','acknowledged':True,**changes})

    def update(self,run):
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('UPDATE gate_runs SET result_json=? WHERE id=?',(json.dumps(run),self.run['run_id']))

    def test_sealed_proposal_is_exactly_bound_and_original_solver_result_preserved(self):
        self.assertEqual(self.run['proposal_sha256'],proposal_hash(self.run))
        self.assertEqual(self.run['review_status']['state'],'pending');self.assertTrue(self.run['review_status']['eligible'])
        self.assertEqual(self.run['candidate'],self.result['candidate'])
        saved=self.store.review(self.user,self.request())
        self.assertEqual(saved['review_status']['state'],'reviewed');self.assertFalse(saved['operational_approval'])
        self.assertEqual(status(saved,self.time)['state'],'reviewed');self.assertEqual(saved['proposal_sha256'],self.run['proposal_sha256'])
        self.assertEqual(saved['review']['decision_sha256'],digest({k:v for k,v in saved['review'].items() if k!='decision_sha256'}))

    def test_expiry_exact_boundary_bad_clock_and_legacy_never_enable_review(self):
        self.time=NOW+timedelta(hours=24)
        self.assertEqual(self.store.recent(self.user)[0]['review_status']['state'],'expired')
        with self.assertRaises(ReviewConflict):self.store.review(self.user,self.request())
        self.assertEqual(status(self.run,NOW-timedelta(seconds=1))['state'],'invalid')
        self.assertEqual(status(self.run,NOW.replace(tzinfo=None))['state'],'invalid')
        legacy={k:v for k,v in self.run.items() if k not in ('proposal_sha256','review_expires_at','review','review_status')}
        self.update(legacy);self.assertEqual(self.store.recent(self.user)[0]['review_status']['state'],'legacy')
        with self.assertRaises(ReviewConflict):self.store.review(self.user,self.request())

    def test_changed_content_recomputed_invalid_plan_and_extended_expiry_are_blocked(self):
        for kind in ['assignment','scope','expiry','row_anchor']:
            changed=copy.deepcopy(self.run)
            if kind=='assignment':
                changed['candidate']['assignments'][0]['gate']='MISSING';changed['proposal_sha256']=proposal_hash(changed)
            elif kind=='scope':changed['operational_approval']=True
            elif kind=='expiry':
                changed['review_expires_at']=(NOW+timedelta(hours=48)).isoformat();changed['proposal_sha256']=proposal_hash(changed)
            else:
                changed['saved_at']=(NOW-timedelta(minutes=1)).isoformat();changed['review_expires_at']=(NOW-timedelta(minutes=1)+timedelta(hours=24)).isoformat();changed['proposal_sha256']=proposal_hash(changed)
            self.update(changed)
            with self.assertRaises(ReviewConflict):self.store.review(self.user,self.request(proposal_sha256=changed['proposal_sha256']))

    def test_identical_retry_is_replayed_even_after_expiry_but_conflicts_are_rejected(self):
        request=self.request();first=self.store.review(self.user,request);self.time=NOW+timedelta(days=2)
        replay=self.store.review(self.user,request);self.assertTrue(replay['review_replayed']);self.assertEqual(first['review'],replay['review'])
        for changes in [{'decision':'needs_changes'},{'note':'Different research note'},{'review_key':str(uuid4())}]:
            with self.assertRaises(ReviewConflict):self.store.review(self.user,GateReview.model_validate({**request.model_dump(),**changes}))
        changed=self.store.recent(self.user)[0];changed['review']['note']='Altered receipt';self.update(changed)
        with self.assertRaises(ReviewConflict):self.store.review(self.user,request)

    def test_competing_decisions_commit_only_once(self):
        requests=[self.request(decision='reviewed'),self.request(decision='needs_changes')]
        def decide(request):
            try:return self.store.review(self.user,request)['review']['decision']
            except ReviewConflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(decide,requests))
        self.assertEqual(results.count('conflict'),1)
        self.assertIn(self.store.recent(self.user)[0]['review']['decision'],['reviewed','needs_changes'])

    def test_owner_role_and_strict_acknowledgment_contract(self):
        with self.assertRaises(KeyError):self.store.review({**self.user,'id':'other-owner'},self.request())
        with self.assertRaises(PermissionError):self.store.review({**self.user,'role':'viewer'},self.request())
        for changes in [{'acknowledged':False},{'acknowledged':1},{'acknowledged':'true'},{'note':'    '},{'operational_approval':True}]:
            with self.assertRaises(ValidationError):self.request(**changes)
        result=self.store.review({'id':'fixture-admin','username':'fixture-admin','role':'admin'},self.request(decision='needs_changes'))
        self.assertEqual(result['review']['reviewer'],'fixture-admin')

    def test_api_requires_session_role_origin_csrf_and_returns_safe_failures(self):
        with patch('services.api.main.GateRunStore',return_value=self.store):app=create_app(self.db)
        with TestClient(app) as client:
            password='temporary-gate-review-fixture-123';origin={'Origin':'http://127.0.0.1:8080'};path='/api/v1/research/gate-review'
            self.assertEqual(client.post(path,json=self.request().model_dump(mode='json'),headers=origin).status_code,401)
            for role in ['admin','viewer']:app.state.auth_store.create_user('fixture-'+role,password,role)
            login=client.post('/api/v1/auth/login',json={'username':'fixture-admin','password':password},headers=origin);csrf={'X-CSRF-Token':login.json()['csrf_token']}
            body=self.request().model_dump(mode='json')
            self.assertEqual(client.post(path,json=body).status_code,403)
            self.assertEqual(client.post(path,json=body,headers=origin).status_code,403)
            self.assertEqual(client.post(path,json=body,headers={**origin,**csrf}).status_code,200)
            self.assertEqual(client.post(path,json=self.request().model_dump(mode='json'),headers={**origin,**csrf}).status_code,409)
            with patch('optimization.history.GateRunStore.review',side_effect=sqlite3.OperationalError('PRIVATE PATH')):
                response=client.post(path,json=body,headers={**origin,**csrf})
            self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE PATH',response.text)
            login=client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':password},headers=origin)
            self.assertEqual(client.post(path,json=body,headers={**origin,'X-CSRF-Token':login.json()['csrf_token']}).status_code,403)

    def test_decision_survives_new_store_and_does_not_rewrite_scenario_or_created_time(self):
        self.store.review(self.user,self.request(decision='needs_changes'))
        restored=GateRunStore(self.db,clock=lambda:self.time).recent(self.user)[0]
        self.assertEqual(restored['review_status']['state'],'needs_changes')
        with closing(sqlite3.connect(self.db)) as c:
            row=c.execute('SELECT scenario_hash,created_at FROM gate_runs WHERE id=?',(self.run['run_id'],)).fetchone()
            self.assertEqual(row,(self.run['scenario_sha256'],self.run['saved_at']))
