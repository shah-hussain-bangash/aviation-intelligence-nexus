from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from sklearn.feature_extraction.text import TfidfVectorizer
from rag.retrieval_diagnostics import evaluate, load_cases, score, summarize, SUITE


class FixtureKnowledge:
    def __init__(self, fail=False, tamper=False, change=False):
        self.fail, self.tamper, self.change = fail, tamper, change
        self.loads = 0
        self.requests = []
        self.chunk = {'id': 'fixture', 'source': 'docs/LOCAL_IDENTITY.md', 'text': 'Sessions expire after eight hours', 'start_line': 1, 'end_line': 1}
        self.payload = {'chunks': [self.chunk], 'revision': 'a' * 40, 'embedding_model': 'fixture', 'embedding_digest': 'fixture-digest', 'sources': []}
        self.vectorizer = TfidfVectorizer(); self.sparse = self.vectorizer.fit_transform([self.chunk['text']])

    def load(self):
        self.loads += 1
        return ('changed' if self.change and self.loads > 1 else 'fixed', self.payload, self.vectorizer, self.sparse, None)

    def query(self, request):
        self.requests.append(request)
        if self.fail:
            raise TimeoutError('PRIVATE-DETAILS-MUST-NOT-LEAK')
        evidence = [deepcopy(self.chunk)] if 'session' in request.question.lower() else []
        if self.tamper and evidence:
            evidence[0]['text'] = 'Changed quotation'
        return {'index_sha256': 'fixed', 'claims': [], 'generation': {'requested': False}, 'mode': 'evidence_only' if evidence else 'abstained', 'evidence': evidence}


class RetrievalDiagnosticTests(unittest.TestCase):
    def suite(self, folder):
        data = {'format': 'ain-retrieval-cases-v1', 'cases': [
            {'id': 'supported', 'question': 'When do local sessions expire?', 'targets': [{'source': 'docs/LOCAL_IDENTITY.md', 'quote': 'Sessions expire after eight hours'}]},
            {'id': 'outside', 'question': 'Describe unrelated plant biology.', 'targets': []}]}
        path = Path(folder) / 'cases.json'; path.write_text(json.dumps(data), encoding='utf-8')
        return path, data

    def test_fixed_suite_has_valid_public_quotes_and_explicit_negative_cases(self):
        cases, fingerprint = load_cases()
        self.assertEqual(len(cases), 24)
        self.assertEqual(sum(bool(c['targets']) for c in cases), 18)
        self.assertEqual(len(fingerprint), 64)
        self.assertEqual(load_cases()[1], fingerprint)

    def test_relevance_requires_both_declared_source_and_quote(self):
        target = [{'source': 'correct', 'quote': 'exact evidence'}]
        evidence = [{'source': 'wrong', 'text': 'exact evidence'}, {'source': 'correct', 'text': 'the exact evidence is here'}]
        result = score(target, evidence)
        self.assertEqual(result['target_ranks'], [2]); self.assertEqual(result['reciprocal_rank_sum'], .5)
        self.assertEqual(score(target, evidence[:1])['target_hits'], 0)
        self.assertTrue(score([], [])['abstained']); self.assertFalse(score([], evidence)['abstained'])

    def test_multiple_targets_and_partial_coverage_are_not_all_found(self):
        targets = [{'source': 'one', 'quote': 'first'}, {'source': 'two', 'quote': 'second'}]
        result = score(targets, [{'source': 'one', 'text': 'first'}])
        self.assertEqual(result['target_ranks'], [1, None]); self.assertFalse(result['all_targets_found'])
        with self.assertRaises(ValueError): score(targets, [{}] * 4)

    def test_bad_labels_duplicates_and_missing_case_groups_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path, original = self.suite(folder)
            for modify in [lambda d: d['cases'][0]['targets'][0].update(source='../private'), lambda d: d['cases'][0]['targets'][0].update(quote='A quotation absent from the actual document'), lambda d: d['cases'][1].update(id='supported'), lambda d: d.update(cases=d['cases'][:1])]:
                data = deepcopy(original); modify(data); path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError): load_cases(path)

    def test_observed_queries_disable_generation_and_preserve_metric_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.suite(folder); knowledge = FixtureKnowledge(); report = evaluate(knowledge, path)
            self.assertTrue(report['complete']); self.assertEqual(report['metrics']['hybrid']['target_recall_at_3'], 1)
            self.assertEqual(report['metrics']['hybrid']['out_of_corpus_abstentions'], 1)
            self.assertTrue(all(q.generate is False for q in knowledge.requests))
            self.assertEqual(report['generated_answers'], 0); self.assertFalse(report['semantic_answer_accuracy_measured'])
            self.assertFalse(report['production_ready']); self.assertFalse(report['operational_approval'])

    def test_unavailable_provider_is_not_counted_as_correct_abstention(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.suite(folder); report = evaluate(FixtureKnowledge(fail=True), path)
            metrics = report['metrics']['hybrid']
            self.assertFalse(report['complete']); self.assertEqual(metrics['unavailable_cases'], 2)
            self.assertIsNone(metrics['target_recall_at_3']); self.assertEqual(metrics['out_of_corpus_abstentions'], 0)
            self.assertIsNone(report['cases'][1]['hybrid']['abstained'])
            self.assertNotIn('PRIVATE-DETAILS', json.dumps(report))

    def test_changed_evidence_or_index_never_produces_verified_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.suite(folder)
            for knowledge in [FixtureKnowledge(tamper=True), FixtureKnowledge(change=True)]:
                with self.assertRaises(ValueError): evaluate(knowledge, path)

    def test_summary_denominators_exclude_unavailable_and_reconcile_hits(self):
        rows = [{'targets': [{'source': 'one', 'quote': 'first'}], 'hybrid': score([{'source': 'one', 'quote': 'first'}], [{'source': 'one', 'text': 'first'}])},
                {'targets': [], 'hybrid': score([], [{'source': 'one', 'text': 'irrelevant'}])},
                {'targets': [], 'hybrid': {'available': False}}]
        result = summarize(rows, 'hybrid')
        self.assertEqual(result['unavailable_cases'], 1); self.assertEqual(result['evaluated_out_of_corpus_cases'], 1)
        self.assertEqual(result['out_of_corpus_false_retrievals'], 1); self.assertEqual(result['target_recall_at_3'], 1)
