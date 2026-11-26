"""Deterministic contract checks; real local-model execution is a separate opt-in receipt."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from rag import index,ollama
from rag.service import Knowledge,Question
from pipelines import verify_case_journey as journey
from services.api.paths import ROOT


class LiveRagJourneyTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'.local').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='rag-journey-test-',dir=ROOT/'.local');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'index.json'
        self.models={ollama.EMBED_MODEL:'synthetic-embedding-digest',ollama.CHAT_MODEL:'synthetic-chat-digest'}

    def build(self):
        with patch.object(ollama,'models',return_value=self.models),patch.object(ollama,'embed',side_effect=lambda texts:[[1.0]*768 for _ in texts]):
            return index.build(destination=self.path)

    def qa(self):
        self.build()
        with patch.object(ollama,'models',return_value=self.models),patch.object(ollama,'embed',return_value=[[1.0]*768]):
            saved=Knowledge(self.path).query(Question(question='What limitations concern UAE airline transfer, weather and seasonal robustness?'))
        e=next(e for e in saved['evidence'] if len(e['text'])>=30);quote=e['text'][:100]
        saved.update(run_id=str(uuid4()),mode='generated',claims=[{'text':quote,'quote':quote,'citation':e['id']}],
            generation={'requested':True,'status':'completed','model':ollama.CHAT_MODEL,'model_digest':self.models[ollama.CHAT_MODEL],'answer_style':'verbatim_source_extracts'})
        return saved

    def test_explicit_index_preserves_active_target_and_has_valid_source_vectors(self):
        sentinel=self.root/'active.json';sentinel.write_text('SYNTHETIC ACTIVE INDEX SENTINEL')
        with patch.object(index,'INDEX',sentinel):result=self.build()
        pin,payload,*_=Knowledge(self.path).load()
        self.assertEqual(result['index_sha256'],pin);self.assertEqual(len(payload['sources']),6)
        self.assertEqual(result['dimensions'],768);self.assertEqual(sentinel.read_text(),'SYNTHETIC ACTIVE INDEX SENTINEL')

    def test_invalid_or_existing_index_path_refused_before_model_calls(self):
        self.path.write_text('preserve')
        with patch.object(ollama,'models') as models:
            for target in [self.path,ROOT/'outside-private.json',self.root/'..'/'escape.json',self.root/'index.txt']:
                with self.assertRaises(ValueError):index.build(destination=target)
            models.assert_not_called()
        self.assertEqual(self.path.read_text(),'preserve')

    def test_qa_contract_binds_real_retrieval_shape_and_canonical_repository_links(self):
        saved=self.qa();metadata=journey.validate_live_qa(saved,self.path,self.models)
        self.assertEqual(metadata['saved_run_id'],saved['run_id']);self.assertFalse(metadata['semantic_usefulness_assessed'])
        self.assertEqual(metadata['generation_digest'],self.models[ollama.CHAT_MODEL])
        self.assertTrue(all(e['source_url'].startswith('https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/') for e in saved['evidence']))

    def test_changed_citations_sources_models_and_empty_generation_are_rejected(self):
        saved=self.qa()
        mutations=[lambda s:s['claims'][0].update(citation='invented'),lambda s:s['claims'][0].update(quote='SYNTHETIC text absent from source'),
            lambda s:s['evidence'][0].update(source_url='https://untrusted.example/'),lambda s:s['evidence'][0].update(source_sha256='0'*64),
            lambda s:s['generation'].update(model_digest='changed'),lambda s:s.update(index_sha256='0'*64),
            lambda s:s['claims'][0].update(text='An unsupported paraphrase'),
            lambda s:s.update(claims=[]),lambda s:s.update(mode='evidence_only')]
        for mutate in mutations:
            changed=copy.deepcopy(saved);mutate(changed)
            with self.assertRaises((ValueError,RuntimeError)):journey.validate_live_qa(changed,self.path,self.models)

    def test_live_rag_requires_boolean_and_explicit_live_ai_before_state_creation(self):
        with patch.object(ollama,'models') as models:
            for kwargs in [{'live_rag':True},{'live_ai':True,'live_rag':'true'}]:
                for function in [journey.exercise,journey.verify]:
                    with self.assertRaises(ValueError):function(self.root/'unused',**kwargs)
            models.assert_not_called()
        self.assertFalse((self.root/'unused').exists())

    def test_verbatim_answer_style_is_explicit_and_strict_and_rejects_paraphrase(self):
        self.build();knowledge=Knowledge(self.path)
        request=Question(question='What limitations concern UAE airline transfer, weather and seasonal robustness?',generate=True,verbatim=True)
        self.assertNotIn('verbatim',Question(question=request.question).model_dump())
        with self.assertRaises(ValueError):Question(question=request.question,verbatim='true')
        with patch.object(ollama,'models',return_value=self.models),patch.object(ollama,'embed',return_value=[[1.0]*768]):
            evidence=knowledge.query(Question(question=request.question))['evidence'];e=evidence[0];quote=e['text'][:100]
            with patch.object(ollama,'generate',return_value={'claims':[{'text':quote,'quote':quote,'citation':e['id']}]}) as generated:
                saved=knowledge.query(request);self.assertEqual(saved['mode'],'generated');self.assertTrue(generated.call_args.kwargs['verbatim'])
            with patch.object(ollama,'generate',return_value={'claims':[{'text':'A paraphrase without extra numbers.','quote':quote,'citation':e['id']}]}):
                refused=knowledge.query(request);self.assertEqual(refused['mode'],'evidence_only');self.assertEqual(refused['claims'],[])

    def test_failed_live_rag_reports_unconfirmed_execution_and_no_fixture_qa_claim(self):
        def fail(directory,**kwargs):
            self.assertEqual(kwargs,{'live_ai':True,'live_rag':True});directory.mkdir(parents=True)
            raise RuntimeError('journey_check_failed:live_qa_binding')
        with patch.object(journey,'ROOT',self.root),patch.object(journey,'SOURCES',()),patch.object(index,'SOURCES',()),patch.object(journey,'exercise',side_effect=fail):
            report=journey.verify(self.root/'.local'/'failed-rag',live_ai=True,live_rag=True)
        self.assertFalse(report['passed']);self.assertTrue(report['live_rag_requested']);self.assertFalse(report['qa_fixture'])
        self.assertIsNone(report['retrieval_executed']);self.assertIsNone(report['qa_generation_executed'])

    def test_missing_embedding_model_blocks_before_index_or_database_creation(self):
        target=self.root/'no-embedding'
        with patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'fixture'}),patch.object(ollama,'embed') as embedded:
            with self.assertRaisesRegex(RuntimeError,'local_rag_models_unavailable'):
                journey.exercise(target,live_ai=True,live_rag=True)
            embedded.assert_not_called()
        self.assertFalse((target/'ain.sqlite3').exists());self.assertFalse((target/'knowledge/index.json').exists())


if __name__=='__main__':unittest.main()
