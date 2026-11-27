import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agents.evaluate_june_agent import evaluate, ROOT
from agents.june_evidence import observation, required_quotes
from rag import ollama


class JuneAgentProviderCheckTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(dir=ROOT/'.local')
        self.base=Path(self.folder.name)
        self.planner_calls=0;self.provider_calls=[]

    def tearDown(self):
        self.folder.cleanup()

    def provider(self, route, payload=None, **kwargs):
        self.provider_calls.append(route)
        if route=='tags':
            return {'models':[{'name':ollama.CHAT_MODEL,'digest':'e'*64}]}
        if 'tools' in payload:
            self.planner_calls+=1
            calls=[{'function':{'name':'june_evidence','arguments':{}}}] if self.planner_calls==1 else []
            return {'done':True,'done_reason':'stop','message':{'tool_calls':calls,'content':'Evidence collected'}}
        quotes=required_quotes(observation()).values()
        claims=[{'text':q,'quote':q,'citation':'T1'} for q in quotes]
        return {'done':True,'done_reason':'stop','message':{'content':json.dumps({'claims':claims})}}

    def test_real_runtime_with_simulated_provider_retains_trace_quotes_and_network_free_replay(self):
        with patch.object(ollama,'call',side_effect=self.provider):
            result=evaluate(self.base/'fresh')
        self.assertTrue(result['passed']);self.assertTrue(all(result['checks'].values()))
        self.assertEqual(len(result['provider_calls']),len(self.provider_calls))
        self.assertEqual([r['purpose'] for r in result['provider_calls'] if r['route']=='chat'],['planner','planner','generator'])
        self.assertEqual(result['run']['model']['digest'],'e'*64)
        self.assertEqual(result['run']['reviews'],[]);self.assertEqual(result['run']['state'],'awaiting_review')
        self.assertFalse(result['evaluation_repeated']);self.assertFalse(result['production_ready'])
        self.assertEqual(json.loads((self.base/'fresh/evaluation.json').read_text())['checks'],result['checks'])
        self.assertNotIn('payload',json.dumps(result['provider_calls']))

    def test_existing_outside_and_parent_relative_paths_never_contact_provider(self):
        with patch.object(ollama,'call') as provider:
            for path in (self.base,ROOT/'outputs/not-private',self.base/'..'/'escape'):
                with self.assertRaises(ValueError):evaluate(path)
            provider.assert_not_called()

    def test_provider_failure_retains_failed_receipt_without_exception_details(self):
        with patch.object(ollama,'call',side_effect=RuntimeError('private transport details')):
            result=evaluate(self.base/'failed')
        self.assertFalse(result['passed'])
        self.assertTrue((self.base/'failed/evaluation.json').exists())
        self.assertEqual(result['provider_calls'][0]['state'],'failed')
        self.assertNotIn('private transport details',json.dumps(result))
        with patch.object(ollama,'call') as provider:
            with self.assertRaises(ValueError):evaluate(self.base/'failed')
            provider.assert_not_called()

    def test_incomplete_generation_is_retained_and_not_claimed_as_success(self):
        def incomplete(route,payload=None,**kwargs):
            response=self.provider(route,payload,**kwargs)
            if route=='chat' and 'tools' not in payload:response['done_reason']='length'
            return response
        with patch.object(ollama,'call',side_effect=incomplete):
            result=evaluate(self.base/'incomplete')
        self.assertFalse(result['passed'])
        self.assertFalse(result['checks']['actual_planner_and_generator_responses'])
        self.assertEqual(result['run']['state'],'failed')
        self.assertFalse(result['run']['reviews'])

    def test_changed_public_evidence_is_refused_before_state_or_provider_access(self):
        target=self.base/'changed'
        with patch('agents.evaluate_june_agent.load_june_evaluation',side_effect=ValueError('changed report')),patch.object(ollama,'call') as provider:
            with self.assertRaises(ValueError):evaluate(target)
            provider.assert_not_called()
        self.assertFalse(target.exists())
