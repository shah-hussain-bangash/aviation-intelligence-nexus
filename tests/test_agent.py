from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from auth_helpers import authenticated_client
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore, Conflict
from agents.tools import execute, flight_metrics
from services.api.main import create_app, initialize
from rag import ollama


def call(name,args=None): return {'function':{'name':name,'arguments':args or {}}}


def summary(question,evidence,**kwargs):
    quote=evidence[0]['text'].splitlines()[0]
    return {'claims':[{'text':quote,'citation':evidence[0]['id'],'quote':quote}]}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.db=Path(self.folder.name)/'test.sqlite3'; initialize(self.db)
        with closing(sqlite3.connect(self.db)) as db,db:
            for i,(cancelled,delay) in enumerate([(0,0),(0,20),(1,None),(0,None)]):
                db.execute('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,cancelled,diverted,arrival_delay_minutes) VALUES(?,?,?,?,?,?,?,?,?)',
                    ('BTS_REPORTING_CARRIER',str(i),'2025-05-10','AA','JFK','LAX',cancelled,0,delay))
            db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,cancelled,diverted,arrival_delay_minutes) VALUES('synthetic_test','X','2025-05-10','AA','JFK','LAX',0,0,99)")
        self.user={'id':'owner','username':'owner','role':'researcher'}
        self.store=AgentStore(self.db); self.knowledge=Mock()
        self.knowledge.query.return_value={'evidence':[{'id':'source1','text':'Delay models are research only and are not approved for airline decisions.','source':'docs/DELAY_V2.md','start_line':1,'end_line':1}],'index_sha256':'fixture'}
        self.runtime=Investigator(self.db,self.knowledge,self.store)
        self.model_patch=patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture-digest'});self.model_patch.start()
        self.summary_patch=patch.object(ollama,'generate',side_effect=summary);self.summary_patch.start()
        self.request=Investigation(objective='Report May flight counts and model limitations.',include_simulation=True)

    def tearDown(self):
        self.summary_patch.stop();self.model_patch.stop();self.folder.cleanup()

    def run_tools(self,calls,request=None,key=None):
        with patch('agents.runtime.select_tools',side_effect=[calls,[]]):
            return self.runtime.run(self.user,key or str(uuid4()),request or self.request)

    def test_sql_measurements_exclude_synthetic_cancelled_and_missing_targets(self):
        result=flight_metrics(self.db,'2025-05')
        self.assertEqual((result['records'],result['eligible'],result['delayed_15']),(4,2,1))
        self.assertEqual(result['arrival_delay_rate'],.5)
        missing=flight_metrics(self.db,'2025-04');self.assertFalse(missing['available'])

    def test_three_selected_tools_execute_and_produce_report_bound_checkpoint(self):
        run=self.run_tools([call('flight_metrics',{'month':'2025-05'}),call('knowledge_search',{'question':'What are model limitations?'}),call('gate_simulation')])
        self.assertEqual(run['state'],'awaiting_review');self.assertEqual(len(run['steps']),3)
        self.assertTrue(all(s['state']=='completed' for s in run['steps']))
        self.assertEqual(run['steps'][2]['observation']['result']['candidate']['verification']['assigned'],5)
        self.assertFalse(run['operational_approval']);self.assertEqual(len(run['report_sha256']),64)
        self.assertEqual(run['uncited_tools'],['T2','T3']);self.assertEqual(run['report_status'],'coverage_incomplete')
        self.assertEqual(self.store.recent(self.user)[0]['run_id'],run['run_id'])

    def test_shell_unknown_sql_and_month_scope_are_rejected_before_execution(self):
        for invalid in [call('shell',{'command':'anything'}),call('flight_metrics',{'sql':'DELETE FROM flights'}),call('flight_metrics',{'month':'2025-04'})]:
            run=self.run_tools([invalid]);self.assertEqual(run['state'],'failed');self.assertEqual(run['steps'],[])
        self.assertEqual(flight_metrics(self.db,'2025-05')['records'],4)

    def test_simulation_requires_user_opt_in_and_duplicate_calls_fail(self):
        run=self.run_tools([call('gate_simulation')],Investigation(objective='Inspect the flight data and limitations.',include_simulation=False))
        self.assertEqual(run['state'],'failed');self.assertEqual(run['steps'],[])
        run=self.run_tools([call('flight_metrics'),call('flight_metrics')])
        self.assertEqual(run['state'],'failed');self.assertEqual(run['steps'],[])

    def test_retry_keys_replay_without_reexecution_and_conflicting_input_is_rejected(self):
        key=str(uuid4());first=self.run_tools([call('flight_metrics')],key=key)
        with patch('agents.runtime.select_tools') as select:
            replay=self.runtime.run(self.user,key,self.request);select.assert_not_called()
        self.assertTrue(replay['replayed']);self.assertEqual(first['run_id'],replay['run_id'])
        with self.assertRaises(Conflict):self.runtime.run(self.user,key,Investigation(objective='A different research question here.'))

    def test_restart_marks_running_checkpoints_interrupted_without_tool_replay(self):
        run=self.store.begin(self.user,str(uuid4()),self.request.model_dump())
        run['steps'].append({'id':'T1','tool':'flight_metrics','arguments':{},'state':'running'});self.store.checkpoint(run)
        self.store.recover();saved=self.store.recent(self.user)[0]
        self.assertEqual(saved['state'],'interrupted');self.assertEqual(saved['steps'][0]['state'],'interrupted')

    def test_report_review_is_owner_scoped_hash_bound_and_cannot_apply_action(self):
        run=self.run_tools([call('flight_metrics')])
        with self.assertRaises(KeyError):self.store.review({'id':'other','username':'other','role':'researcher'},run['run_id'],run['report_sha256'],'reviewed','Checked counts')
        with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],'0'*64,'reviewed','Checked counts')
        original_text=run['claims'][0]['text'];run['claims'][0]['text']='Changed report contents';self.store.checkpoint(run)
        with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Checked counts')
        run['claims'][0]['text']=original_text;self.store.checkpoint(run)
        reviewed=self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Checked the source counts and limitations.')
        self.assertEqual(reviewed['state'],'reviewed');self.assertFalse(reviewed['operational_approval'])
        with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Second review')

    def test_unverifiable_summary_is_excluded_and_failed_tool_is_visible(self):
        with patch.object(ollama,'generate',return_value={'claims':[{'text':'There were 9999 flights','citation':'T1','quote':'An invented quotation that does not exist.'}]}):
            run=self.run_tools([call('flight_metrics')])
        self.assertEqual(run['claims'],[]);self.assertEqual(run['rejected_claims'],1)
        self.assertEqual(run['report_status'],'evidence_only')
        with patch('agents.runtime.tools.execute',side_effect=RuntimeError('Private diagnostic')):
            run=self.run_tools([call('flight_metrics')])
        self.assertEqual(run['state'],'failed');self.assertEqual(run['steps'][0]['state'],'failed')
        self.assertNotIn('Private diagnostic',str(run))

    def test_deadline_exhaustion_saves_failure_without_executing_tools(self):
        with patch('agents.runtime.time.monotonic',side_effect=[0,130]),patch('agents.runtime.select_tools') as select:
            run=self.runtime.run(self.user,str(uuid4()),self.request)
        select.assert_not_called();self.assertEqual(run['state'],'failed');self.assertEqual(run['error_type'],'TimeoutError')
        self.assertEqual(self.store.recent(self.user)[0]['run_id'],run['run_id'])

    def test_dashboard_read_snapshot_does_not_block_new_checkpoints(self):
        with closing(sqlite3.connect(self.db)) as reader:
            reader.execute('BEGIN');reader.execute('SELECT COUNT(*) FROM flights').fetchone()
            run=self.store.begin(self.user,str(uuid4()),self.request.model_dump())
            run['state']='interrupted';self.store.checkpoint(run)
            self.assertEqual(self.store.recent(self.user)[0]['state'],'interrupted')

    def test_api_requires_role_csrf_and_request_key_and_preserves_history(self):
        app=create_app(self.db)
        with authenticated_client(app) as client:
            with patch('agents.runtime.select_tools',side_effect=[[call('flight_metrics')],[]]):
                response=client.post('/api/v1/research/agent-run',json=self.request.model_dump(),headers={'Idempotency-Key':str(uuid4())})
            self.assertEqual(response.status_code,200);run=response.json();self.assertEqual(run['state'],'awaiting_review')
            self.assertEqual(client.post('/api/v1/research/agent-run',json=self.request.model_dump()).status_code,422)
            client.app.state.auth_store.create_user('agent-viewer','temporary-viewer-fixture-123','viewer')
            login=client.post('/api/v1/auth/login',json={'username':'agent-viewer','password':'temporary-viewer-fixture-123'})
            client.headers['X-CSRF-Token']=login.json()['csrf_token']
            self.assertEqual(client.post('/api/v1/research/agent-run',json=self.request.model_dump(),headers={'Idempotency-Key':str(uuid4())}).status_code,403)
            self.assertEqual(client.get('/api/v1/research/agent-history').json()['runs'],[])
            self.assertEqual(client.post('/api/v1/research/agent-review',json={'run_id':run['run_id'],'report_sha256':run['report_sha256'],'decision':'reviewed','note':'Checked evidence'}).status_code,403)
