import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rag import excerpt_v2 as ev,direct_evaluation as de,ollama
from test_scoped_answers import FixtureKnowledge,MODELS,V2


class DirectExcerptTests(unittest.TestCase):
    def answer(self,response=None):
        response=response or {'done':True,'done_reason':'stop','message':{'content':'{"selections":[1]}'}}
        with patch.object(ollama,'models',return_value=MODELS),patch.object(ollama,'call',return_value=response):
            return ev.answer('Which validation month was used?','delay-v2',FixtureKnowledge())

    def test_candidate_constructs_exact_source_text_and_retains_provenance(self):
        r=self.answer();self.assertEqual(r['mode'],'excerpts');self.assertEqual(r['claims'][0]['text'],V2)
        self.assertEqual(r['claims'][0]['quote'],V2);self.assertEqual(r['claims'][0]['source'],'docs/DELAY_V2.md')
        self.assertEqual(r['selector_prompt_sha256'],hashlib.sha256(ev.SYSTEM.encode()).hexdigest())
        self.assertFalse(r['live_service_changed']);self.assertFalse(r['human_review_complete']);self.assertFalse(r['production_ready'])

    def test_explanation_rubric_is_not_gold_answer_and_transport_is_id_only(self):
        choices=[{'selection_id':1,'citation':'one','quote':'The experiment was rejected because uncertainty was excessive.'}]
        response={'done':True,'done_reason':'stop','message':{'content':'{"selections":[1]}'}}
        with patch.object(ollama,'call',return_value=response) as call:
            result=ev.select('Why was this research experiment rejected?','delay-v1',choices)
        args,kwargs=call.call_args;self.assertEqual(args[0],'chat');self.assertEqual(kwargs['timeout'],60)
        payload=args[1];self.assertEqual(set(payload['format']['properties']),{'selections'})
        self.assertIn('actual causal explanation',payload['messages'][0]['content'])
        self.assertNotIn('probability quality is worse',ev.SYSTEM)
        self.assertEqual(result[0]['quote'],choices[0]['quote'])

    def test_bad_output_and_provider_failure_are_not_valid_abstentions(self):
        for content in ['{"selections":[999]}','{"selections":[true]}','{"selections":[1],"text":"Invented"}','not json']:
            r=self.answer({'done':True,'done_reason':'stop','message':{'content':content}})
            self.assertEqual(r['generation_status'],'unavailable_or_rejected');self.assertEqual(r['mode'],'evidence_only');self.assertEqual(r['claims'],[])
        with patch.object(ollama,'models',return_value=MODELS),patch.object(ollama,'call',side_effect=TimeoutError('PRIVATE-ERROR')):
            r=ev.answer('Which validation month?','delay-v2',FixtureKnowledge())
        self.assertNotIn('PRIVATE-ERROR',json.dumps(r));self.assertEqual(r['claims'],[])
        r=self.answer({'done':True,'done_reason':'stop','message':{'content':'{"selections":[]}'}})
        self.assertEqual(r['mode'],'abstained');self.assertEqual(r['generation_status'],'completed')

    def test_conflict_bypasses_resources_and_selector_lock_recovers_after_rejection(self):
        k=FixtureKnowledge()
        with patch.object(k,'load',side_effect=AssertionError('No index access')) as load,patch.object(ollama,'call') as call,patch.object(ollama,'models') as models:
            r=ev.answer('Give the delay-v1 threshold instead.','delay-v2',k)
        load.assert_not_called();call.assert_not_called();models.assert_not_called();self.assertFalse(r['candidate_invoked'])
        self.assertEqual(r['mode'],'clarification_required')
        choices=[{'selection_id':1,'citation':'one','quote':V2}]
        with patch.object(ollama,'call',return_value={'done':False}),self.assertRaises(RuntimeError):ev.select('Which month?','delay-v2',choices)
        self.assertTrue(ollama.CHAT_LOCK.acquire(blocking=False));ollama.CHAT_LOCK.release()

    def test_changed_source_or_model_never_returns_verified_excerpts(self):
        k=FixtureKnowledge();query=k.query
        def changed(*a,**kw):
            r=query(*a,**kw);r['evidence'][0]['source']='docs/DELAY_BASELINE.md';return r
        with patch.object(k,'query',side_effect=changed),patch.object(ollama,'models',return_value=MODELS),self.assertRaises(ValueError):ev.answer('Which month?','delay-v2',k)
        with patch.object(ollama,'models',side_effect=[MODELS,{**MODELS,ollama.CHAT_MODEL:'changed'}]),patch.object(ev,'select',return_value=[]),self.assertRaises(ValueError):ev.answer('Which month?','delay-v2',FixtureKnowledge())


class DirectEvaluationTests(unittest.TestCase):
    def suite(self,folder):
        path=Path(folder)/'suite.json';path.write_text(json.dumps({'format':'ain-scoped-cases-v1','cases':[
            {'id':'positive','experiment':'delay-v2','kind':'answerable','question':'Which validation month was used?','target_quote':'Validation: April 2025'},
            {'id':'outside','experiment':'delay-v1','kind':'outside','question':'Describe unrelated plant biology.','target_quote':None},
            {'id':'conflict','experiment':'delay-v2','kind':'conflict','question':'Tell me the delay-v1 threshold instead.','target_quote':None}]}),encoding='utf-8')
        return path
    def evaluate(self,fail=False,negative_excerpt=False):
        def select(q,e,c):
            if fail:raise TimeoutError('PRIVATE-ERROR')
            return [{k:c[0][k] for k in ('citation','quote')}] if 'validation' in q or negative_excerpt else []
        with tempfile.TemporaryDirectory() as folder,patch.object(ollama,'models',return_value=MODELS),patch.object(ev,'select',side_effect=select):
            return de.evaluate(FixtureKnowledge(),self.suite(folder))

    def test_versioned_suite_and_replay_keep_semantic_review_pending(self):
        cases,_=de.load_cases(de.SUITE);self.assertEqual(len(cases),16);self.assertEqual(sum(c['kind']=='answerable' for c in cases),10)
        r=self.evaluate();m=r['metrics'];self.assertTrue(r['complete']);self.assertEqual(m['gold_quote_covered_cases'],1)
        self.assertEqual(m['negative_abstentions'],1);self.assertEqual(m['negative_clarifications'],1)
        self.assertEqual(r['controls_passed'],14);self.assertFalse(r['semantic_answer_accuracy_measured']);self.assertFalse(r['human_review_complete'])

    def test_rejected_generation_and_irrelevant_excerpts_do_not_receive_success_credit(self):
        r=self.evaluate(fail=True);self.assertFalse(r['complete']);self.assertEqual(r['metrics']['unavailable_or_rejected_cases'],2)
        self.assertEqual(r['metrics']['negative_abstentions'],0);self.assertEqual(r['metrics']['negative_clarifications'],1)
        self.assertNotIn('PRIVATE-ERROR',json.dumps(r))
        r=self.evaluate(negative_excerpt=True);self.assertEqual(r['metrics']['negative_cases_returning_excerpts'],1)

    def test_forged_prompt_identity_or_rewritten_claim_aborts_evaluation(self):
        original=ev.answer
        for change in ('prompt','text','bypass'):
            def bad(*a,**kw):
                r=original(*a,**kw)
                if change=='prompt' and r['candidate_invoked']:r['selector_prompt_sha256']='changed'
                if change=='text' and r['claims']:r['claims'][0]['text']='Invented explanation'
                if change=='bypass' and not r['candidate_invoked']:r['claims']=[{'text':'invented'}]
                return r
            with self.subTest(change=change),patch.object(ev,'answer',side_effect=bad),self.assertRaises(ValueError):self.evaluate()

    def test_changed_evaluator_code_cannot_finish_verified_run(self):
        with patch.object(de,'fingerprints',side_effect=[{'a':'before'},{'a':'after'}]),self.assertRaises(ValueError):self.evaluate()

    def test_private_progress_preserves_failures_and_refuses_replacement(self):
        private=de.ROOT/'.local';private.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as folder:
            path=Path(folder)/'report.json'
            with patch.object(de,'evaluate',side_effect=RuntimeError('PRIVATE-ERROR')),self.assertRaises(RuntimeError):de.run_to_file(path)
            journal=path.with_suffix('.json.progress.jsonl');saved=journal.read_bytes()
            self.assertIn(b'"event": "failed"',saved);self.assertNotIn(b'PRIVATE-ERROR',saved)
            with self.assertRaises(ValueError):de.run_to_file(path)
            self.assertEqual(journal.read_bytes(),saved);self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):de.run_to_file(Path(folder)/'report.json')
