from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rag import context_excerpts as ce,context_replay as cr,ollama


class ContextExcerptTests(unittest.TestCase):
    def fixture(self,text=None,quote=None):
        reason='The probabilities were unreliable and the alert volume was excessive.'
        status='Do not serve this experimental model as an operational predictor.'
        text=text or reason+' '+status;quote=quote or status
        passage={'id':'one','source':'docs/DELAY_BASELINE.md','text':text,'start_line':1,'end_line':3}
        claim={'citation':'one','source':passage['source'],'text':quote,'quote':quote,'start_line':1,'end_line':3}
        return reason,passage,claim

    def test_explanation_includes_preceding_sentence_without_rewriting_or_mutation(self):
        reason,p,c=self.fixture();original=deepcopy(c)
        claims,count=ce.enrich('Why was this experiment rejected?',[c],{'one':p},p['source'])
        self.assertEqual(count,1);self.assertIn(reason,claims[0]['quote']);self.assertEqual(claims[0]['text'],p['text'])
        self.assertEqual(c,original);self.assertEqual(claims[0]['text'],claims[0]['quote'])

    def test_non_explanatory_repeated_and_separate_paragraph_quotes_are_not_expanded(self):
        reason,p,c=self.fixture()
        self.assertEqual(ce.enrich('What is the model status?',[c],{'one':p},p['source'])[1],0)
        for text in [reason+'\n\n'+c['quote'],c['quote']+' '+c['quote']]:
            _,p,c=self.fixture(text=text)
            self.assertEqual(ce.enrich('Explain the model status.',[c],{'one':p},p['source'])[1],0)

    def test_oversize_context_is_not_truncated_and_changed_source_fails(self):
        _,p,c=self.fixture(text='Long explanation '+('a'*390)+'. '+'Do not serve this experimental model as an operational predictor.')
        self.assertEqual(ce.enrich('Why was it rejected?',[c],{'one':p},p['source'])[1],0)
        for change in [{'source':'docs/DELAY_V2.md'},{'text':'Invented rewrite'},{'citation':'unknown'},{'start_line':99}]:
            with self.subTest(change=change),self.assertRaises(ValueError):ce.enrich('Why was it rejected?',[{**c,**change}],{'one':p},p['source'])

    def test_wrapper_retains_unavailable_and_clarification_without_context_or_extra_calls(self):
        for mode in ('evidence_only','clarification_required'):
            original={'mode':mode,'claims':[],'question':'Why was it rejected?','production_ready':False}
            with patch.object(ce.excerpt_v2,'answer',return_value=deepcopy(original)),patch.object(ollama,'models') as models:
                r=ce.answer('Why was it rejected?','delay-v1',object())
            models.assert_not_called();self.assertEqual(r['mode'],mode);self.assertEqual(r['context_added_count'],0)
        reason,p,c=self.fixture()
        class K:
            def load(self):return 'fixed',{'chunks':[p]},None,None,None
        original={'mode':'excerpts','question':'Why was it rejected?','claims':[c],'index_sha256':'fixed','source':p['source']}
        with patch.object(ce.excerpt_v2,'answer',return_value=deepcopy(original)):
            r=ce.answer(original['question'],'delay-v1',K())
        self.assertEqual(r['original_claims'],[c]);self.assertEqual(r['context_added_count'],1);self.assertIn(reason,r['claims'][0]['quote'])
        with patch.object(ce.excerpt_v2,'answer',return_value={**original,'index_sha256':'changed'}),self.assertRaises(ValueError):ce.answer(original['question'],'delay-v1',K())

    def test_saved_replay_uses_no_model_and_retains_negative_failure(self):
        # Use the real public baseline's identities but a tiny fake corpus and pinned-fixture reader.
        reason,p,c=self.fixture();case={'id':'positive','question':'Why was it rejected?','experiment':'delay-v1','kind':'answerable',
            'target_quote':reason,'claims':[c],'outcome':'excerpts','candidate_invoked':True,'gold_quote_covered':False}
        negative={**deepcopy(case),'id':'negative','question':'Why was an unknown coefficient selected?','kind':'outside','target_quote':None}
        report={'format':'ain-direct-evaluation-v2','index_sha256':'fixed','sources':[],'suite_sha256':'suite','cases':[case,negative]}
        report['metrics']=cr.summarize(report['cases'])
        class K:
            def load(self):return 'fixed',{'sources':[],'chunks':[p],'revision':'a'*40},None,None,None
        with patch.object(cr,'baseline',return_value=report),patch.object(ollama,'models',side_effect=AssertionError('No model calls')):
            r=cr.replay(K())
        self.assertEqual(r['generation_calls_in_this_replay'],0);self.assertEqual(r['metrics_after']['gold_quote_covered_cases'],1)
        self.assertEqual(r['metrics_after']['negative_cases_returning_excerpts'],1)
        self.assertFalse(r['human_review_complete']);self.assertEqual(report['cases'][0]['claims'][0]['quote'],c['quote'])

    def test_baseline_tampering_is_rejected_and_recorded_baseline_is_available(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'baseline.json';path.write_text('{}')
            with patch.object(cr,'BASELINE',path),self.assertRaises(ValueError):cr.baseline()
        # Real baseline is pinned independently of this fixture test.
        self.assertEqual(cr.baseline()['format'],'ain-direct-evaluation-v2')
