import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4
from pydantic import ValidationError
from agents.runtime import Investigation,Investigator
from agents.store import AgentStore,Conflict,sha
from agents.jobs import JobQueue
from agents.tools import definitions,execute
from agents.duration_evidence import observation,valid_observation,LIMIT,required_quotes
from agents.quality import assess_report
from services.api.main import initialize
from services.api.agent_operations import snapshot
from rag import ollama


def extracts(question,evidence,**kwargs):
    row=evidence[0];quotes=required_quotes({'evidence_text':row['text']})
    return {'claims':[{'text':line,'quote':line,'citation':row['id']} for line in quotes.values()]}



class AgentDurationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'fixture.sqlite3';initialize(self.db)
        self.user={'id':'fixture-owner','username':'fixture-owner','role':'researcher'};self.store=AgentStore(self.db);self.runtime=Investigator(self.db,None,self.store)
        self.request=Investigation(objective='Review frozen negative duration regression and severe errors.',include_duration_evidence=True,required_tools=['duration_evidence'])

    def tearDown(self):self.folder.cleanup()

    def run_agent(self,key=None,generator=extracts):
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture-model'}),patch.object(ollama,'generate',side_effect=generator) as summary,patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'duration_evidence','arguments':{}}}],[]]) as planner:
            result=self.runtime.run(self.user,key or str(uuid4()),self.request)
            messages=[json.loads(m['content']) for m in planner.call_args[0][0] if m['role']=='tool'];self.assertNotIn('snapshot',messages[0])
            if result['steps'][0]['state']=='completed':self.assertIn(LIMIT,messages[0]['evidence_text'])
            return result,summary.call_count

    def test_opt_in_preserves_old_requests_and_enforces_three_tool_budget(self):
        old=Investigation(objective='Review historical research evidence.')
        self.assertNotIn('include_duration_evidence',old.model_dump());self.assertEqual(old.model_dump(),Investigation.model_validate({**old.model_dump(),'include_duration_evidence':False}).model_dump())
        for changes in [{'include_duration_evidence':False},{'include_duration_evidence':'true'},{'required_tools':[]},{'required_tools':['duration_evidence','model_evidence','flight_metrics','knowledge_search']}]:
            with self.assertRaises(ValidationError):Investigation.model_validate({**self.request.model_dump(),**changes})
        self.assertNotIn('duration_evidence',[r['function']['name'] for r in definitions(False)])
        self.assertIn('duration_evidence',[r['function']['name'] for r in definitions(False,False,False,False,True)])

    def test_unpermitted_or_nonempty_arguments_never_read_source(self):
        old=Investigation(objective='Review historical research evidence.')
        with patch('agents.tools.duration_observation') as source:
            for args,request in [({'sql':'anything'},self.request),({'period':'2026-01'},self.request),({},old)]:
                with self.assertRaises(ValueError):execute('duration_evidence',args,request,self.db,None)
            source.assert_not_called()

    def test_recorded_snapshot_retry_and_report_review_keep_exact_source(self):
        key=str(uuid4());run,calls=self.run_agent(key);self.assertEqual(calls,1);self.assertTrue(run['quality']['passed']);self.assertTrue(valid_observation(run['steps'][0]['observation']))
        self.assertEqual(run['steps'][0]['observation']['snapshot']['evaluation']['datasets']['test']['records'],597574);self.assertEqual(run['state'],'awaiting_review')
        with patch('agents.runtime.select_tools') as planner:replay=self.runtime.run(self.user,key,self.request);planner.assert_not_called()
        self.assertTrue(replay['replayed']);self.assertEqual(replay['report_sha256'],run['report_sha256'])
        reviewed=self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Fixture research review only.');self.assertEqual(reviewed['state'],'reviewed');self.assertFalse(reviewed['operational_approval']);self.assertFalse(reviewed['steps'][0]['observation']['snapshot']['evaluation']['research_check']['passed'])
        reviewed['execution']='local-background-queue-v1';self.store.checkpoint(reviewed)
        stats=snapshot(self.db,{'enabled':False,'alive':False,'last_poll':None,'error':None})
        self.assertEqual(stats['recent_window']['tools']['duration_evidence'],{'attempted':1,'completed':1,'failed_or_unfinished':0})

    def test_each_required_quote_is_enforced_with_one_bounded_repair(self):
        for label,quote in required_quotes(observation()).items():
            def missing(question,evidence,**kwargs):
                result=extracts(question,evidence,**kwargs);result['claims']=[c for c in result['claims'] if c['quote']!=quote];return result
            run,calls=self.run_agent(generator=missing);self.assertEqual(calls,2);self.assertFalse(run['quality']['passed']);self.assertEqual(run['quality']['duration_quotes_uncited'],['T1'])
            self.assertIn('T1:'+label,run['quality']['duration_required_quotes_missing'])
            with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','A required quotation is missing.')
            changed=self.store.review(self.user,run['run_id'],run['report_sha256'],'needs_changes','Include all mandatory source quotations.');self.assertEqual(changed['state'],'needs_changes')

    def test_tampered_snapshot_or_permission_cannot_pass_even_with_cached_quality(self):
        original,_=self.run_agent()
        for mutate in [lambda r:r['steps'][0]['observation']['snapshot']['evaluation']['research_check'].__setitem__('passed',True),lambda r:r['request'].__setitem__('include_duration_evidence',False),lambda r:r['steps'][0].__setitem__('arguments',{'url':'private'})]:
            run=copy.deepcopy(original);mutate(run);run['quality']={'passed':True};self.assertFalse(assess_report(run)['passed']);self.assertEqual(assess_report(run)['duration_evidence_mismatches'],['T1'])
            run['report_sha256']=sha({key:run[key] for key in ['request','steps','claims']});self.store.checkpoint(run)
            with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Even a resealed changed snapshot cannot be accepted.')
        changed=copy.deepcopy(observation());changed['evidence_text']+=' Extra unsupported finding.';self.assertFalse(valid_observation(changed))
        changed=copy.deepcopy(original);changed['steps'][0]['observation']['evidence_text']=None;self.assertFalse(assess_report(changed)['passed'])

    def test_source_failure_stops_without_fabricated_snapshot_and_releases_runtime_lock(self):
        with patch('agents.tools.duration_observation',side_effect=ValueError('changed source')):
            run,_=self.run_agent();self.assertFalse(run.get('quality',{}).get('passed'));self.assertEqual(run['steps'][0]['state'],'failed');self.assertNotIn('observation',run['steps'][0])
        healthy,_=self.run_agent();self.assertTrue(healthy['quality']['passed'])

    def test_queue_dedup_distinguishes_permission_and_retains_legacy_false_default(self):
        queue=JobQueue(self.store);old=Investigation(objective='Review recorded research evidence.')
        first=queue.enqueue(self.user,str(uuid4()),old);same=queue.enqueue(self.user,str(uuid4()),Investigation.model_validate({**old.model_dump(),'include_duration_evidence':False}));self.assertEqual(first['run_id'],same['run_id'])
        new=queue.enqueue(self.user,str(uuid4()),self.request);self.assertNotEqual(first['run_id'],new['run_id'])
