from contextlib import closing,contextmanager
from concurrent.futures import ThreadPoolExecutor
import copy,json,os
from pathlib import Path
import sqlite3,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from uuid import uuid4
from fastapi.testclient import TestClient
from pydantic import ValidationError
from agents.jobs import JobQueue,JobWorker,QueueFull
from agents.runtime import Investigation,Investigator
from agents.store import AgentStore,Conflict,sha
from agents.archive import page,ArchiveQuery
from services.api.case_jobs import CaseJobs,CaseInvestigation
from services.api.research_cases import ResearchCaseService,OpenCase,ChangeCase,CaseConflict,CaseMissing,digest
from services.api.case_agents import AttachAgent
from services.api.auth import AuthStore
from services.api.main import create_app
from services.api.case_workspace import create_case_app
from tests.test_case_recovery import seed_workspace,PASSWORD


class CaseJobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.fixture=seed_workspace(self.root/'state');self.database=self.root/'state/ain.sqlite3';self.user=self.fixture['user']
        auth=AuthStore(self.database);auth.create_user('other-admin',PASSWORD,'admin');auth.create_user('other-researcher',PASSWORD,'researcher')
        with closing(sqlite3.connect(self.database)) as db:
            self.users={r[1]:dict(zip(('id','username','role'),r)) for r in db.execute('SELECT id,username,role FROM auth_users')}
        self.cases=ResearchCaseService(self.database,self.root/'state/research-cases.sqlite3');self.case=self.open_case('SYNTHETIC private case title')
        self.service=CaseJobs(self.cases);self.store=AgentStore(self.database);self.queue=JobQueue(self.store,self.service)

    def open_case(self,title):
        r=self.fixture['record']
        return self.cases.open(self.user,OpenCase(source_run_id=r['source_run_id'],source_sha256=r['source_sha256'],title=title),uuid4())

    def request(self,version=1,objective='SYNTHETIC investigate recorded input distributions for this case'):
        return CaseInvestigation(expected_version=version,investigation=Investigation(objective=objective,include_distribution_evidence=True,required_tools=['distribution_evidence']))

    def submit(self,request=None,key=None,case=None,user=None):
        request=request or self.request();user=user or self.user;case=case or self.case
        return self.queue.enqueue(user,key or str(uuid4()),request.investigation,context=self.service.submission(user,case['id'],request))

    def execute_fixture(self):
        investigator=Investigator(self.database,None,self.store);worker=JobWorker(self.queue,investigator)
        calls=[[{'function':{'name':'distribution_evidence','arguments':{}}}],[]]
        with patch('agents.runtime.ollama.models',return_value={'qwen3:8b':'synthetic-model-digest'}),patch('agents.runtime.select_tools',side_effect=calls),patch('agents.runtime.ollama.generate',return_value={'claims':[]}):
            # Model key follows the existing configured model name; no provider is contacted.
            from rag import ollama
            with patch('agents.runtime.ollama.models',return_value={ollama.CHAT_MODEL:'synthetic-model-digest'}):self.assertTrue(worker.tick())

    def test_context_and_retry_are_frozen_without_mutating_case(self):
        key=str(uuid4());first=self.submit(key=key);context=first['request']['case_context']
        self.assertEqual(context['case_sha256'],digest({k:v for k,v in self.case.items() if k!='replayed'}))
        self.assertEqual(context['case_id'],self.case['id']);self.assertNotIn('events',context)
        self.cases.change(self.user,self.case['id'],ChangeCase(expected_version=1,action='close',note='SYNTHETIC close before replay'))
        self.assertEqual(self.submit(key=key)['run_id'],first['run_id'])
        with self.assertRaises(CaseConflict):self.submit()
        with self.assertRaises(Conflict):self.submit(key=key,request=self.request(objective='SYNTHETIC changed investigation request'))

    def test_two_cases_do_not_coalesce_and_queue_limits_still_apply(self):
        first=self.submit();second=self.submit(case=self.open_case('SYNTHETIC second case'))
        self.assertNotEqual(first['run_id'],second['run_id'])
        with self.assertRaises(QueueFull):self.submit(request=self.request(objective='SYNTHETIC third unique objective'))

    def test_generic_request_key_cannot_be_reused_to_bind_a_case(self):
        key=str(uuid4());self.queue.enqueue(self.user,key,self.request().investigation)
        with self.assertRaises(CaseConflict):self.submit(key=key)

    def test_wrong_owner_even_admin_and_current_role_are_denied(self):
        for name in ('other-admin','other-researcher'):
            with self.assertRaises(CaseMissing):self.submit(user=self.users[name])
        with closing(sqlite3.connect(self.database)) as db,db:db.execute("UPDATE auth_users SET role='viewer' WHERE id=?",(self.user['id'],))
        with self.assertRaises(PermissionError):self.submit()

    def test_changed_or_closed_case_cancels_waiting_work_without_provider_call(self):
        first=self.submit();self.cases.change(self.user,self.case['id'],ChangeCase(expected_version=1,action='note',note='SYNTHETIC newer evidence'))
        with patch('agents.runtime.ollama.models',side_effect=AssertionError('Provider must not run')):self.assertIsNone(self.queue.claim())
        self.assertEqual(self.queue.get(self.user,first['run_id'])['state'],'cancelled')

    def test_disabled_case_workspace_never_claims_a_bound_job(self):
        first=self.submit();self.assertIsNone(JobQueue(self.store).claim())
        self.assertEqual(self.queue.get(self.user,first['run_id'])['state'],'cancelled')

    def test_missing_case_store_leaves_work_unclaimed_and_blocks_empty_startup(self):
        first=self.submit();self.cases.case_database.rename(self.root/'retained-case-store.sqlite3')
        with self.assertRaises(sqlite3.OperationalError):self.queue.claim()
        with self.assertRaises(sqlite3.OperationalError):self.cases.get(self.user,self.case['id'])
        self.assertEqual(self.queue.get(self.user,first['run_id'])['state'],'queued')
        with patch.dict(os.environ,{'AIN_ENV':'test','AIN_STATE_ROOT':str(self.database.parent),'AIN_DB_PATH':str(self.database)},clear=True),self.assertRaises(ValueError):create_case_app()
        self.assertFalse(self.cases.case_database.exists())

    def test_checkpoint_rejects_changed_or_removed_case_request(self):
        first=self.submit();self.queue.claim();changed=copy.deepcopy(first);changed['request'].pop('case_context')
        with self.assertRaises(Conflict):self.store.checkpoint(changed)
        self.assertEqual(self.queue.get(self.user,first['run_id'])['request'],first['request'])

    def test_runtime_hash_review_and_retained_attachment_bind_the_origin_case(self):
        first=self.submit();self.execute_fixture();result=self.queue.get(self.user,first['run_id'])
        self.assertEqual(result['state'],'awaiting_review');self.assertEqual(result['steps'][0]['state'],'completed')
        self.assertEqual(result['report_sha256'],sha({k:result[k] for k in ('request','steps','claims')}))
        reviewed=self.store.review(self.user,first['run_id'],result['report_sha256'],'needs_changes','SYNTHETIC fixture review; missing generated findings')
        other=self.open_case('SYNTHETIC unrelated target')
        with self.assertRaises(CaseConflict):self.cases.attach_agent(self.user,other['id'],AttachAgent(expected_version=1,agent_run_id=first['run_id'],agent_sha256=digest(reviewed)))
        attached=self.cases.attach_agent(self.user,self.case['id'],AttachAgent(expected_version=1,agent_run_id=first['run_id'],agent_sha256=digest(reviewed)))
        self.assertEqual(attached['version'],2);self.assertEqual(attached['agent_links'][0]['run_id'],first['run_id'])

    def test_owner_only_across_job_history_archive_review_and_cancel(self):
        first=self.submit();other=self.users['other-admin']
        with self.assertRaises(KeyError):self.queue.get(other,first['run_id'])
        with self.assertRaises(KeyError):self.queue.cancel(other,first['run_id'])
        with self.assertRaises(KeyError):self.store.withdraw_sharing(other,SimpleNamespace(run_id=first['run_id']))
        self.assertNotIn(first['run_id'],[r['run_id'] for r in self.store.recent(other)])
        self.assertNotIn(first['run_id'],[r['run_id'] for r in page(self.database,other,ArchiveQuery())['runs']])
        with self.assertRaises(KeyError):self.store.review(other,first['run_id'],'0'*64,'needs_changes','SYNTHETIC unauthorized review')

    def test_restart_interrupts_claimed_job_and_preserves_context(self):
        first=self.submit();self.queue.claim();self.store.recover();saved=self.queue.get(self.user,first['run_id'])
        self.assertEqual(saved['state'],'interrupted');self.assertEqual(saved['request']['case_context'],first['request']['case_context'])

    def test_claims_compete_atomically(self):
        first=self.submit()
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:self.queue.claim(),range(2)))
        self.assertEqual(sum(r is not None for r in claims),1)
        self.assertEqual(next(r for r in claims if r)[2]['run_id'],first['run_id'])

    def test_primary_commit_precedes_release_of_case_guard(self):
        request=self.request();factory=self.service.submission(self.user,self.case['id'],request);key=str(uuid4())
        @contextmanager
        def guarded(primary,prior):
            with factory(primary,prior) as context:
                with closing(sqlite3.connect(self.cases.case_database,timeout=.01)) as writer:
                    with self.assertRaises(sqlite3.OperationalError):writer.execute("UPDATE cases SET title='blocked'")
                yield context
                with closing(sqlite3.connect(self.database)) as reader:
                    self.assertEqual(reader.execute('SELECT count(*) FROM agent_runs WHERE request_key=?',(key,)).fetchone()[0],1)
        self.queue.enqueue(self.user,key,request.investigation,context=guarded)

    def test_account_revocation_stops_bound_execution_at_safe_boundary(self):
        first=self.submit();self.queue.claim()
        with closing(sqlite3.connect(self.database)) as db,db:db.execute("UPDATE auth_users SET active=0 WHERE id=?",(self.user['id'],))
        self.assertTrue(self.store.stop_requested(first['run_id']))

    def test_api_checks_auth_roles_csrf_staleness_and_extra_authority(self):
        with patch.dict(os.environ,{'AIN_AGENT_JOBS':'1'}):app=create_app(self.database,research_cases=self.cases)
        worker=app.state.job_worker
        with patch.object(worker,'start'),patch.object(worker,'stop',new=AsyncMock()),TestClient(app) as client:
            worker.task=SimpleNamespace(done=lambda:False);path='/api/v1/research/cases/'+self.case['id']+'/jobs'
            self.assertEqual(client.get(path).status_code,401)
            def login(name):
                response=client.post('/api/v1/auth/login',json={'username':name,'password':PASSWORD},headers={'Origin':'http://localhost:8080'})
                return {'Origin':'http://localhost:8080','X-CSRF-Token':response.json()['csrf_token'],'Idempotency-Key':str(uuid4())}
            headers=login('case-owner');payload=self.request().model_dump(mode='json')
            self.assertEqual(client.post(path,json=payload,headers={'Origin':'http://localhost:8080'}).status_code,403)
            self.assertEqual(client.post(path+'?owner=other',json=payload,headers=headers).status_code,422)
            self.assertEqual(client.post(path,json={**payload,'case_context':{}},headers=headers).status_code,422)
            self.assertEqual(client.post(path,json={**payload,'expected_version':2},headers=headers).status_code,409)
            result=client.post(path,json=payload,headers=headers);self.assertEqual(result.status_code,202,result.text)
            self.assertEqual(client.get(path).json()['jobs'][0]['run_id'],result.json()['run_id'])
            injected={**payload['investigation'],'case_context':result.json()['request']['case_context']}
            self.assertEqual(client.post('/api/v1/research/agent-jobs',json=injected,headers=headers).status_code,422)
            headers=login('other-admin');self.assertEqual(client.get(path).status_code,404);self.assertEqual(client.post(path,json=payload,headers=headers).status_code,404)
            headers=login('case-viewer');self.assertEqual(client.post(path,json=payload,headers=headers).status_code,403)
            headers=login('case-owner');worker.enabled=False;self.assertEqual(client.post(path,json=payload,headers=headers).status_code,503)

    def test_client_case_context_and_peer_sharing_are_not_accepted(self):
        with self.assertRaises(ValidationError):Investigation(objective='SYNTHETIC forged case input',case_context={})
        with self.assertRaises(ValidationError):CaseInvestigation(expected_version=1,investigation=Investigation(objective='SYNTHETIC sharing request',require_peer_review=True))
