from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4
from fastapi.testclient import TestClient
from agents.runtime import Investigation,Investigator
from agents.store import AgentStore,Conflict
from agents.jobs import JobQueue
from agents.cancellation import finish_cancelled
from agents import tools
from rag import ollama
from services.api.main import initialize,create_app
from services.api.auth import AuthStore


def draft(question,evidence,**kwargs):
    row=evidence[0];line=next(line for line in row['text'].splitlines() if line.startswith('Input reliance is not'))
    return {'claims':[{'text':line,'quote':line,'citation':row['id']}]}


class AgentStopTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'state.sqlite3';initialize(self.db)
        auth=AuthStore(self.db)
        auth.create_user('synthetic-setup-admin','synthetic-stop-fixture-password','admin')
        auth.create_user('fixture-owner','synthetic-stop-fixture-password','researcher')
        with closing(auth.connect()) as db:
            self.user=dict(db.execute("SELECT id,username,role FROM auth_users WHERE username='fixture-owner'").fetchone())
        self.store=AgentStore(self.db);self.queue=JobQueue(self.store);self.runtime=Investigator(self.db,Mock(),self.store)
        self.request=Investigation(objective='Review recorded model evidence and limitations.',include_model_evidence=True,required_tools=['model_evidence'])

    def tearDown(self):self.folder.cleanup()

    def running(self):return self.store.begin(self.user,str(uuid4()),self.request.model_dump())

    def test_stop_request_is_owner_checked_idempotent_and_not_an_immediate_interrupt(self):
        run=self.running()
        with self.assertRaises(KeyError):self.queue.cancel({**self.user,'id':'foreign'},run['run_id'])
        with self.assertRaises(PermissionError):self.queue.cancel({**self.user,'role':'viewer'},run['run_id'])
        first=self.queue.cancel(self.user,run['run_id']);self.assertEqual(first['state'],'running')
        second=self.queue.cancel({**self.user,'role':'admin','username':'fixture-admin'},run['run_id'])
        self.assertEqual(second['cancel_requested_at'],first['cancel_requested_at']);self.assertEqual(second['cancel_requested_by'],self.user['username'])

    def test_stop_before_first_call_skips_model_and_has_no_reviewable_draft(self):
        run=self.running();self.queue.cancel(self.user,run['run_id'])
        with patch.object(ollama,'models') as models:
            result=self.runtime.run(self.user,'fixture-key',self.request,queued_result=run);models.assert_not_called()
        self.assertEqual(result['state'],'cancelled');self.assertEqual(result['steps'],[]);self.assertEqual(result['claims'],[])
        self.assertNotIn('report_sha256',result)

    def exercise_blocked(self,stage):
        entered=Event();release=Event();key=str(uuid4());real_execute=tools.execute
        def planner(*args):
            if stage=='planner':entered.set();release.wait(5)
            return [{'function':{'name':'model_evidence','arguments':{}}}]
        def execute(*args):
            if stage=='tool':entered.set();release.wait(5)
            return real_execute(*args)
        def generate(*args,**kwargs):
            if stage=='summary':entered.set();release.wait(5)
            return draft(*args,**kwargs)
        calls=[0]
        def select(*args):
            calls[0]+=1
            return planner(*args) if calls[0]==1 else []
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch('agents.runtime.select_tools',side_effect=select),patch('agents.tools.execute',side_effect=execute) as tool,patch.object(ollama,'generate',side_effect=generate) as summary:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(self.runtime.run,self.user,key,self.request)
                try:
                    self.assertTrue(entered.wait(5));saved=self.store.recent(self.user)[0]
                    requested=self.queue.cancel(self.user,saved['run_id']);self.assertEqual(requested['state'],'running');self.assertFalse(pending.done())
                finally:release.set()
                result=pending.result(timeout=10)
            self.assertEqual(result['state'],'cancelled');self.assertNotIn('report_sha256',result);self.assertEqual(result['claims'],[])
            if stage=='planner':tool.assert_not_called();summary.assert_not_called()
            elif stage=='tool':self.assertEqual(tool.call_count,1);summary.assert_not_called();self.assertEqual(result['steps'][0]['state'],'completed')
            else:self.assertEqual(summary.call_count,1);self.assertEqual(result['steps'][0]['state'],'completed')
        with patch('agents.runtime.select_tools') as select:
            replay=self.runtime.run(self.user,key,self.request);select.assert_not_called()
        self.assertTrue(replay['replayed']);self.assertEqual(replay['state'],'cancelled')
        with self.assertRaises(Conflict):self.store.review(self.user,result['run_id'],'a'*64,'reviewed','No draft can be reviewed')
        return result

    def test_current_planner_finishes_then_no_tool_is_started(self):self.exercise_blocked('planner')

    def test_current_tool_finishes_and_its_evidence_is_retained(self):self.exercise_blocked('tool')

    def test_current_summary_finishes_but_its_draft_is_not_published(self):self.exercise_blocked('summary')

    def test_final_checkpoint_serializes_stop_before_draft_commit_and_preserves_aliases(self):
        original=self.store.checkpoint
        def checkpoint(run):
            if run['state']=='awaiting_review':self.queue.cancel(self.user,run['run_id'])
            original(run)
        with patch.object(self.store,'checkpoint',side_effect=checkpoint),patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'model_evidence','arguments':{}}}],[]]),patch.object(ollama,'generate',side_effect=draft):
            result=self.runtime.run(self.user,str(uuid4()),self.request)
        self.assertEqual(result['state'],'cancelled');self.assertNotIn('quality',result);self.assertNotIn('report_sha256',result)
        fresh=self.running();stale=copy.deepcopy(fresh);self.queue.cancel(self.user,fresh['run_id']);stale['submission_keys']=['fixture-alias']
        self.store.checkpoint(stale);self.assertTrue(self.queue.get(self.user,fresh['run_id'])['cancel_requested_at'])
        # Completion wins if its transaction commits before a stop request.
        fresh=self.running();fresh.update(state='awaiting_review',report_sha256='a'*64);self.store.checkpoint(fresh)
        with self.assertRaises(Conflict):self.queue.cancel(self.user,fresh['run_id'])
        self.assertEqual(self.queue.get(self.user,fresh['run_id'])['state'],'awaiting_review')

    def test_restart_with_pending_stop_is_interrupted_and_never_replayed(self):
        run=self.running();self.queue.cancel(self.user,run['run_id']);self.store.recover()
        saved=self.queue.get(self.user,run['run_id']);self.assertEqual(saved['state'],'interrupted');self.assertTrue(saved['cancel_requested_at'])
        self.assertIsNone(self.queue.claim())

    def test_api_running_acknowledgment_role_origin_csrf_and_completed_stop(self):
        app=create_app(self.db)
        with TestClient(app) as client:
            password='temporary-stop-fixture-123';origin={'Origin':'http://127.0.0.1:8080'};path='/api/v1/research/agent-cancel'
            self.assertEqual(client.post(path,json={'run_id':str(uuid4())},headers=origin).status_code,401)
            for role in ['admin','viewer']:app.state.auth_store.create_user('fixture-'+role,password,role)
            with closing(sqlite3.connect(self.db)) as c:
                row=c.execute("SELECT id,username,role FROM auth_users WHERE username='fixture-admin'").fetchone()
            user=dict(zip(['id','username','role'],row));run=self.store.begin(user,str(uuid4()),self.request.model_dump())
            login=client.post('/api/v1/auth/login',json={'username':'fixture-admin','password':password},headers=origin)
            headers={**origin,'X-CSRF-Token':login.json()['csrf_token']};body={'run_id':run['run_id']}
            self.assertEqual(client.post(path,json=body).status_code,403);self.assertEqual(client.post(path,json=body,headers=origin).status_code,403)
            response=client.post(path,json=body,headers=headers);self.assertEqual(response.status_code,202);self.assertEqual(response.json()['state'],'running')
            finish_cancelled(run,response.json()['cancel_requested_at']);self.store.checkpoint(run)
            self.assertEqual(client.post(path,json=body,headers=headers).status_code,200)
            login=client.post('/api/v1/auth/login',json={'username':'fixture-viewer','password':password},headers=origin)
            self.assertEqual(client.post(path,json=body,headers={**origin,'X-CSRF-Token':login.json()['csrf_token']}).status_code,403)
