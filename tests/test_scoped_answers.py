from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rag import ollama, scoped_answers as sa, scoped_evaluation as se

MODELS={ollama.EMBED_MODEL:'e'*64,ollama.CHAT_MODEL:'g'*64}
V2='- Validation: April 2025, used for model selection and the demonstration threshold.'
V1='The selected threshold is 0.15; this is not a business-cost or operational-capacity threshold.'


class FixtureKnowledge:
    def __init__(self):
        self.payload={'embedding_digest':MODELS[ollama.EMBED_MODEL],'revision':'a'*40,'sources':[],
                      'chunks':[{'id':'v1','source':sa.EXPERIMENTS['delay-v1'],'text':V1,'start_line':1,'end_line':1},
                                {'id':'v2','source':sa.EXPERIMENTS['delay-v2'],'text':V2,'start_line':1,'end_line':1}]}
        self.requests=[]
    def load(self):return 'fixed',self.payload,None,None,None
    def query(self,request,source_document):
        self.requests.append((request,source_document))
        evidence=[deepcopy(e) for e in self.payload['chunks'] if e['source']==source_document]
        return {'index_sha256':'fixed','evidence':evidence,'claims':[],'generation':{'requested':False},'mode':'evidence_only'}


class ScopedAnswerTests(unittest.TestCase):
    def answer(self,knowledge=None,selector=None,inventory=None):
        with patch.object(ollama,'models',side_effect=inventory or [MODELS,MODELS]), patch.object(sa,'select_excerpts',side_effect=selector or (lambda q,e,c:[{k:c[0][k] for k in ('citation','quote')}])):
            return sa.answer('Which month was used for validation?','delay-v2',knowledge or FixtureKnowledge())

    def test_explicit_experiment_limits_sources_and_constructs_verbatim_text(self):
        k=FixtureKnowledge();r=self.answer(k)
        self.assertEqual(k.requests[0][1],sa.EXPERIMENTS['delay-v2']);self.assertFalse(k.requests[0][0].generate)
        self.assertEqual(r['claims'][0]['text'],V2);self.assertEqual(r['claims'][0]['text'],r['claims'][0]['quote'])
        self.assertTrue(all(c['source']==sa.EXPERIMENTS['delay-v2'] for c in r['claims']))
        self.assertFalse(r['live_service_changed']);self.assertFalse(r['human_review_complete']);self.assertFalse(r['production_ready'])
        with patch.object(ollama,'models') as models,self.assertRaises(ValueError):sa.answer('Which month was used?','../private',k)
        models.assert_not_called()

    def test_choices_are_bound_exact_source_spans_and_deduplicate_per_citation(self):
        evidence=[{'id':'one','text':V2+'\n'+V2},{'id':'two','text':V2}]
        choices=sa.choices_for(evidence)
        self.assertEqual(len(choices),2);self.assertEqual([c['selection_id'] for c in choices],[1,2])
        for c in choices:self.assertIn(c['quote'],next(e['text'] for e in evidence if e['id']==c['citation']))
        with self.assertRaises(ValueError):sa.choices_for([{'id':'one','text':'\n'.join('Distinct source line number '+str(i) for i in range(201))}])

    def test_invalid_selector_ids_free_text_booleans_duplicates_are_rejected(self):
        choices=sa.choices_for([{'id':'one','text':V2}])
        for value in [{'selections':[True]},{'selections':[0]},{'selections':[2]},{'selections':[1,1]},
                      {'selections':[1],'text':'invented April'}, {'selections':['1']},{'claims':[]}]:
            with self.subTest(value=value),self.assertRaises(ValueError):sa.validate_selection(value,choices)
        self.assertEqual(sa.validate_selection({'selections':[]},choices),[])

    def test_selector_calls_fixed_local_chat_and_releases_lock_after_bad_output(self):
        choices=sa.choices_for([{'id':'one','text':V2}])
        response={'done':True,'done_reason':'stop','message':{'content':'{"selections":[1]}'}}
        with patch.object(ollama,'call',return_value=response) as call:
            selected=sa.select_excerpts('Which validation month?','delay-v2',choices)
            args,kwargs=call.call_args;self.assertEqual(args[0],'chat');self.assertEqual(kwargs['timeout'],60)
            self.assertEqual(args[1]['model'],ollama.CHAT_MODEL);self.assertEqual(args[1]['format']['properties']['selections']['items']['enum'],[1])
            self.assertEqual(selected[0]['quote'],V2)
        with patch.object(ollama,'call',return_value={**response,'done_reason':'length'}),self.assertRaises(RuntimeError):sa.select_excerpts('Which month?','delay-v2',choices)
        with patch.object(ollama,'call',return_value=response):self.assertTrue(sa.select_excerpts('Which month?','delay-v2',choices))
        self.assertTrue(ollama.CHAT_LOCK.acquire(blocking=False))
        try:
            with self.assertRaises(RuntimeError):sa.select_excerpts('Which month?','delay-v2',choices)
        finally:ollama.CHAT_LOCK.release()

    def test_unavailable_selection_is_not_a_valid_empty_answer(self):
        r=self.answer(selector=lambda *args: (_ for _ in ()).throw(TimeoutError('PRIVATE-ERROR')))
        self.assertEqual(r['generation_status'],'unavailable_or_rejected');self.assertEqual(r['mode'],'evidence_only')
        self.assertEqual(r['claims'],[]);self.assertNotIn('PRIVATE-ERROR',json.dumps(r))
        r=self.answer(selector=lambda *args:[])
        self.assertEqual(r['generation_status'],'completed');self.assertEqual(r['mode'],'abstained')

    def test_no_evidence_skips_generation(self):
        k=FixtureKnowledge();k.query=lambda *a,**kw:{'index_sha256':'fixed','evidence':[],'claims':[],'generation':{'requested':False},'mode':'abstained'}
        with patch.object(sa,'select_excerpts') as select,patch.object(ollama,'models',return_value=MODELS):
            r=sa.answer('Which validation month?','delay-v2',k)
        select.assert_not_called();self.assertEqual(r['generation_status'],'skipped_no_evidence')

    def test_cross_source_or_changed_passage_is_never_selected(self):
        for mutate in [lambda r:r['evidence'][0].update(source=sa.EXPERIMENTS['delay-v1']),lambda r:r['evidence'][0].update(text='Changed quote'),
                       lambda r:r.update(index_sha256='changed'),lambda r:r['generation'].update(requested=True)]:
            k=FixtureKnowledge();original=k.query
            def changed(*a,**kw):
                r=original(*a,**kw);mutate(r);return r
            k.query=changed
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):self.answer(k)

    def test_model_and_index_identity_changes_abort_candidate_result(self):
        with self.assertRaises(ValueError):self.answer(inventory=[MODELS,{**MODELS,ollama.CHAT_MODEL:'changed'}])
        k=FixtureKnowledge();original=k.load()
        with patch.object(k,'load',side_effect=[original,('changed',k.payload,None,None,None)]),self.assertRaises(ValueError):self.answer(k)
        with self.assertRaises(RuntimeError):self.answer(inventory=[{ollama.EMBED_MODEL:'changed'}])


class ScopedEvaluationTests(unittest.TestCase):
    def suite(self,folder):
        path=Path(folder)/'cases.json'
        path.write_text(json.dumps({'format':'ain-scoped-cases-v1','cases':[
            {'id':'positive','experiment':'delay-v2','kind':'answerable','question':'Which validation month was used?','target_quote':'Validation: April 2025'},
            {'id':'negative','experiment':'delay-v1','kind':'outside','question':'Describe unrelated plant biology.','target_quote':None}]}),encoding='utf-8')
        return path
    def evaluate(self,fail=False,negative_claim=False):
        k=FixtureKnowledge()
        def selector(q,e,c):
            if fail:raise TimeoutError('PRIVATE-ERROR')
            return [{key:c[0][key] for key in ('citation','quote')}] if 'validation' in q or negative_claim else []
        with tempfile.TemporaryDirectory() as folder,patch.object(ollama,'models',return_value=MODELS),patch.object(sa,'select_excerpts',side_effect=selector):
            return se.evaluate(k,self.suite(folder))

    def test_fixed_suite_and_exact_target_quote_coverage_are_not_semantic_accuracy(self):
        cases,digest=se.load_cases();self.assertEqual(len(cases),12);self.assertEqual(sum(c['kind']=='answerable' for c in cases),8);self.assertEqual(len(digest),64)
        r=self.evaluate();self.assertTrue(r['complete']);self.assertEqual(r['metrics']['gold_quote_covered_cases'],1)
        self.assertEqual(r['metrics']['negative_abstentions'],1);self.assertEqual(r['metrics']['wrong_source_excerpts'],0)
        self.assertFalse(r['semantic_answer_accuracy_measured']);self.assertFalse(r['human_review_complete'])
        self.assertEqual(r['cases'][0]['human_review_status'],'pending')

    def test_unavailable_and_negative_excerpts_remain_failures(self):
        r=self.evaluate(fail=True);self.assertFalse(r['complete']);self.assertEqual(r['metrics']['unavailable_or_rejected_cases'],2)
        self.assertEqual(r['metrics']['negative_abstentions'],0);self.assertNotIn('PRIVATE-ERROR',json.dumps(r))
        r=self.evaluate(negative_claim=True);self.assertEqual(r['metrics']['negative_cases_returning_excerpts'],1)
        self.assertEqual(r['metrics']['negative_abstentions'],0)

    def test_invalid_labels_changed_code_and_injected_claim_provenance_abort(self):
        with tempfile.TemporaryDirectory() as folder:
            path=self.suite(folder);d=json.loads(path.read_text());d['cases'][0]['target_quote']='Not in the selected source document';path.write_text(json.dumps(d))
            with self.assertRaises(ValueError):se.load_cases(path)
        with patch.object(se,'identities',side_effect=[{'a':'first'},{'a':'changed'}]),self.assertRaises(ValueError):self.evaluate()
        original=se.answer
        def bad(*a,**kw):
            r=original(*a,**kw)
            if r['claims']:r['claims'][0]['text']='Rewritten February claim'
            return r
        with patch.object(se,'answer',side_effect=bad),self.assertRaises(ValueError):self.evaluate()

    def test_failed_progress_is_preserved_and_existing_output_is_not_replaced(self):
        private=se.ROOT/'.local';private.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as folder:
            path=Path(folder)/'evaluation.json'
            with patch.object(se,'evaluate',side_effect=RuntimeError('PRIVATE-ERROR')),self.assertRaises(RuntimeError):se.run_to_file(path)
            journal=path.with_suffix('.json.progress.jsonl');saved=journal.read_bytes()
            self.assertNotIn(b'PRIVATE-ERROR',saved);self.assertIn(b'"event": "failed"',saved)
            with self.assertRaises(ValueError):se.run_to_file(path)
            self.assertEqual(journal.read_bytes(),saved);self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as folder,self.assertRaises(ValueError):se.run_to_file(Path(folder)/'outside.json')
