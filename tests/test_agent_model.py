import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from uuid import uuid4
from pydantic import ValidationError
from agents.runtime import Investigation,Investigator
from agents.store import AgentStore,Conflict
from agents.jobs import JobQueue
from agents.tools import definitions,execute
from agents.model_evidence import observation,valid_observation
from agents.quality import assess_report
from services.api.main import initialize
from rag import ollama


def extracts(question,evidence,**kwargs):
    row=evidence[0]
    return {'claims':[{'text':line,'quote':line,'citation':row['id']} for line in row['text'].splitlines()
        if line.startswith(('May test:','April-only input-reliance','Input reliance is not'))]}


class AgentModelTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'fixture.sqlite3';initialize(self.db)
        self.user={'id':'fixture-owner','username':'fixture-owner','role':'researcher'}
        self.store=AgentStore(self.db);self.runtime=Investigator(self.db,Mock(),self.store)
        self.request=Investigation(objective='Review frozen model errors, calibration and input reliance.',include_model_evidence=True,required_tools=['model_evidence'])

    def tearDown(self):self.folder.cleanup()

    def run_model(self,key=None):
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture-model'}),patch.object(ollama,'generate',side_effect=extracts),patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'model_evidence','arguments':{}}}],[]]) as planner:
            run=self.runtime.run(self.user,key or str(uuid4()),self.request)
            tool_messages=[json.loads(m['content']) for m in planner.call_args[0][0] if m['role']=='tool']
            self.assertTrue(tool_messages);self.assertNotIn('snapshot',tool_messages[0])
            self.assertIn('May test:',tool_messages[0]['evidence_text'])
            return run

    def test_opt_in_contract_preserves_legacy_hash_and_tool_arguments(self):
        old=Investigation(objective='Inspect existing historical research evidence.')
        self.assertNotIn('include_model_evidence',old.model_dump())
        self.assertEqual(old.model_dump(),Investigation.model_validate({**old.model_dump(),'include_model_evidence':False}).model_dump())
        for changes in [{'include_model_evidence':False},{'include_model_evidence':'true'},{'required_tools':[]},
                        {'required_tools':['model_evidence','flight_metrics','knowledge_search','route_history']}]:
            with self.assertRaises(ValidationError):Investigation.model_validate({**self.request.model_dump(),**changes})
        self.assertNotIn('model_evidence',[r['function']['name'] for r in definitions(False)])
        self.assertIn('model_evidence',[r['function']['name'] for r in definitions(False,False,True)])
        with patch('agents.tools.model_observation') as source:
            for args,request in [({'path':'anything'},self.request),({'period':'2025-05'},self.request),({},old)]:
                with self.assertRaises(ValueError):execute('model_evidence',args,request,self.db,None)
            source.assert_not_called()

    def test_actual_fixed_snapshot_is_retained_and_retry_does_not_call_model(self):
        key=str(uuid4());run=self.run_model(key)
        self.assertTrue(run['quality']['passed']);self.assertEqual(run['state'],'awaiting_review')
        self.assertTrue(valid_observation(run['steps'][0]['observation']))
        self.assertEqual(run['steps'][0]['observation']['snapshot']['periods']['test']['false_alerts'],241732)
        self.assertEqual(len(run['claims']),3);self.assertEqual(run['reviews'],[])
        with patch('agents.runtime.select_tools') as planner:
            replay=self.runtime.run(self.user,key,self.request);planner.assert_not_called()
        self.assertTrue(replay['replayed']);self.assertEqual(replay['run_id'],run['run_id'])
        self.assertFalse(run['operational_approval']);self.assertEqual(run['bounds']['max_tool_calls'],3)

    def test_unpermitted_or_nonempty_call_fails_before_tool_execution(self):
        old=Investigation(objective='No model evidence has been explicitly permitted.')
        for request,args in [(old,{}),(self.request,{'sql':'SELECT anything'})]:
            with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch('agents.runtime.select_tools',return_value=[{'function':{'name':'model_evidence','arguments':args}}]),patch('agents.tools.model_observation') as source:
                run=self.runtime.run(self.user,str(uuid4()),request);source.assert_not_called()
            self.assertEqual(run['state'],'failed');self.assertEqual(run['steps'],[])

    def test_changed_source_fails_closed_without_private_error(self):
        with patch('agents.model_evidence.load_explanations',side_effect=ValueError('private path')):
            self.assertFalse(valid_observation({}))
            with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'model_evidence','arguments':{}}}],[]]):
                run=self.runtime.run(self.user,str(uuid4()),self.request)
        self.assertEqual(run['state'],'failed');self.assertEqual(run['steps'][0]['state'],'failed')
        self.assertNotIn('private path',str(run));self.assertFalse(assess_report(run)['passed'])

    def test_saved_metrics_text_scope_and_cached_quality_cannot_bypass_review(self):
        run=self.run_model()
        for kind in ['count','bool','quote','source','scope','arguments','reliance']:
            changed=copy.deepcopy(run);obs=changed['steps'][0]['observation']
            if kind=='count':obs['snapshot']['periods']['test']['false_alerts']=1
            elif kind=='bool':obs['snapshot']['research_only']=1
            elif kind=='quote':obs['evidence_text']+=' Unsupported generated diagnosis.'
            elif kind=='source':obs['snapshot']['reliance_sha256']='0'*64
            elif kind=='scope':changed['request']['include_model_evidence']=False
            elif kind=='arguments':changed['steps'][0]['arguments']={'period':'2025-01'}
            else:obs['snapshot']['input_reliance']['groups'][0]['mean']['log_loss_increase']=999
            changed['quality']['passed']=True
            self.assertEqual(assess_report(changed)['model_evidence_mismatches'],['T1'])
            self.assertFalse(assess_report(changed)['passed']);self.store.checkpoint(changed)
            with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Fixture research check')
        changed=copy.deepcopy(run);changed['request']['required_tools']=[];changed['steps']=[]
        self.assertIn('model_evidence',assess_report(changed)['missing_tools'])

    def test_queue_keys_distinguish_explicit_model_permission(self):
        queue=JobQueue(self.store);key=str(uuid4())
        first=queue.enqueue(self.user,key,self.request)
        self.assertEqual(queue.enqueue(self.user,str(uuid4()),self.request)['run_id'],first['run_id'])
        old=Investigation(objective=self.request.objective)
        with self.assertRaises(Conflict):queue.enqueue(self.user,key,old)
        second=queue.enqueue(self.user,str(uuid4()),old)
        self.assertNotEqual(first['run_id'],second['run_id'])

    def test_missing_limitation_is_blocked_and_uses_one_bounded_repair(self):
        request=self.request;calls=[]
        def draft(question,evidence,**kwargs):
            calls.append(question)
            row=evidence[0]
            prefix='Input reliance is not' if question.startswith('Repair') else 'May test:'
            line=next(line for line in row['text'].splitlines() if line.startswith(prefix))
            return {'claims':[{'text':line,'quote':line,'citation':row['id']}]}
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch.object(ollama,'generate',side_effect=draft),patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'model_evidence','arguments':{}}}],[]]):
            run=self.runtime.run(self.user,str(uuid4()),request)
        self.assertEqual(len(calls),2);self.assertEqual(run['report_repair']['attempts'],1)
        self.assertTrue(run['quality']['passed'])
        run['claims']=[c for c in run['claims'] if not c['quote'].startswith('Input reliance')]
        self.assertEqual(assess_report(run)['model_limitations_uncited'],['T1'])
        self.assertFalse(assess_report(run)['passed'])
