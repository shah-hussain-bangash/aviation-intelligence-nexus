from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
import json
import sqlite3
import unittest
from uuid import uuid4
from agents.evaluate_peer_review import seed as seed_agent
from agents.store import AgentStore,sha
from services.api.main import create_app
from services.api.research_cases import ResearchCaseService,CaseConflict,digest
from services.api.case_agents import AttachAgent
from tests.auth_helpers import authenticated_client
from tests import test_research_cases as cases
BASE=cases.BASE


class CaseAgentTests(unittest.TestCase):
    setUp=cases.ResearchCaseTests.setUp
    seed=cases.ResearchCaseTests.seed
    body=cases.ResearchCaseTests.body
    open_case=cases.ResearchCaseTests.open_case

    def agent(self,peer=False,decision='needs_changes',pending=False,owner=None,reviewer=None):
        owner=owner or self.user;store=AgentStore(self.database);run=seed_agent(store,owner,peer)
        run['request']['objective']='SYNTHETIC case attachment: inspect recorded research evidence.'
        run['report_sha256']=sha({k:run[k] for k in ('request','steps','claims')});store.checkpoint(run)
        if not pending:store.review(reviewer or owner,run['run_id'],run['report_sha256'],decision,'SYNTHETIC fixture review; no model execution or real-user acceptance')
        with closing(sqlite3.connect(self.database)) as db:return json.loads(db.execute('SELECT result_json FROM agent_runs WHERE id=?',(run['run_id'],)).fetchone()[0])

    def payload(self,run,version=1):return {'expected_version':version,'agent_run_id':run['run_id'],'agent_sha256':digest(run)}

    def user_record(self,name,role):
        self.app.state.auth_store.create_user(name,'synthetic-agent-password',role)
        with closing(sqlite3.connect(self.database)) as db:row=db.execute('SELECT id,username,role FROM auth_users WHERE username=?',(name,)).fetchone()
        return dict(zip(('id','username','role'),row))

    def test_attachment_replay_source_deletion_closure_and_recreated_app(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.agent();payload=self.payload(run);path=BASE+'/'+case['id']
            saved=client.post(path+'/agents',json=payload);self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(saved.json()['agent_links'][0]['review_state'],'needs_changes')
            endpoint=path+'/agents/'+run['run_id'];snapshot=client.get(endpoint).json()
            self.assertEqual(snapshot['snapshot'],run);self.assertEqual(snapshot['attached_version'],2)
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('DELETE FROM agent_runs WHERE id=?',(run['run_id'],))
            self.assertEqual(client.get(endpoint).json(),snapshot)
            self.assertTrue(client.post(path+'/agents',json=payload).json()['replayed'])
            self.assertEqual(client.post(path+'/agents',json={**payload,'expected_version':2}).status_code,409)
            client.post(path+'/events',json={'expected_version':2,'action':'close','note':'SYNTHETIC outcome'})
            self.assertEqual(client.post(path+'/agents',json=payload).json()['version'],3)
            self.assertEqual(client.post(path+'/agents',json=self.payload(self.agent(),3)).status_code,409)
        with authenticated_client(create_app(self.database,research_cases=ResearchCaseService(self.database,self.sidecar))) as client:
            self.assertEqual(client.get(endpoint).json()['snapshot'],run)

    def test_pending_and_foreign_reports_cannot_be_copied_even_by_admin(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();path=BASE+'/'+case['id'];pending=self.agent(pending=True)
            self.assertEqual(client.get('/api/v1/research/case-agent-sources').json()['sources'],[])
            self.assertEqual(client.post(path+'/agents',json=self.payload(pending)).status_code,503)
            foreign=self.user_record('foreign-author','researcher');report=self.agent(owner=foreign)
            self.assertEqual(client.post(path+'/agents',json=self.payload(report)).status_code,404)
            self.assertEqual(client.get(path+'/agents/'+report['run_id']).status_code,404)

    def test_peer_review_record_and_role_boundary_preserved(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();reviewer=self.user_record('case-peer','researcher')
            run=self.agent(peer=True,decision='reviewed',reviewer=reviewer);path=BASE+'/'+case['id'];payload=self.payload(run)
            self.assertEqual(client.post(path+'/agents',json=payload).status_code,200)
            snapshot=client.get(path+'/agents/'+run['run_id']).json();self.assertEqual(snapshot['review_kind'],'second_account')
            self.assertTrue(snapshot['snapshot']['reviews'][0]['second_account_review']);self.assertFalse(snapshot['operational_approval'])
            for name,role in [('case-peer','researcher'),('case-viewer','viewer')]:
                if role=='viewer':self.user_record(name,role)
                login=client.post('/api/v1/auth/login',json={'username':name,'password':'synthetic-agent-password'});client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.get('/api/v1/research/case-agent-sources').json()['sources'],[])
                self.assertEqual(client.get(path+'/agents/'+run['run_id']).status_code,404)
                self.assertEqual(client.post(path+'/agents',json=payload).status_code,403 if role=='viewer' else 404)

    def test_pins_review_binding_and_snapshot_corruption_fail_closed(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.agent();payload=self.payload(run);path=BASE+'/'+case['id']
            self.assertEqual(client.post(path+'/agents',json={**payload,'agent_sha256':'0'*64}).status_code,409)
            changed=copy.deepcopy(run);changed['reviews'][0]['report_sha256']='0'*64
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('UPDATE agent_runs SET result_json=?',(json.dumps(changed),))
            self.assertEqual(client.post(path+'/agents',json=self.payload(changed)).status_code,503)
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('UPDATE agent_runs SET result_json=?',(json.dumps(run),))
            self.assertEqual(client.post(path+'/agents',json=payload).status_code,200)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute("UPDATE case_agents SET snapshot_json='{}'")
            self.assertEqual(client.get(path).status_code,503);self.assertEqual(client.get(path+'/agents/'+run['run_id']).status_code,503)

    def test_atomic_failure_contention_and_five_report_limit(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.agent();path=BASE+'/'+case['id'];payload=self.payload(run)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute("CREATE TRIGGER reject_agent BEFORE INSERT ON case_agents BEGIN SELECT RAISE(ABORT,'fixture'); END")
            self.assertEqual(client.post(path+'/agents',json=payload).status_code,503);self.assertEqual(client.get(path).json()['version'],1)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute('DROP TRIGGER reject_agent')
            other=self.payload(self.agent())
            def attach(body):
                try:self.service.attach_agent(self.user,case['id'],AttachAgent(**body));return 'saved'
                except CaseConflict:return 'conflict'
            with ThreadPoolExecutor(max_workers=2) as workers:self.assertEqual(sorted(workers.map(attach,(payload,other))),['conflict','saved'])
            for version in range(2,6):self.assertEqual(client.post(path+'/agents',json=self.payload(self.agent(),version)).status_code,200)
            self.assertEqual(client.post(path+'/agents',json=self.payload(self.agent(),6)).status_code,409)
            self.assertEqual(len(client.get(path).json()['agent_links']),5)

    def test_schema_two_preserves_evidence_and_case_history(self):
        from rag.history import EvidenceHistory
        from services.api.research_cases import AttachEvidence
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json()
            saved=EvidenceHistory(self.database).save(self.user,{'question':'SYNTHETIC evidence','mode':'abstained','evidence':[],'claims':[],'research_only':True,'operational_approval':False})
            self.service.attach_evidence(self.user,case['id'],AttachEvidence(expected_version=1,evidence_run_id=saved['run_id'],evidence_sha256=digest(saved)))
            before=self.service.get(self.user,case['id'])
        with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute('DROP TABLE case_agents');db.execute('PRAGMA user_version=2')
        service=ResearchCaseService(self.database,self.sidecar);self.assertEqual(service.get(self.user,case['id']),before)
        with closing(sqlite3.connect(self.sidecar)) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_request_bounds_csrf_and_query_authority(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.agent();body=self.payload(run);path=BASE+'/'+case['id']+'/agents'
            self.assertEqual(client.post(path,json=body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
            for extra in ({'expected_version':True},{'owner_id':'other'},{'operational_approval':True}):self.assertEqual(client.post(path,json={**body,**extra}).status_code,422)
            self.assertEqual(client.get('/api/v1/research/case-agent-sources?owner=other').status_code,422)

    def test_invalid_peer_receipt_state_report_hash_and_size_rejected(self):
        from services.api.case_agents import checked_agent
        with authenticated_client(self.app) as client:
            self.open_case(client);reviewer=self.user_record('bounded-peer','researcher');run=self.agent(peer=True,reviewer=reviewer)
            self.assertEqual(checked_agent(json.dumps(run),run['run_id'],self.user['id'])['state'],'needs_changes')
            invalid=[]
            for state in ('queued','running','awaiting_review','cancelled','withdrawn'):
                changed=copy.deepcopy(run);changed['state']=state;invalid.append(changed)
            for patch in ({'reviewer_id':self.user['id']},{'second_account_review':False},{'report_sha256':'f'*64}):
                changed=copy.deepcopy(run);changed['reviews'][0].update(patch);invalid.append(changed)
            changed=copy.deepcopy(run);changed['request']['objective']='Changed report content';invalid.append(changed)
            invalid.append({**run,'oversized':'x'*128000})
            for changed in invalid:
                with self.assertRaises(ValueError):checked_agent(json.dumps(changed),run['run_id'],self.user['id'])
