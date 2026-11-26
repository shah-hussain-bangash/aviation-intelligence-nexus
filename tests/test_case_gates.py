from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import copy
from datetime import datetime,timedelta,timezone
import json
import sqlite3
import unittest
from uuid import uuid4
from unittest.mock import patch
from agents.tools import gate_sample
from optimization.gates import optimize
from optimization.history import GateRunStore
from optimization.reviews import GateReview
from services.api.main import create_app
from services.api.research_cases import ResearchCaseService,CaseConflict,digest,ChangeCase
from services.api.case_gates import AttachGate,checked_gate
from tests.auth_helpers import authenticated_client
from tests import test_research_cases as cases
from tests import test_case_agents as agent_tests
BASE=cases.BASE
NOW=datetime(2026,11,20,12,tzinfo=timezone.utc)


class CaseGateTests(unittest.TestCase):
    setUp=cases.ResearchCaseTests.setUp
    seed=cases.ResearchCaseTests.seed
    body=cases.ResearchCaseTests.body
    open_case=cases.ResearchCaseTests.open_case
    user_record=agent_tests.CaseAgentTests.user_record

    def gate(self,owner=None,review=True):
        owner=owner or self.user;store=GateRunStore(self.database,clock=lambda:NOW)
        saved=store.save(owner,str(uuid4()),optimize(gate_sample()))
        if review:
            store.clock=lambda:NOW+timedelta(minutes=1)
            store.review(owner,GateReview(run_id=saved['run_id'],proposal_sha256=saved['proposal_sha256'],review_key=uuid4(),decision='needs_changes',note='SYNTHETIC fixture review; not a real gate decision',acknowledged=True))
        with closing(sqlite3.connect(self.database)) as db:return json.loads(db.execute('SELECT result_json FROM gate_runs WHERE id=?',(saved['run_id'],)).fetchone()[0])

    def payload(self,run,version=1):return {'expected_version':version,'gate_run_id':run['run_id'],'gate_sha256':digest(run)}

    def test_attach_retention_replay_closure_and_no_solver_rerun(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.gate();body=self.payload(run);path=BASE+'/'+case['id'];endpoint=path+'/gates/'+run['run_id']
            with patch('scipy.optimize.milp',side_effect=AssertionError('Attachment must not solve')):
                saved=client.post(path+'/gates',json=body);self.assertEqual(saved.status_code,200,saved.text)
                snapshot=client.get(endpoint).json()
            self.assertEqual(snapshot['snapshot'],run);self.assertEqual(snapshot['data_kind'],'synthetic');self.assertEqual(snapshot['review_state'],'needs_changes')
            self.assertEqual(snapshot['candidate_assigned']+snapshot['candidate_unassigned'],snapshot['flight_count'])
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('DELETE FROM gate_runs WHERE id=?',(run['run_id'],))
            self.assertEqual(client.get(endpoint).json(),snapshot)
            self.assertTrue(client.post(path+'/gates',json=body).json()['replayed'])
            self.assertEqual(client.post(path+'/gates',json={**body,'expected_version':2}).status_code,409)
            client.post(path+'/events',json={'expected_version':2,'action':'close','note':'SYNTHETIC outcome; no allocation'})
            self.assertEqual(client.post(path+'/gates',json=body).json()['version'],3)
            self.assertEqual(client.post(path+'/gates',json=self.payload(self.gate(),3)).status_code,409)
        with authenticated_client(create_app(self.database,research_cases=ResearchCaseService(self.database,self.sidecar))) as client:
            self.assertEqual(client.get(endpoint).json()['snapshot'],run)

    def test_owner_roles_csrf_and_request_boundaries(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.gate();body=self.payload(run);path=BASE+'/'+case['id']
            self.assertEqual(client.post(path+'/gates',json=body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
            for change in ({'expected_version':True},{'owner_id':'other'},{'operational_approval':True}):self.assertEqual(client.post(path+'/gates',json={**body,**change}).status_code,422)
            self.assertEqual(client.get('/api/v1/research/case-gate-sources?owner=other').status_code,422)
            foreign=self.user_record('gate-foreign','researcher');foreign_run=self.gate(owner=foreign)
            self.assertEqual(client.post(path+'/gates',json=self.payload(foreign_run)).status_code,404)
            self.assertEqual(client.post(path+'/gates',json=body).status_code,200)
            for name,role in [('gate-peer','researcher'),('gate-viewer','viewer')]:
                self.user_record(name,role);login=client.post('/api/v1/auth/login',json={'username':name,'password':'synthetic-agent-password'});client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.get('/api/v1/research/case-gate-sources').json()['sources'],[])
                self.assertEqual(client.get(path+'/gates/'+run['run_id']).status_code,404)
                self.assertEqual(client.post(path+'/gates',json=body).status_code,403 if role=='viewer' else 404)

    def test_unreviewed_expired_proposal_excluded_and_old_decision_retained(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();pending=self.gate(review=False)
            self.assertEqual(client.get('/api/v1/research/case-gate-sources').json()['sources'],[])
            self.assertEqual(client.post(BASE+'/'+case['id']+'/gates',json=self.payload(pending)).status_code,503)
            reviewed=self.gate();self.assertEqual(checked_gate(json.dumps(reviewed),reviewed['run_id'])['review']['decision'],'needs_changes')
            self.assertEqual(len(client.get('/api/v1/research/case-gate-sources').json()['sources']),1)

    def test_changed_pins_source_metadata_and_captured_hash_withheld(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.gate();body=self.payload(run);path=BASE+'/'+case['id']
            self.assertEqual(client.post(path+'/gates',json={**body,'gate_sha256':'0'*64}).status_code,409)
            with closing(sqlite3.connect(self.database)) as db,db:db.execute("UPDATE gate_runs SET scenario_hash=?",('0'*64,))
            self.assertEqual(client.post(path+'/gates',json=body).status_code,503)
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('UPDATE gate_runs SET scenario_hash=?',(run['scenario_sha256'],))
            self.assertEqual(client.post(path+'/gates',json=body).status_code,200)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute("UPDATE case_gates SET snapshot_json='{}'")
            self.assertEqual(client.get(path).status_code,503);self.assertEqual(client.get(path+'/gates/'+run['run_id']).status_code,503)

    def test_plan_receipt_scope_and_size_validation(self):
        from optimization.reviews import proposal_hash,digest as review_digest
        with authenticated_client(self.app) as client:
            self.open_case(client);run=self.gate();invalid=[]
            for change in ('plan','receipt','scope','size'):
                item=copy.deepcopy(run)
                if change=='plan':item['candidate']['verification']['assigned']=-1
                if change=='receipt':item['review']['note']='Altered unsigned receipt'
                if change=='scope':item['scenario']['data_kind']='live'
                if change=='size':item['extra']='x'*64000
                if change in ('plan','scope'):
                    item['proposal_sha256']=proposal_hash(item);item['review']['proposal_sha256']=item['proposal_sha256']
                    item['review']['decision_sha256']=review_digest({k:v for k,v in item['review'].items() if k!='decision_sha256'})
                invalid.append(item)
            for item in invalid:
                with self.assertRaises((ValueError,KeyError)):checked_gate(json.dumps(item),run['run_id'])

    def test_atomic_failure_contention_and_five_proposal_limit(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();path=BASE+'/'+case['id'];body=self.payload(self.gate())
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute("CREATE TRIGGER reject_gate BEFORE INSERT ON case_gates BEGIN SELECT RAISE(ABORT,'fixture'); END")
            self.assertEqual(client.post(path+'/gates',json=body).status_code,503);self.assertEqual(client.get(path).json()['version'],1)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute('DROP TRIGGER reject_gate')
            other=self.payload(self.gate())
            def attach(payload):
                try:self.service.attach_gate(self.user,case['id'],AttachGate(**payload));return 'saved'
                except CaseConflict:return 'conflict'
            with ThreadPoolExecutor(max_workers=2) as workers:self.assertEqual(sorted(workers.map(attach,(body,other))),['conflict','saved'])
            for version in range(2,6):self.assertEqual(client.post(path+'/gates',json=self.payload(self.gate(),version)).status_code,200)
            self.assertEqual(client.post(path+'/gates',json=self.payload(self.gate(),6)).status_code,409)
            self.assertEqual(len(client.get(path).json()['gate_links']),5)

    def test_schema_three_preserves_agent_and_note_history(self):
        from services.api.case_agents import AttachAgent
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();agent=agent_tests.CaseAgentTests.agent(self)
            self.service.attach_agent(self.user,case['id'],AttachAgent(expected_version=1,agent_run_id=agent['run_id'],agent_sha256=digest(agent)))
            self.service.change(self.user,case['id'],ChangeCase(expected_version=2,action='note',note='SYNTHETIC migration note'))
            before=self.service.get(self.user,case['id'])
        with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute('DROP TABLE case_gates');db.execute('PRAGMA user_version=3')
        service=ResearchCaseService(self.database,self.sidecar);self.assertEqual(service.get(self.user,case['id']),before)
        with closing(sqlite3.connect(self.sidecar)) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)

    def test_missing_gate_snapshot_cannot_leave_an_unbound_event(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();client.post(BASE+'/'+case['id']+'/gates',json=self.payload(self.gate()))
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute('DELETE FROM case_gates')
            self.assertEqual(client.get(BASE+'/'+case['id']).status_code,503)
