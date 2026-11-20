from contextlib import closing
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from pydantic import ValidationError
from agents.runtime import Investigation, Investigator
from agents.tools import definitions, execute
from agents.store import AgentStore, Conflict
from agents.jobs import JobQueue
from agents.quality import assess_report
from services.api.main import initialize
from services.api.route_history import valid_saved_profile, LookupBusy
from rag import ollama


def extract(question,evidence,**kwargs):
    return {'claims':[{'text':line,'quote':line,'citation':row['id']} for row in evidence[:3]
        for line in [next(line for line in row['text'].splitlines() if 'January-March 2025:' in line)]]}


class AgentRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.db=Path(self.folder.name)/'agent.sqlite3';initialize(self.db)
        with closing(sqlite3.connect(self.db)) as connection,connection:
            for i,(date,delay) in enumerate([('2025-01-15',0),('2025-01-15',20),('2025-05-15',60)]):
                connection.execute('INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination,cancelled,diverted,arrival_delay_minutes) VALUES(?,?,?,?,?,?,?,?,?)',('BTS_REPORTING_CARRIER',str(i),date,'AA','JFK','LAX',0,0,delay))
        self.user={'id':'fixture-owner','username':'fixture-owner','role':'researcher'}
        self.store=AgentStore(self.db);self.knowledge=Mock();self.runtime=Investigator(self.db,self.knowledge,self.store)
        self.request=Investigation(objective='Compare the selected historical route counts and uncertainty.',required_tools=['route_history'],route={'origin':'JFK','destination':'LAX'})

    def tearDown(self):
        self.folder.cleanup()

    def run_route(self,request=None,key=None):
        chosen=request or self.request
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture-model'}),patch.object(ollama,'generate',side_effect=extract),patch('agents.runtime.select_tools',side_effect=[[{'function':{'name':'route_history','arguments':chosen.route.model_dump()}}],[],[]]):
            return self.runtime.run(self.user,key or str(uuid4()),chosen)

    def test_scoped_contract_preserves_old_payload_and_three_tool_limit(self):
        legacy=Investigation(objective='Inspect the existing monthly historical data.')
        self.assertNotIn('route',legacy.model_dump())
        self.assertEqual(Investigation.model_validate(legacy.model_dump()).model_dump(),legacy.model_dump())
        for changes in [{'route':None},{'route':{'origin':'JFK','destination':'JFK'}},{'route':{'origin':'jfk','destination':'LAX'}},
                        {'route':{'origin':'JFK','destination':'LAX','sql':'anything'}},
                        {'required_tools':[]},{'required_tools':['route_history','flight_metrics','knowledge_search','gate_simulation'],'include_simulation':True}]:
            with self.assertRaises(ValidationError):Investigation.model_validate({**self.request.model_dump(),**changes})

    def test_tool_is_opt_in_and_model_cannot_replace_airports(self):
        self.assertNotIn('route_history',[row['function']['name'] for row in definitions(False)])
        self.assertIn('route_history',[row['function']['name'] for row in definitions(False,True)])
        with patch('agents.tools.lookup_route') as query:
            for arguments in [{'origin':'SFO','destination':'LAX'},{'sql':'SELECT 1'},{'month':'2025-04'}]:
                with self.assertRaises(ValueError):execute('route_history',arguments,self.request,self.db,self.knowledge)
            with self.assertRaises(ValueError):execute('route_history',{},Investigation(objective='No route has been explicitly selected.'),self.db,self.knowledge)
            query.assert_not_called()
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture-model'}),patch('agents.runtime.select_tools',return_value=[{'function':{'name':'route_history','arguments':{'origin':'SFO','destination':'LAX'}}}]):
            rejected=self.runtime.run(self.user,str(uuid4()),self.request)
        self.assertEqual(rejected['state'],'failed');self.assertEqual(rejected['steps'],[])

    def test_real_sql_tool_saves_structured_counts_intervals_and_replays(self):
        key=str(uuid4());run=self.run_route(key=key)
        self.assertEqual(run['state'],'awaiting_review');self.assertTrue(run['quality']['passed'])
        profile=run['steps'][0]['observation']['profile']
        self.assertTrue(valid_saved_profile(profile,self.request.route.model_dump()))
        self.assertEqual([row['flights'] for row in profile['periods']],[2,1])
        self.assertIn('nominal 95% Wilson',run['steps'][0]['observation']['evidence_text'])
        self.assertEqual(run['bounds']['max_tool_calls'],3)
        self.assertEqual(run['bounds']['first_planner_timeout_seconds'],45)
        self.assertEqual(run['bounds']['later_planner_timeout_seconds'],20)
        self.assertEqual(run['bounds']['deadline_seconds'],120)
        with patch('agents.runtime.select_tools') as planner:
            replay=self.runtime.run(self.user,key,self.request);planner.assert_not_called()
        self.assertEqual(replay['run_id'],run['run_id']);self.assertTrue(replay['replayed'])
        self.assertFalse(run['operational_approval'])

    def test_scope_or_interval_tampering_blocks_research_acceptance(self):
        run=self.run_route()
        for mutation in ['route','interval','rate','metric_bool','arguments']:
            changed=copy.deepcopy(run);profile=changed['steps'][0]['observation']['profile']
            if mutation=='route':profile['route']['origin']='SFO'
            elif mutation=='interval':profile['periods'][0]['delay_15']['wilson_95'][1]=.1
            elif mutation=='rate':profile['periods'][0]['delay_15']['rate']=.1
            elif mutation=='metric_bool':profile['periods'][0]['delay_15']['events']=True
            else:changed['steps'][0]['arguments']['origin']='SFO'
            changed['quality']['passed']=True
            self.assertEqual(assess_report(changed)['route_scope_mismatches'],['T1'])
            self.assertFalse(assess_report(changed)['passed'])
            self.store.checkpoint(changed)
            with self.assertRaises(Conflict):self.store.review(self.user,run['run_id'],run['report_sha256'],'reviewed','Fixture source check')

    def test_missing_or_busy_route_never_creates_available_route_evidence(self):
        request=Investigation(objective='Compare an unobserved historical route.',required_tools=['route_history'],route={'origin':'AAA','destination':'BBB'})
        run=self.run_route(request)
        self.assertEqual(run['state'],'failed');self.assertFalse(run['steps'][0]['observation']['available'])
        self.assertFalse(assess_report(run)['passed'])
        with patch('agents.tools.lookup_route',side_effect=LookupBusy('private diagnostic')):
            failed=self.run_route()
        self.assertEqual(failed['state'],'failed');self.assertEqual(failed['steps'][0]['state'],'failed')
        self.assertNotIn('private diagnostic',str(failed))

    def test_saved_queue_deduplicates_only_identical_explicit_scope(self):
        queue=JobQueue(self.store);key=str(uuid4())
        first=queue.enqueue(self.user,key,self.request)
        self.assertEqual(queue.enqueue(self.user,str(uuid4()),self.request)['run_id'],first['run_id'])
        changed=Investigation.model_validate({**self.request.model_dump(),'route':{'origin':'SFO','destination':'LAX'}})
        with self.assertRaises(Conflict):queue.enqueue(self.user,key,changed)
        second=queue.enqueue(self.user,str(uuid4()),changed)
        self.assertNotEqual(first['run_id'],second['run_id'])
        self.assertEqual(second['request']['route']['origin'],'SFO')
