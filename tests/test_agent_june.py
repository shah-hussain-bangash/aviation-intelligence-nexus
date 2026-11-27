import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from agents.runtime import Investigation, Investigator
from agents.store import AgentStore, Conflict, sha
from agents.jobs import JobQueue
from agents.tools import definitions, execute
from agents.june_evidence import observation, valid_observation, LIMIT, required_quotes
from agents.quality import assess_report
from services.api.main import initialize, create_app
from rag import ollama


def extracts(question, evidence, **kwargs):
    row = evidence[0]
    return {'claims': [{'text': q, 'quote': q, 'citation': row['id']}
                       for q in required_quotes({'evidence_text': row['text']}).values()]}


class AgentJuneTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / 'fixture.sqlite3'
        initialize(self.db)
        self.user = {'id': 'fixture-owner', 'username': 'fixture-owner', 'role': 'researcher'}
        self.store = AgentStore(self.db)
        self.runtime = Investigator(self.db, None, self.store)
        self.request = Investigation(objective='Review the frozen June comparison and descriptive uncertainty only.',
                                     include_june_evidence=True, required_tools=['june_evidence'])

    def tearDown(self):
        self.folder.cleanup()

    def run_agent(self, key=None, generator=extracts):
        with patch.object(ollama, 'models', return_value={ollama.CHAT_MODEL: 'synthetic-model'}), \
             patch.object(ollama, 'generate', side_effect=generator) as summary, \
             patch('agents.runtime.select_tools', side_effect=[
                 [{'function': {'name': 'june_evidence', 'arguments': {}}}], []]) as planner:
            result = self.runtime.run(self.user, key or str(uuid4()), self.request)
            messages = [json.loads(m['content']) for m in planner.call_args[0][0] if m['role'] == 'tool']
            self.assertNotIn('snapshot', messages[0])
            if result['steps'][0]['state'] == 'completed':
                self.assertIn(LIMIT, messages[0]['evidence_text'])
            return result, summary.call_count

    def test_explicit_opt_in_and_three_tool_bound_preserve_legacy_request(self):
        old = Investigation(objective='Review historical research evidence.')
        self.assertNotIn('include_june_evidence', old.model_dump())
        self.assertEqual(old.model_dump(), Investigation.model_validate({**old.model_dump(), 'include_june_evidence': False}).model_dump())
        for changes in ({'include_june_evidence': False}, {'include_june_evidence': 'true'},
                        {'required_tools': []}, {'required_tools': ['june_evidence'] * 2},
                        {'required_tools': ['june_evidence', 'flight_metrics', 'knowledge_search', 'model_evidence']}):
            with self.assertRaises(ValidationError):
                Investigation.model_validate({**self.request.model_dump(), **changes})
        self.assertNotIn('june_evidence', [d['function']['name'] for d in definitions(False)])
        self.assertIn('june_evidence', [d['function']['name'] for d in definitions(False, june=True)])

    def test_unauthorized_or_nonempty_arguments_do_not_read_source(self):
        old = Investigation(objective='Review historical research evidence.')
        with patch('agents.tools.june_observation') as source:
            for args, request in (({'path': 'private'}, self.request), ({'month': '2025-07'}, self.request), ({}, old)):
                with self.assertRaises(ValueError):
                    execute('june_evidence', args, request, self.db, None)
            source.assert_not_called()

    def test_fixed_snapshot_review_and_retry_preserve_evidence(self):
        key = str(uuid4())
        run, calls = self.run_agent(key)
        self.assertEqual(calls, 1)
        self.assertTrue(run['quality']['passed'])
        saved = run['steps'][0]['observation']
        self.assertTrue(valid_observation(saved))
        self.assertEqual(saved['snapshot']['evaluation']['model']['records'], 599472)
        self.assertEqual(saved['snapshot']['evaluation']['candidate_period'], '2025-06')
        self.assertNotIn('.local', json.dumps(saved))
        self.assertEqual(run['state'], 'awaiting_review')
        self.assertFalse(run['reviews'])
        with patch('agents.runtime.select_tools') as planner:
            replay = self.runtime.run(self.user, key, self.request)
            planner.assert_not_called()
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['report_sha256'], run['report_sha256'])
        reviewed = self.store.review(self.user, run['run_id'], run['report_sha256'], 'reviewed', 'Synthetic review only; no human usefulness rating.')
        self.assertEqual(reviewed['state'], 'reviewed')
        self.assertFalse(reviewed['operational_approval'])

    def test_each_mandatory_quote_has_one_bounded_repair_and_blocks_review_if_still_missing(self):
        for label, quote in required_quotes(observation()).items():
            def missing(question, evidence, **kwargs):
                result = extracts(question, evidence, **kwargs)
                result['claims'] = [c for c in result['claims'] if c['quote'] != quote]
                return result
            run, calls = self.run_agent(generator=missing)
            self.assertEqual(calls, 2)
            self.assertFalse(run['quality']['passed'])
            self.assertIn('T1:' + label, run['quality']['june_required_quotes_missing'])
            self.assertEqual(run['quality']['june_quotes_uncited'], ['T1'])
            with self.assertRaises(Conflict):
                self.store.review(self.user, run['run_id'], run['report_sha256'], 'reviewed', 'Cannot accept missing evidence.')

    def test_repair_can_restore_a_missing_scope_quote_within_original_budget(self):
        calls = []
        def repair(question, evidence, **kwargs):
            calls.append(question)
            result = extracts(question, evidence, **kwargs)
            if len(calls) == 1:
                result['claims'] = result['claims'][:2]
            return result
        run, count = self.run_agent(generator=repair)
        self.assertEqual(count, 2)
        self.assertTrue(run['quality']['passed'])
        self.assertIn(LIMIT, calls[1])
        self.assertLessEqual(len(run['steps']), 3)
        self.assertFalse(run['quality']['semantic_entailment_verified'])

    def test_tampered_snapshot_permission_and_arguments_block_fresh_review(self):
        original, _ = self.run_agent()
        for mutate in (lambda r: r['steps'][0]['observation']['snapshot']['evaluation']['model'].__setitem__('roc_auc', 1),
                       lambda r: r['request'].__setitem__('include_june_evidence', False),
                       lambda r: r['steps'][0].__setitem__('arguments', {'url': 'private'})):
            run = copy.deepcopy(original)
            mutate(run)
            run['quality'] = {'passed': True}
            self.assertFalse(assess_report(run)['passed'])
            self.assertEqual(assess_report(run)['june_evidence_mismatches'], ['T1'])
            run['report_sha256'] = sha({k: run[k] for k in ('request', 'steps', 'claims')})
            self.store.checkpoint(run)
            with self.assertRaises(Conflict):
                self.store.review(self.user, run['run_id'], run['report_sha256'], 'reviewed', 'Changed source cannot be accepted.')
        changed = copy.deepcopy(observation())
        changed['evidence_text'] += ' Unsupported assertion.'
        self.assertFalse(valid_observation(changed))

    def test_source_failure_fabricates_no_evidence_and_releases_runtime(self):
        with patch('agents.tools.june_observation', side_effect=ValueError('private changed source')):
            run, calls = self.run_agent()
        self.assertEqual(calls, 0)
        self.assertEqual(run['steps'][0]['state'], 'failed')
        self.assertNotIn('observation', run['steps'][0])
        self.assertNotIn('private changed source', json.dumps(run))
        self.assertTrue(self.run_agent()[0]['quality']['passed'])

    def test_queue_permission_identity_and_legacy_false_default(self):
        queue = JobQueue(self.store)
        old = Investigation(objective='Review historical research evidence.')
        first = queue.enqueue(self.user, str(uuid4()), old)
        same = queue.enqueue(self.user, str(uuid4()), Investigation.model_validate({**old.model_dump(), 'include_june_evidence': False}))
        self.assertEqual(first['run_id'], same['run_id'])
        new = queue.enqueue(self.user, str(uuid4()), self.request)
        self.assertNotEqual(first['run_id'], new['run_id'])

    def test_http_role_boundary_for_explicit_june_request(self):
        with TestClient(create_app(self.db)) as client:
            app = client.app
            origin = {'Origin': 'http://127.0.0.1:8080'}
            path = '/api/v1/research/agent-run'
            self.assertEqual(client.post(path, headers=origin, json=self.request.model_dump()).status_code, 401)
            password = 'synthetic-june-agent-password'
            for role in ('admin', 'researcher', 'viewer'):
                app.state.auth_store.create_user('june-' + role, password, role)
                login = client.post('/api/v1/auth/login', headers=origin, json={'username': 'june-' + role, 'password': password})
                client.headers.update({**origin, 'X-CSRF-Token': login.json()['csrf_token'], 'Idempotency-Key': str(uuid4())})
                with patch('agents.runtime.Investigator.run', return_value={'fixture': True}) as runtime:
                    response = client.post(path, json=self.request.model_dump())
                self.assertEqual(response.status_code, 403 if role == 'viewer' else 200)
                self.assertEqual(runtime.call_count, 0 if role == 'viewer' else 1)
                self.assertEqual(client.post('/api/v1/auth/logout').status_code, 200)
