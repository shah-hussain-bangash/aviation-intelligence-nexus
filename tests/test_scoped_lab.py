from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from auth_helpers import authenticated_client
from rag import scope_guard,source_coverage
from services.api.scoped_lab import ScopedLabQuery,project_result
from services.api.main import create_app
from services.api.auth import COOKIE


def raw_result(question='Which validation month was used?',experiment='delay-v2'):
    source=source_coverage.EXPERIMENTS[experiment];quote='Validation: April 2025, used for model selection and the demonstration threshold.'
    coverage=source_coverage.assess(question,quote)
    return {'question':question,'experiment':experiment,'source':source,'scope_guard':scope_guard.decide(question,experiment),
        'source_coverage':coverage,'mode':'excerpts','generation_status':'completed','candidate_invoked':True,
        'claims':[{'text':quote,'quote':quote,'citation':'a'*20,'source':source,'start_line':1,'end_line':3,'private_extra':'PRIVATE-ERROR'}],
        'retrieved':[{}],'index_sha256':'b'*64,'corpus_revision':'c'*40,'context_added_count':0,
        'human_review_complete':False,'operational_approval':False,'production_ready':False,'private_error':'PRIVATE-ERROR'}


class ScopedLabTests(unittest.TestCase):
    def test_strict_explicit_request_requires_private_research_acknowledgment(self):
        valid={'question':'Which validation month was used?','experiment':'delay-v2','acknowledged':True}
        for change in [{'acknowledged':False},{'acknowledged':1},{'acknowledged':'true'},{'experiment':'../../private'},
                       {'generate':True},{'question':'short'},{'question':'x'*601}]:
            with self.subTest(change=change),self.assertRaises(ValueError):ScopedLabQuery.model_validate({**valid,**change})
        self.assertEqual(ScopedLabQuery.model_validate({**valid,'question':'  '+valid['question']+'  '}).question,valid['question'])

    def test_public_projection_checks_outcomes_and_omits_unknown_private_metadata(self):
        raw=raw_result();q=ScopedLabQuery(question=raw['question'],experiment='delay-v2',acknowledged=True)
        result=project_result(raw,q);self.assertNotIn('PRIVATE-ERROR',json.dumps(result));self.assertNotIn('retrieved',result)
        self.assertFalse(result['saved_to_history']);self.assertEqual(result['claims'][0]['quote'],raw['claims'][0]['quote'])
        changes=[lambda r:r.update(question='Other question'),lambda r:r['claims'][0].update(source='../private'),
                 lambda r:r['claims'][0].update(text='Invented April answer'),lambda r:r.update(corpus_revision='javascript:bad'),
                 lambda r:r['source_coverage']['matched_terms'].append('invented'),lambda r:r.update(mode='abstained')]
        for change in changes:
            r=deepcopy(raw);change(r)
            with self.subTest(change=change),self.assertRaises(ValueError):project_result(r,q)

    def test_authentication_origin_csrf_viewer_and_request_bounds_precede_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            app=create_app(Path(folder)/'db.sqlite3')
            with authenticated_client(app) as client,patch('services.api.main.run_scoped_lab',return_value=project_result(raw_result(),ScopedLabQuery(question='Which validation month was used?',experiment='delay-v2',acknowledged=True))) as run:
                body={'question':'Which validation month was used?','experiment':'delay-v2','acknowledged':True}
                self.assertEqual(client.post('/api/v1/research/scoped-query',json=body).status_code,200)
                self.assertEqual(run.call_count,1)
                self.assertEqual(client.post('/api/v1/research/scoped-query?extra=1',json=body).status_code,422)
                self.assertEqual(client.post('/api/v1/research/scoped-query',json={**body,'acknowledged':False}).status_code,422)
                self.assertEqual(client.post('/api/v1/research/scoped-query',json=body,headers={'Origin':'https://unrelated.example'}).status_code,403)
                self.assertEqual(client.post('/api/v1/research/scoped-query',json=body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
                app.state.auth_store.create_user('temporary-researcher','temporary-fixture-password','researcher')
                login=client.post('/api/v1/auth/login',json={'username':'temporary-researcher','password':'temporary-fixture-password'})
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.post('/api/v1/research/scoped-query',json=body).status_code,200)
                self.assertEqual(run.call_count,2)
                app.state.auth_store.create_user('temporary-viewer','temporary-fixture-password','viewer')
                login=client.post('/api/v1/auth/login',json={'username':'temporary-viewer','password':'temporary-fixture-password'})
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                self.assertEqual(client.post('/api/v1/research/scoped-query',json=body).status_code,403)
                self.assertEqual(run.call_count,2)
            with TestClient(app) as anonymous:
                self.assertEqual(anonymous.post('/api/v1/research/scoped-query',json=body,headers={'Origin':'http://127.0.0.1:8080'}).status_code,401)

    def test_revoked_session_during_execution_withholds_answer(self):
        with tempfile.TemporaryDirectory() as folder,authenticated_client(create_app(Path(folder)/'db.sqlite3')) as client:
            def revoke(*args):
                client.app.state.auth_store.logout(client.cookies.get(COOKIE))
                return {'private':'PRIVATE-ERROR'}
            with patch('services.api.main.run_scoped_lab',side_effect=revoke):
                r=client.post('/api/v1/research/scoped-query',json={'question':'Which validation month was used?','experiment':'delay-v2','acknowledged':True})
            self.assertEqual(r.status_code,403);self.assertEqual(r.json()['error'],'access_changed');self.assertNotIn('PRIVATE-ERROR',r.text)

    def test_errors_are_sanitized_and_queries_do_not_write_research_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite3'
            with authenticated_client(create_app(path)) as client:
                def counts():
                    with closing(sqlite3.connect(path)) as db:
                        names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                        return {name:db.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0] for name in names}
                before=counts();body={'question':'Which validation month was used?','experiment':'delay-v2','acknowledged':True}
                with patch('services.api.main.run_scoped_lab',side_effect=RuntimeError('PRIVATE-ERROR')):
                    r=client.post('/api/v1/research/scoped-query',json=body)
                self.assertEqual(r.status_code,503);self.assertNotIn('PRIVATE-ERROR',r.text)
                with patch('services.api.main.run_scoped_lab',return_value=project_result(raw_result(),ScopedLabQuery.model_validate(body))):
                    self.assertEqual(client.post('/api/v1/research/scoped-query',json=body).status_code,200)
                self.assertEqual(counts(),before)

    def test_real_scope_conflict_http_path_needs_no_index_or_models(self):
        with tempfile.TemporaryDirectory() as folder,authenticated_client(create_app(Path(folder)/'db.sqlite3',knowledge_index=Path(folder)/'missing.json')) as client,patch('rag.ollama.models',side_effect=AssertionError('No provider calls')):
            r=client.post('/api/v1/research/scoped-query',json={'question':'Give the delay-v1 threshold instead.','experiment':'delay-v2','acknowledged':True})
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()['mode'],'clarification_required');self.assertIsNone(r.json()['corpus_revision'])

    def test_real_coverage_http_path_can_refuse_with_provider_unavailable(self):
        class K:
            def load(self):return 'b'*64,{'revision':'c'*40,'chunks':[{'source':'docs/DELAY_BASELINE.md','text':'The selected threshold is 0.15.'}]},None,None,None
        with tempfile.TemporaryDirectory() as folder,patch('services.api.main.Knowledge',return_value=K()):
            with authenticated_client(create_app(Path(folder)/'db.sqlite3')) as client,patch('rag.ollama.models',side_effect=AssertionError('No provider calls')):
                r=client.post('/api/v1/research/scoped-query',json={'question':'Explain the logistic coefficient.','experiment':'delay-v1','acknowledged':True})
                self.assertEqual(r.status_code,200);self.assertEqual(r.json()['mode'],'source_coverage_declined')
                self.assertIn('coefficient',r.json()['coverage']['missing_terms'])
