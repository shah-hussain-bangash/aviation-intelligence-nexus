from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rag import source_coverage as sc,coverage_evaluation as ce,ollama,context_excerpts
from test_scoped_answers import FixtureKnowledge,MODELS


class SourceCoverageTests(unittest.TestCase):
    def test_policy_controls_include_a_false_refusal_and_unsupported_allow(self):
        rows,digest=ce.controls();self.assertEqual(len(rows),12);self.assertTrue(all(r['passed'] for r in rows));self.assertEqual(len(digest),64)
        paraphrase=next(r for r in rows if r['id']=='valid-paraphrase-refused')
        self.assertTrue(paraphrase['source_answerable']);self.assertEqual(paraphrase['observed']['decision'],'decline')
        short=next(r for r in rows if r['id']=='short-absent-subject')
        self.assertFalse(short['source_answerable']);self.assertEqual(short['observed']['required_terms'],[])
        self.assertEqual(sc.assess('Explain these probabilities.','The probability was measured.')['decision'],'allow')

    def test_missing_subject_declines_before_model_or_candidate_even_during_outage(self):
        k=FixtureKnowledge()
        with patch.object(context_excerpts,'answer',side_effect=AssertionError('No candidate')) as candidate,patch.object(ollama,'models',side_effect=TimeoutError('PRIVATE-ERROR')) as models:
            r=sc.answer('Why was a logistic coefficient chosen?','delay-v1',k)
        candidate.assert_not_called();models.assert_not_called()
        self.assertEqual(r['mode'],'source_coverage_declined');self.assertFalse(r['candidate_invoked'])
        self.assertIn('coefficient',r['source_coverage']['missing_terms']);self.assertEqual(r['claims'],[]);self.assertEqual(r['retrieved'],[])
        self.assertNotIn('generation_digest',r);self.assertNotIn('PRIVATE-ERROR',json.dumps(r));self.assertFalse(r['production_ready'])

    def test_scope_conflict_precedes_index_access(self):
        k=FixtureKnowledge()
        with patch.object(k,'load',side_effect=AssertionError('No index access')) as load:
            r=sc.answer('Tell me the delay-v1 threshold instead.','delay-v2',k)
        load.assert_not_called();self.assertEqual(r['mode'],'clarification_required')
        self.assertEqual(r['source_coverage']['decision'],'not_checked_scope_conflict')

    def test_allowed_unavailable_result_is_preserved_and_changed_index_rejected(self):
        k=FixtureKnowledge();original={'index_sha256':'fixed','mode':'evidence_only','generation_status':'unavailable_or_rejected','claims':[],'candidate_invoked':True}
        with patch.object(context_excerpts,'answer',return_value=deepcopy(original)) as candidate:
            r=sc.answer('Which validation month was used?','delay-v2',k)
        candidate.assert_called_once();self.assertEqual(r['generation_status'],'unavailable_or_rejected');self.assertEqual(r['source_coverage']['decision'],'allow')
        with patch.object(context_excerpts,'answer',return_value={**original,'index_sha256':'changed'}),self.assertRaises(ValueError):sc.answer('Which validation month was used?','delay-v2',k)

    def test_changed_index_after_refusal_and_invalid_request_fail_closed(self):
        k=FixtureKnowledge();first=k.load()
        with patch.object(k,'load',side_effect=[first,('changed',k.payload,None,None,None)]),self.assertRaises(ValueError):sc.answer('Explain the logistic coefficient.','delay-v1',k)
        for question,experiment in [('tiny','delay-v1'),('Which validation month?','../private')]:
            with self.subTest(question=question),self.assertRaises(ValueError):sc.answer(question,experiment,k)
        k.payload['chunks']=[]
        with self.assertRaises(ValueError):sc.answer('Which validation month?','delay-v2',k)


class CoverageEvaluationTests(unittest.TestCase):
    def suite(self,folder):
        cases=[
            {'id':'positive','experiment':'delay-v2','kind':'answerable','question':'Which validation month was used?','target_quote':'Validation: April 2025'},
            {'id':'paraphrase','experiment':'delay-v2','kind':'answerable','question':'Which chronological month was used?','target_quote':'Validation: April 2025'},
            {'id':'missing','experiment':'delay-v1','kind':'outside','question':'Why was a logistic coefficient chosen?','target_quote':None},
            {'id':'short','experiment':'delay-v1','kind':'outside','question':'How many spare tires were used?','target_quote':None},
            {'id':'conflict','experiment':'delay-v2','kind':'conflict','question':'Give the delay-v1 threshold instead.','target_quote':None}]
        path=Path(folder)/'suite.json';path.write_text(json.dumps({'format':'ain-scoped-cases-v1','cases':cases}),encoding='utf-8');return path
    def evaluate(self,fail=False):
        from rag import excerpt_v2
        def select(q,e,c):
            if fail:raise TimeoutError('PRIVATE-ERROR')
            return [{k:c[0][k] for k in ('citation','quote')}] if 'validation' in q else []
        with tempfile.TemporaryDirectory() as folder,patch.object(ollama,'models',return_value=MODELS),patch.object(excerpt_v2,'select',side_effect=select):
            return ce.evaluate(FixtureKnowledge(),self.suite(folder))

    def test_regression_counts_keep_false_refusal_and_policy_outcomes_separate(self):
        cases,_=ce.load_cases(ce.SUITE);self.assertEqual(len(cases),18);self.assertEqual(sum(c['kind']=='answerable' for c in cases),11)
        r=self.evaluate();m=r['metrics'];self.assertTrue(r['complete']);self.assertEqual(m['gold_quote_covered_cases'],1)
        self.assertEqual(m['answerable_coverage_refusals'],1);self.assertEqual(m['negative_coverage_refusals'],1)
        self.assertEqual(m['negative_model_abstentions'],1);self.assertEqual(m['negative_scope_clarifications'],1)
        self.assertEqual(m['negative_cases_returning_excerpts'],0);self.assertEqual(r['coverage_controls_passed'],12)
        self.assertFalse(r['human_review_complete']);self.assertFalse(r['semantic_answer_accuracy_measured'])

    def test_provider_failure_does_not_become_successful_coverage_refusal(self):
        r=self.evaluate(fail=True);m=r['metrics'];self.assertFalse(r['complete'])
        self.assertEqual(m['unavailable_or_rejected_cases'],2);self.assertEqual(m['negative_model_abstentions'],0)
        self.assertEqual(m['negative_coverage_refusals'],1);self.assertEqual(m['answerable_coverage_refusals'],1)
        self.assertNotIn('PRIVATE-ERROR',json.dumps(r))

    def test_forged_coverage_or_nonempty_refusal_cannot_verify(self):
        original=sc.answer
        for field in ('coverage','claims'):
            def bad(*a,**kw):
                r=original(*a,**kw)
                if field=='coverage' and r['mode']=='source_coverage_declined':r['source_coverage']['missing_terms']=[]
                if field=='claims' and r['mode']=='source_coverage_declined':r['claims']=[{'text':'invented'}]
                return r
            with self.subTest(field=field),patch.object(sc,'answer',side_effect=bad),self.assertRaises(ValueError):self.evaluate()

    def test_changed_code_or_invalid_controls_do_not_produce_verified_results(self):
        with patch.object(ce,'fingerprints',side_effect=[{'a':'before'},{'a':'after'}]),self.assertRaises(ValueError):self.evaluate()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'controls.json';path.write_text(json.dumps({'format':'ain-coverage-controls-v1','cases':[{'id':'one'},{'id':'one'}]}))
            with self.assertRaises(ValueError):ce.controls(path)

    def test_exclusive_progress_retains_failed_runs_without_internal_error_text(self):
        private=ce.ROOT/'.local';private.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as folder:
            path=Path(folder)/'report.json'
            with patch.object(ce,'evaluate',side_effect=RuntimeError('PRIVATE-ERROR')),self.assertRaises(RuntimeError):ce.run_to_file(path)
            journal=path.with_suffix('.json.progress.jsonl');saved=journal.read_bytes()
            self.assertIn(b'"event": "failed"',saved);self.assertNotIn(b'PRIVATE-ERROR',saved)
            with self.assertRaises(ValueError):ce.run_to_file(path)
            self.assertEqual(journal.read_bytes(),saved);self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):ce.run_to_file(Path(folder)/'outside.json')
