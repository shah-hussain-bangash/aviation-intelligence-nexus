from contextlib import closing
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch,Mock
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.store import AgentStore
from agents.jobs import JobQueue
from agents.runtime import Investigation,Investigator
from services.api.main import initialize,create_app
from services.api.agent_operations import snapshot,age_seconds,OperationsUnavailable,LOCK
from rag import ollama

NOW=datetime(2026,11,20,12,tzinfo=timezone.utc)
WORKER={'enabled':True,'alive':True,'last_poll':(NOW-timedelta(seconds=1)).isoformat(),'error':None}


class AgentOperationsTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'state.sqlite3';initialize(self.db)
        self.store=AgentStore(self.db)
        self.user={'id':'private-owner','username':'private-username','role':'researcher'}

    def tearDown(self):self.folder.cleanup()

    def record(self,state,elapsed=None,flag=None,execution=True,created=None,started=None):
        run=self.store.begin(self.user,str(uuid4()),{'objective':'PRIVATE OBJECTIVE'})
        run.update(state=state,created_at=created or NOW.isoformat(),started_at=started or NOW.isoformat(),claims=[{'private':'PRIVATE ANSWER'}])
        if execution:run['execution']='local-background-queue-v1'
        if flag is not None:run['quality']={'passed':flag};run['report_sha256']='a'*64
        if elapsed is not None:run['steps']=[{'tool':'model_evidence','state':'completed' if state!='failed' else 'failed','elapsed_ms':elapsed,'arguments':{'private':'PRIVATE ARGUMENT'}}]
        self.store.checkpoint(run);return run

    def test_counts_window_timing_ages_privacy_and_read_only(self):
        self.record('queued',created=(NOW-timedelta(seconds=120)).isoformat());self.record('queued',created=(NOW+timedelta(seconds=1)).isoformat())
        self.record('running',started=(NOW-timedelta(seconds=45)).isoformat())
        self.record('awaiting_review',12,True);self.record('failed',30);self.record('needs_changes',20,False);self.record('reviewed',True)
        self.record('failed',999,execution=False)
        before=hashlib.sha256(self.db.read_bytes()).hexdigest()
        data=snapshot(self.db,WORKER,NOW)
        self.assertEqual(data['total_background_runs'],7);self.assertEqual(data['totals']['queued'],2)
        self.assertEqual(data['active_ages']['oldest_wait_seconds'],120)
        self.assertEqual(data['active_ages']['oldest_running_seconds'],45)
        self.assertEqual(data['active_ages']['unknown_wait_times'],1)
        self.assertEqual(data['recent_window']['recorded_draft_coverage'],{'passed':1,'blocked':1,'not_recorded':1})
        self.assertEqual(data['recent_window']['tool_time'],{'sample_size':3,'not_recorded':1,'p50_ms':20,'p95_ms':30,'max_ms':30})
        self.assertEqual(data['recent_window']['tools']['model_evidence'],{'attempted':4,'completed':3,'failed_or_unfinished':1})
        for private in ['private-owner','private-username','PRIVATE OBJECTIVE','PRIVATE ANSWER','PRIVATE ARGUMENT']:
            self.assertNotIn(private,json.dumps(data))
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)
        self.assertFalse(data['external_alert_delivery']);self.assertFalse(data['production_ready'])

    def test_june_tool_is_counted_without_exposing_arguments_or_claiming_provider_success(self):
        run=self.record('awaiting_review',2,True)
        run['steps'][0]['tool']='june_evidence';self.store.checkpoint(run)
        data=snapshot(self.db,WORKER,NOW)
        self.assertEqual(data['recent_window']['tools']['june_evidence'],{'attempted':1,'completed':1,'failed_or_unfinished':0})
        self.assertEqual(data['recent_window']['tools']['unknown']['attempted'],0)
        self.assertNotIn('PRIVATE ARGUMENT',json.dumps(data));self.assertFalse(data['production_ready'])

    def test_worker_states_and_invalid_times_do_not_infer_health(self):
        self.assertEqual(snapshot(self.db,WORKER,NOW)['worker']['state'],'idle')
        for changes,state in [({'enabled':False},'disabled'),({'alive':False},'unavailable'),({'error':'PRIVATE ERROR'},'unavailable'),({'last_poll':None},'unknown'),({'last_poll':(NOW-timedelta(seconds=6)).isoformat()},'unknown')]:
            data=snapshot(self.db,{**WORKER,**changes},NOW);self.assertEqual(data['worker']['state'],state);self.assertNotIn('PRIVATE ERROR',json.dumps(data))
        for value in [None,'invalid',NOW.replace(tzinfo=None).isoformat(),(NOW+timedelta(seconds=1)).isoformat()]:
            self.assertIsNone(age_seconds(value,NOW))
        self.record('running',started='invalid')
        data=snapshot(self.db,{**WORKER,'last_poll':(NOW-timedelta(seconds=120)).isoformat()},NOW)
        self.assertEqual(data['worker']['state'],'active');self.assertEqual(data['active_ages']['unknown_running_times'],1)

    def test_recent_window_is_bounded_while_totals_include_retained_history(self):
        for _ in range(205):self.record('failed')
        data=snapshot(self.db,WORKER,NOW)
        self.assertEqual(data['total_background_runs'],205);self.assertEqual(data['recent_window']['size'],200)
        self.assertEqual(data['recent_window']['tool_time']['not_recorded'],200)
        self.assertIsNone(data['recent_window']['tool_time']['p95_ms'])

    def test_missing_busy_deadline_and_bad_storage_fail_without_creation(self):
        missing=self.db.parent/'missing.sqlite3'
        with self.assertRaises(OperationsUnavailable):snapshot(missing,WORKER,NOW)
        self.assertFalse(missing.exists())
        with LOCK:
            with self.assertRaises(OperationsUnavailable):snapshot(self.db,WORKER,NOW)
        calls=[0]
        def expired():calls[0]+=1;return 0 if calls[0]==1 else 4
        with self.assertRaises(OperationsUnavailable):snapshot(self.db,WORKER,NOW,clock=expired)
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('INSERT INTO agent_runs VALUES(?,?,?,?,?,?)',('bad','owner','key','hash','not json','now'))
        with self.assertRaises(OperationsUnavailable):snapshot(self.db,WORKER,NOW)

    def test_admin_only_read_route_and_non_admin_never_reads_snapshot(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            path='/api/v1/research/agent-operations';self.assertEqual(client.get(path).status_code,401)
            password='temporary-operations-fixture-123';origin={'Origin':'http://127.0.0.1:8080'}
            for role in ['admin','researcher','viewer']:app.state.auth_store.create_user('fixture-'+role,password,role)
            for role in ['researcher','viewer']:
                client.post('/api/v1/auth/login',json={'username':'fixture-'+role,'password':password},headers=origin)
                with patch('services.api.main.agent_operations_snapshot') as read:
                    self.assertEqual(client.get(path).status_code,403);read.assert_not_called()
            login=client.post('/api/v1/auth/login',json={'username':'fixture-admin','password':password},headers=origin)
            result=client.get(path);self.assertEqual(result.status_code,200);self.assertEqual(result.headers['cache-control'],'no-store')
            client.headers.update({**origin,'X-CSRF-Token':login.json()['csrf_token']})
            self.assertEqual(client.post(path,json={}).status_code,405);self.assertEqual(client.get(path+'/arbitrary').status_code,404)

    def test_api_unavailability_never_returns_private_diagnostics_or_prior_counts(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            password='temporary-operations-fixture-123';app.state.auth_store.create_user('fixture-admin',password,'admin')
            client.post('/api/v1/auth/login',json={'username':'fixture-admin','password':password},headers={'Origin':'http://127.0.0.1:8080'})
            with patch('services.api.main.agent_operations_snapshot',side_effect=OperationsUnavailable('PRIVATE PATH')):
                response=client.get('/api/v1/research/agent-operations')
            self.assertEqual(response.status_code,503);self.assertNotIn('totals',response.json());self.assertNotIn('PRIVATE PATH',response.text)

    def test_real_queue_claim_draft_and_review_transitions_are_observable(self):
        from services.api.auth import AuthStore
        auth=AuthStore(self.db);auth.create_user('fixture-admin','temporary-operations-fixture-123','admin')
        with closing(sqlite3.connect(self.db)) as c:
            row=c.execute('SELECT id,username,role FROM auth_users').fetchone()
        user=dict(zip(['id','username','role'],row));queue=JobQueue(self.store)
        request=Investigation(objective='Review recorded model errors and limitations.',include_model_evidence=True,required_tools=['model_evidence'])
        queued=queue.enqueue(user,str(uuid4()),request)
        self.assertEqual(snapshot(self.db,WORKER)['totals']['queued'],1)
        owner,key,running=queue.claim();self.assertEqual(snapshot(self.db,WORKER)['totals']['running'],1)
        def generate(question,evidence,**kwargs):
            line=next(line for line in evidence[0]['text'].splitlines() if line.startswith('Input reliance is not'))
            return {'claims':[{'text':line,'quote':line,'citation':evidence[0]['id']}]}
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch.object(ollama,'generate',side_effect=generate),patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'model_evidence','arguments':{}}}],[]]):
            run=Investigator(self.db,Mock(),self.store).run(owner,key,request,queued_result=running)
        data=snapshot(self.db,WORKER);self.assertEqual(data['totals']['awaiting_review'],1)
        self.assertEqual(data['recent_window']['recorded_draft_coverage']['passed'],1)
        self.store.review(user,run['run_id'],run['report_sha256'],'needs_changes','Fixture reviewer requests more context')
        data=snapshot(self.db,WORKER);self.assertEqual(data['totals']['needs_changes'],1)
        self.assertEqual(data['recent_window']['tool_time']['sample_size'],1)
