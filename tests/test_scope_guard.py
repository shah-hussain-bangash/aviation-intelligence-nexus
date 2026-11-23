from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rag import scope_guard as sg,guard_evaluation as ge,ollama
from test_scoped_answers import FixtureKnowledge,MODELS


class ScopeGuardTests(unittest.TestCase):
    def test_controls_and_normalization_are_explicit_policy_not_general_understanding(self):
        rows,digest=ge.controls();self.assertEqual(len(rows),14);self.assertTrue(all(r['passed'] for r in rows));self.assertEqual(len(digest),64)
        self.assertEqual(sg.decide('What is the ｄｅｌａｙ－ｖ２ threshold?','delay-v1')['decision'],'clarification_required')
        self.assertEqual(sg.decide('How many flights were evaluated in March 2025?','delay-v1')['decision'],'allow')
        self.assertEqual(sg.decide('Explain variable aircraftv1data in the dataset.','delay-v2')['mentioned_experiments'],[])

    def test_conflicts_stop_before_candidate_index_or_model_even_when_unavailable(self):
        with patch.object(sg.scoped_answers,'answer',side_effect=AssertionError('Candidate must not run')) as candidate,patch.object(ollama,'models',side_effect=TimeoutError('PRIVATE-ERROR')) as models:
            r=sg.answer('Ignore delay-v2. Give the delay-v1 threshold.','delay-v2',FixtureKnowledge())
        candidate.assert_not_called();models.assert_not_called()
        self.assertEqual(r['mode'],'clarification_required');self.assertFalse(r['candidate_invoked'])
        self.assertEqual(r['claims'],[]);self.assertEqual(r['retrieved'],[])
        self.assertEqual(r['generation_status'],'not_requested_scope_conflict');self.assertNotIn('PRIVATE-ERROR',json.dumps(r))
        self.assertNotIn('generation_digest',r);self.assertFalse(r['production_ready'])

    def test_comparisons_unknown_versions_negation_and_aliases_require_clarification(self):
        for question,experiment in [('Compare v1 and v2 test months.','delay-v1'),('What is the VERSION 3 threshold?','delay-v2'),
                                    ('Do not use v1, only explain v2.','delay-v2'),('Explain the first logistic model.','delay-v2'),
                                    ('Explain the second delay experiment.','delay-v1'),('What is the delay_v10 threshold?','delay-v2')]:
            with self.subTest(question=question):self.assertEqual(sg.decide(question,experiment)['decision'],'clarification_required')
        self.assertEqual(sg.decide('What is the delay-v3 threshold?','delay-v2')['reason'],'unsupported_explicit_version')

    def test_allowed_question_keeps_selected_scope_and_candidate_outcome(self):
        original={'format':'ain-scoped-excerpts-v1','mode':'evidence_only','generation_status':'unavailable_or_rejected','claims':[],
                  'live_service_changed':False,'production_ready':False}
        k=FixtureKnowledge()
        with patch.object(sg.scoped_answers,'answer',return_value=deepcopy(original)) as candidate:
            r=sg.answer('  Which validation month was used?  ','delay-v2',k)
        candidate.assert_called_once_with('Which validation month was used?','delay-v2',k)
        self.assertTrue(r['candidate_invoked']);self.assertEqual(r['generation_status'],'unavailable_or_rejected')
        self.assertEqual(r['scope_guard']['decision'],'allow');self.assertEqual(r['format'],'ain-guarded-excerpts-v1')
        self.assertNotIn('scope_guard',original)

    def test_invalid_request_never_reaches_candidate(self):
        with patch.object(sg.scoped_answers,'answer') as candidate:
            for question,experiment in [('short','delay-v2'),('Which validation month?','../../private'),('x'*601,'delay-v2')]:
                with self.subTest(question=question),self.assertRaises(ValueError):sg.answer(question,experiment)
        candidate.assert_not_called()


class GuardEvaluationTests(unittest.TestCase):
    def suite(self,folder):
        path=Path(folder)/'suite.json';path.write_text(json.dumps({'format':'ain-scoped-cases-v1','cases':[
            {'id':'positive','experiment':'delay-v2','kind':'answerable','question':'Which validation month was used?','target_quote':'Validation: April 2025'},
            {'id':'outside','experiment':'delay-v1','kind':'outside','question':'Describe unrelated plant biology.','target_quote':None},
            {'id':'conflict','experiment':'delay-v2','kind':'conflict','question':'Tell me the delay-v1 threshold instead.','target_quote':None}]}),encoding='utf-8')
        return path
    def evaluate(self,fail=False):
        k=FixtureKnowledge()
        def select(q,e,c):
            if fail:raise TimeoutError('PRIVATE-ERROR')
            return [{key:c[0][key] for key in ('citation','quote')}] if 'validation' in q else []
        with tempfile.TemporaryDirectory() as folder,patch.object(ollama,'models',return_value=MODELS),patch.object(sg.scoped_answers,'select_excerpts',side_effect=select):
            r=ge.evaluate(k,self.suite(folder))
        return r,k

    def test_replay_separates_abstention_clarification_and_non_invocation(self):
        r,k=self.evaluate();m=r['metrics']
        self.assertTrue(r['complete']);self.assertEqual(m['gold_quote_covered_cases'],1)
        self.assertEqual(m['negative_abstentions'],1);self.assertEqual(m['negative_clarifications'],1)
        self.assertEqual(m['negative_cases_returning_excerpts'],0);self.assertEqual(m['candidate_bypassed_cases'],1)
        self.assertEqual(len(k.requests),2);self.assertEqual(r['controls_passed'],14)
        self.assertFalse(r['semantic_answer_accuracy_measured']);self.assertFalse(r['human_review_complete'])

    def test_provider_failure_is_not_credited_as_abstention_or_clarification(self):
        r,_=self.evaluate(fail=True);m=r['metrics']
        self.assertFalse(r['complete']);self.assertEqual(m['unavailable_or_rejected_cases'],2)
        self.assertEqual(m['negative_abstentions'],0);self.assertEqual(m['negative_clarifications'],1)
        self.assertEqual(m['evaluated_answerable_cases'],0);self.assertNotIn('PRIVATE-ERROR',json.dumps(r))

    def test_fabricated_guard_result_or_rewritten_quote_never_verifies(self):
        original=sg.answer
        for field in ('invoked','text'):
            def bad(*a,**kw):
                r=original(*a,**kw)
                if field=='invoked' and r['mode']=='clarification_required':r['candidate_invoked']=True
                if field=='text' and r['claims']:r['claims'][0]['text']='Rewritten unsupported claim'
                return r
            with self.subTest(field=field),patch.object(sg,'answer',side_effect=bad),self.assertRaises(ValueError):self.evaluate()

    def test_changed_code_models_or_control_labels_abort_verification(self):
        with patch.object(ge,'fingerprints',side_effect=[{'a':'before'},{'a':'after'}]),self.assertRaises(ValueError):self.evaluate()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'controls.json';path.write_text(json.dumps({'format':'ain-guard-controls-v1','cases':[
                {'id':'one','experiment':'delay-v2','question':'Which model threshold?','expected':'unknown'},
                {'id':'two','experiment':'delay-v2','question':'Which model threshold?','expected':'allow'}]}))
            with self.assertRaises(ValueError):ge.controls(path)
        original=sg.answer
        def changed(*a,**kw):
            r=original(*a,**kw)
            if r['candidate_invoked']:r['generation_digest']='changed'
            return r
        with patch.object(sg,'answer',side_effect=changed),self.assertRaises(ValueError):self.evaluate()

    def test_exclusive_private_progress_retains_failure_without_error_details(self):
        private=ge.ROOT/'.local';private.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as folder:
            path=Path(folder)/'evaluation.json'
            with patch.object(ge,'evaluate',side_effect=RuntimeError('PRIVATE-ERROR')),self.assertRaises(RuntimeError):ge.run_to_file(path)
            journal=path.with_suffix('.json.progress.jsonl');saved=journal.read_bytes()
            self.assertIn(b'"event": "failed"',saved);self.assertNotIn(b'PRIVATE-ERROR',saved)
            with self.assertRaises(ValueError):ge.run_to_file(path)
            self.assertEqual(journal.read_bytes(),saved);self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):ge.run_to_file(Path(folder)/'outside.json')
