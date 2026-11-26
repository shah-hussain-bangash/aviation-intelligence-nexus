from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
import unittest
from uuid import uuid4
from rag.history import EvidenceHistory
from services.api.main import create_app
from services.api.research_cases import ResearchCaseService, AttachEvidence, CaseConflict
from tests.auth_helpers import authenticated_client
from tests import test_research_cases as cases
BASE=cases.BASE


class CaseEvidenceTests(unittest.TestCase):
    setUp=cases.ResearchCaseTests.setUp
    seed=cases.ResearchCaseTests.seed
    body=cases.ResearchCaseTests.body
    open_case=cases.ResearchCaseTests.open_case
    def evidence(self):
        result={'question':'SYNTHETIC evidence: what was the research scope?', 'mode':'evidence_only',
            'research_only':True,'operational_approval':False,'claims':[],
            'evidence':[{'id':'fixture-1','source':'SYNTHETIC fixture','text':'Synthetic passage only; no actual model retrieval.', 'source_sha256':'b'*64}],
            'generation':{'requested':False,'status':'not_requested'}}
        return EvidenceHistory(self.database).save(self.user,result)

    def attachment_body(self,client,run=None,version=1):
        run=run or self.evidence()
        source=next(s for s in client.get('/api/v1/research/case-evidence-sources').json()['sources'] if s['run_id']==run['run_id'])
        return {'expected_version':version,'evidence_run_id':run['run_id'],'evidence_sha256':source['sha256']}

    def test_attach_replay_retained_snapshot_and_recreated_service(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();body=self.attachment_body(client);path=BASE+'/'+case['id']
            attached=client.post(path+'/evidence',json=body);self.assertEqual(attached.status_code,200,attached.text)
            value=attached.json();self.assertEqual(value['version'],2);self.assertEqual(value['events'][1]['action'],'evidence')
            self.assertEqual(value['attachments'][0]['attached_version'],2)
            snapshot=client.get(path+'/evidence/'+body['evidence_run_id']).json()
            self.assertEqual(snapshot['sha256'],body['evidence_sha256']);self.assertFalse(snapshot['production_ready'])
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('DELETE FROM knowledge_runs')
            self.assertEqual(client.get(path+'/evidence/'+body['evidence_run_id']).json(),snapshot)
            self.assertTrue(client.post(path+'/evidence',json=body).json()['replayed'])
            client.post(path+'/events',json={'expected_version':2,'action':'close','note':'Synthetic outcome'})
            self.assertEqual(client.post(path+'/evidence',json=body).json()['version'],3)
            self.assertEqual(client.post(path+'/evidence',json={**body,'expected_version':2}).status_code,409)
            self.assertEqual(client.post(path+'/evidence',json=self.attachment_body(client,version=3)).status_code,409)
        service=ResearchCaseService(self.database,self.sidecar)
        with authenticated_client(create_app(self.database,research_cases=service)) as client:
            self.assertEqual(client.get(path+'/evidence/'+body['evidence_run_id']).json()['snapshot'],snapshot['snapshot'])

    def test_source_pins_roles_owner_and_query_boundaries(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();body=self.attachment_body(client);path=BASE+'/'+case['id']
            self.assertEqual(client.post(path+'/evidence',json={**body,'evidence_sha256':'0'*64}).status_code,409)
            self.assertEqual(client.post(path+'/evidence',json={**body,'expected_version':True}).status_code,422)
            self.assertEqual(client.post(path+'/evidence',json={**body,'operational_approval':True}).status_code,422)
            self.assertEqual(client.post(path+'/evidence',json=body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
            self.assertEqual(client.get('/api/v1/research/case-evidence-sources?owner=peer').status_code,422)
            self.assertEqual(client.post(path+'/evidence',json=body).status_code,200)
            for role in ('researcher','viewer'):
                self.app.state.auth_store.create_user('evidence-'+role,'synthetic-peer-password',role)
                login=client.post('/api/v1/auth/login',json={'username':'evidence-'+role,'password':'synthetic-peer-password'})
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.get('/api/v1/research/case-evidence-sources').json()['sources'],[])
                self.assertEqual(client.get(path+'/evidence/'+body['evidence_run_id']).status_code,404)
                self.assertEqual(client.post(path+'/evidence',json=body).status_code,403 if role=='viewer' else 404)

    def test_corruption_and_event_inventory_are_withheld(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();body=self.attachment_body(client);path=BASE+'/'+case['id']
            client.post(path+'/evidence',json=body)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute("UPDATE case_evidence SET snapshot_json='{}'")
            self.assertEqual(client.get(path).status_code,503)
            self.assertEqual(client.get(path+'/evidence/'+body['evidence_run_id']).status_code,503)
            self.assertEqual(client.post(path+'/events',json={'expected_version':2,'action':'close','note':'Blocked'}).status_code,503)

    def test_atomic_failure_and_concurrent_expected_version(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();body=self.attachment_body(client);path=BASE+'/'+case['id']
            with closing(sqlite3.connect(self.sidecar)) as db,db:
                db.execute("CREATE TRIGGER reject_fixture BEFORE INSERT ON case_evidence BEGIN SELECT RAISE(ABORT,'fixture'); END")
            self.assertEqual(client.post(path+'/evidence',json=body).status_code,503)
            self.assertEqual(client.get(path).json()['version'],1)
            with closing(sqlite3.connect(self.sidecar)) as db,db:db.execute('DROP TRIGGER reject_fixture')
            other=self.attachment_body(client)
            def attach(payload):
                try:self.service.attach_evidence(self.user,case['id'],AttachEvidence(**payload));return 'saved'
                except CaseConflict:return 'conflict'
            with ThreadPoolExecutor(max_workers=2) as workers:self.assertEqual(sorted(workers.map(attach,(body,other))),['conflict','saved'])
            self.assertEqual(len(client.get(path).json()['attachments']),1)

    def test_schema_one_migrates_without_losing_case_or_events(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json()
        with closing(sqlite3.connect(self.sidecar)) as db,db:
            db.execute('DROP TABLE case_agents');db.execute('DROP TABLE case_evidence');db.execute('PRAGMA user_version=1')
        service=ResearchCaseService(self.database,self.sidecar)
        self.assertEqual(service.get(self.user,case['id']),{k:v for k,v in case.items() if k!='replayed'})
        with closing(sqlite3.connect(self.sidecar)) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_source_size_identity_scope_and_changed_pins(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();run=self.evidence();body=self.attachment_body(client,run);path=BASE+'/'+case['id']+'/evidence'
            for patch in ({'operational_approval':True},{'run_id':str(uuid4())},{'question':'x'*601},{'extra':'x'*64000}):
                with closing(sqlite3.connect(self.database)) as db,db:db.execute('UPDATE knowledge_runs SET result_json=?',(json.dumps({**run,**patch}),))
                self.assertEqual(client.post(path,json=body).status_code,503)
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('UPDATE knowledge_runs SET result_json=?',(json.dumps({**run,'question':'Changed valid question'}),))
            self.assertEqual(client.post(path,json=body).status_code,409)

    def test_ten_attachment_limit_and_foreign_evidence_denied(self):
        with authenticated_client(self.app) as client:
            case=self.open_case(client).json();path=BASE+'/'+case['id']
            self.app.state.auth_store.create_user('foreign-evidence','synthetic-peer-password','researcher')
            with closing(sqlite3.connect(self.database)) as db:owner=db.execute("SELECT id FROM auth_users WHERE username='foreign-evidence'").fetchone()[0]
            run=self.evidence()
            with closing(sqlite3.connect(self.database)) as db,db:db.execute('UPDATE knowledge_runs SET owner_id=?',(owner,))
            from services.api.research_cases import digest
            foreign={'expected_version':1,'evidence_run_id':run['run_id'],'evidence_sha256':digest(run)}
            self.assertEqual(client.post(path+'/evidence',json=foreign).status_code,404)
            for version in range(1,11):
                body=self.attachment_body(client,version=version)
                self.assertEqual(client.post(path+'/evidence',json=body).status_code,200)
            extra=self.attachment_body(client,version=11)
            self.assertEqual(client.post(path+'/evidence',json=extra).status_code,409)
            saved=client.get(path).json();self.assertEqual(saved['version'],11);self.assertEqual(len(saved['attachments']),10)
