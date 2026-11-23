from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rag import generation_diagnostics as gd
from rag import ollama

MODELS = {ollama.EMBED_MODEL: 'e' * 64, ollama.CHAT_MODEL: 'g' * 64}
QUOTE = 'Sessions expire after eight hours'


class KnowledgeFixture:
    def __init__(self, outcome='generated', fail=False, tamper=None, outside_evidence=False):
        self.outcome, self.fail, self.tamper, self.outside_evidence = outcome, fail, tamper, outside_evidence
        self.requests = []
        self.chunk = {'id': 'fixture', 'source': 'docs/LOCAL_IDENTITY.md', 'text': QUOTE, 'start_line': 1, 'end_line': 1}
        self.payload = {'chunks': [self.chunk], 'revision': 'a' * 40, 'embedding_digest': MODELS[ollama.EMBED_MODEL], 'sources': []}

    def load(self):
        return 'fixed', self.payload, None, None, None

    def query(self, request):
        self.requests.append(request)
        if self.fail:
            raise TimeoutError('PRIVATE-DETAILS')
        evidence = [deepcopy(self.chunk)] if 'sessions' in request.question.lower() or self.outside_evidence else []
        claims = [{'text': QUOTE, 'citation': 'fixture', 'quote': QUOTE}] if evidence and self.outcome == 'generated' else []
        status = 'completed' if evidence else 'skipped_no_evidence'
        mode = 'generated' if claims else 'abstained'
        if evidence and self.outcome == 'rejected':
            status, mode = 'unavailable_or_rejected', 'evidence_only'
        result = {'index_sha256': 'fixed', 'research_only': True, 'operational_approval': False,
                  'evidence': evidence, 'claims': claims, 'mode': mode,
                  'generation': {'requested': True, 'status': status, 'model': ollama.CHAT_MODEL,
                                 'model_digest': MODELS[ollama.CHAT_MODEL], 'private_error': 'PRIVATE-DETAILS'},
                  'private_extra': 'PRIVATE-DETAILS'}
        if self.tamper:
            self.tamper(result)
        return result


class GenerationDiagnosticTests(unittest.TestCase):
    def suite(self, folder):
        path = Path(folder) / 'cases.json'
        path.write_text(json.dumps({'format': 'ain-retrieval-cases-v1', 'cases': [
            {'id': 'supported', 'question': 'When do local sessions expire?', 'targets': [{'source': 'docs/LOCAL_IDENTITY.md', 'quote': QUOTE}]},
            {'id': 'outside', 'question': 'Describe unrelated plant biology.', 'targets': []}]}), encoding='utf-8')
        return path

    def evaluate(self, knowledge=None, inventories=None, progress=None):
        with tempfile.TemporaryDirectory() as folder, patch.object(ollama, 'models', side_effect=inventories or [MODELS, MODELS]):
            return gd.evaluate(knowledge or KnowledgeFixture(), self.suite(folder), progress=progress)

    def test_generated_claims_quote_coverage_scope_and_explicit_requests(self):
        knowledge = KnowledgeFixture(); rows = []
        r = self.evaluate(knowledge, progress=rows.append)
        self.assertTrue(r['complete']); self.assertEqual(r['metrics']['generated_answers'], 1)
        self.assertEqual(r['metrics']['gold_quote_coverage'], 1)
        self.assertEqual(r['metrics']['structurally_verified_claims'], 1)
        self.assertEqual(r['metrics']['outside_answer_abstentions'], 1)
        self.assertEqual(len(rows), 2); self.assertTrue(all(q.generate is True for q in knowledge.requests))
        self.assertTrue(all(c['human_review']['semantic_correctness'] is None for c in r['cases']))
        self.assertFalse(r['human_review_complete']); self.assertFalse(r['semantic_answer_accuracy_measured'])
        self.assertFalse(r['ranking_prompt_or_threshold_changes']); self.assertFalse(r['production_ready'])
        self.assertNotIn('PRIVATE-DETAILS', json.dumps(r)); self.assertNotIn('text', r['cases'][0]['retrieved'][0])

    def test_unavailable_retrieval_never_counts_as_correct_abstention(self):
        r = self.evaluate(KnowledgeFixture(fail=True)); m = r['metrics']
        self.assertFalse(r['complete']); self.assertEqual(m['retrieval_unavailable_cases'], 2)
        self.assertEqual(m['evaluated_out_of_corpus_cases'], 0); self.assertIsNone(m['gold_quote_coverage'])
        self.assertEqual(m['outside_answer_abstentions'], 0)
        self.assertTrue(all(c['answer_abstained'] is None for c in r['cases']))
        self.assertNotIn('PRIVATE-DETAILS', json.dumps(r))

    def test_rejected_generation_and_valid_empty_claims_are_distinct(self):
        r = self.evaluate(KnowledgeFixture(outcome='rejected', outside_evidence=True)); m = r['metrics']
        self.assertEqual(m['generation_unavailable_or_rejected_cases'], 2)
        self.assertEqual(m['outside_answer_abstentions'], 0); self.assertFalse(r['complete'])
        self.assertTrue(all(c['answer_abstained'] is None for c in r['cases']))
        r = self.evaluate(KnowledgeFixture(outcome='empty', outside_evidence=True)); m = r['metrics']
        self.assertTrue(r['complete']); self.assertEqual(m['answerable_abstentions'], 1)
        self.assertEqual(m['outside_answer_abstentions'], 1); self.assertEqual(m['gold_quote_coverage'], 0)

    def test_outside_generated_answer_is_retained_as_a_failure(self):
        r = self.evaluate(KnowledgeFixture(outside_evidence=True))
        self.assertEqual(r['metrics']['outside_generated_answers'], 1)
        self.assertEqual(r['metrics']['outside_answer_abstentions'], 0)
        self.assertEqual(len(r['cases'][1]['claims']), 1)
        self.assertEqual(r['cases'][1]['human_review']['status'], 'pending')

    def test_contradictory_response_citations_numbers_or_provenance_abort(self):
        changes = [lambda r: r.update(index_sha256='changed'),
                   lambda r: r['evidence'][0].update(text='changed'),
                   lambda r: r['claims'][0].update(citation='unknown'),
                   lambda r: r['claims'][0].update(text='The session lasts 777 hours'),
                   lambda r: r.update(mode='evidence_only'),
                   lambda r: r['generation'].update(model_digest='changed'),
                   lambda r: r['generation'].update(requested=False),
                   lambda r: r['generation'].update(status='unknown')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.evaluate(KnowledgeFixture(tamper=change))

    def test_changed_models_index_suite_or_code_cannot_finish_verified_run(self):
        with self.assertRaises(ValueError):
            self.evaluate(inventories=[MODELS, {**MODELS, ollama.CHAT_MODEL: 'changed'}])
        with self.assertRaises(RuntimeError):
            self.evaluate(inventories=[{ollama.EMBED_MODEL: MODELS[ollama.EMBED_MODEL]}])
        knowledge = KnowledgeFixture(); original = knowledge.load
        with patch.object(knowledge, 'load', side_effect=[original(), ('changed', knowledge.payload, None, None, None)]), self.assertRaises(ValueError):
            self.evaluate(knowledge)
        with patch.object(gd, 'fingerprints', side_effect=[{'code': 'a'}, {'code': 'b'}]), self.assertRaises(ValueError):
            self.evaluate()
        original_cases = gd.load_cases
        with tempfile.TemporaryDirectory() as folder:
            suite = self.suite(folder); cases, digest = original_cases(suite)
            with patch.object(gd, 'load_cases', side_effect=[(cases, digest), (cases, 'changed')]), patch.object(ollama, 'models', return_value=MODELS), self.assertRaises(ValueError):
                gd.evaluate(KnowledgeFixture(), suite)

    def test_quote_coverage_requires_matching_source_and_exact_gold_text(self):
        k = KnowledgeFixture(); case = {'targets': [{'source': 'docs/LOCAL_IDENTITY.md', 'quote': 'eight hours'}]}
        result = k.query(type('Q', (), {'question': 'sessions'})())
        corpus = {k.chunk['id']: k.chunk}
        r = gd.inspect_result(result, case, corpus, 'fixed', MODELS[ollama.CHAT_MODEL])
        self.assertEqual(r['target_quote_covered'], [True])
        case['targets'][0]['source'] = 'docs/DELAY_V2.md'
        self.assertEqual(gd.inspect_result(result, case, corpus, 'fixed', MODELS[ollama.CHAT_MODEL])['target_quote_covered'], [False])
        # A structurally valid quote and number check do not prove semantic entailment.
        result['claims'][0]['text'] = 'Sessions never expire.'
        r = gd.inspect_result(result, {'targets': []}, corpus, 'fixed', MODELS[ollama.CHAT_MODEL])
        self.assertEqual(r['human_review']['status'], 'pending')

    def test_private_exclusive_outputs_preserve_failed_journal_and_prior_reports(self):
        private = gd.ROOT / '.local'; private.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=private) as folder:
            target = Path(folder) / 'report.json'
            with patch.object(gd, 'evaluate', side_effect=RuntimeError('PRIVATE-DETAILS')), self.assertRaises(RuntimeError):
                gd.run_to_file(target)
            journal = target.with_suffix('.json.progress.jsonl')
            saved = journal.read_bytes(); self.assertNotIn(b'PRIVATE-DETAILS', saved)
            self.assertIn(b'"event": "failed"', saved); self.assertFalse(target.exists())
            with patch.object(gd, 'evaluate') as evaluate, self.assertRaises(ValueError):
                gd.run_to_file(target)
            evaluate.assert_not_called(); self.assertEqual(journal.read_bytes(), saved)
            target = Path(folder) / 'success.json'
            with patch.object(gd, 'evaluate', return_value={'complete': True, 'production_ready': False}):
                gd.run_to_file(target)
            before = target.read_bytes()
            with self.assertRaises(ValueError):gd.run_to_file(target)
            self.assertEqual(target.read_bytes(), before)
        with tempfile.TemporaryDirectory() as outside, self.assertRaises(ValueError):
            gd.run_to_file(Path(outside) / 'report.json')
