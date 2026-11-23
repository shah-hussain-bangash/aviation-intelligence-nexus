from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from services.api.main import create_app
from services.api.retrieval_evaluation import ROOT,REPORT,SUITE,load_retrieval_evaluation,validate_report
from rag.retrieval_diagnostics import summarize


def fixture():return json.loads((ROOT/REPORT).read_text(encoding='utf-8'))
def suite():return json.loads((ROOT/SUITE).read_text(encoding='utf-8'))


class RetrievalEvaluationTests(unittest.TestCase):
    def test_recorded_scope_and_metrics_load_without_model_calls(self):
        with patch('rag.ollama.models') as models,patch('rag.ollama.embed') as embed,patch('rag.ollama.generate') as generate:
            r=load_retrieval_evaluation()
            self.assertEqual(r['metrics']['hybrid']['target_hits_at_3'],17)
            self.assertEqual(r['metrics']['hybrid']['out_of_corpus_false_retrievals'],3)
            self.assertEqual(r['metrics']['lexical']['out_of_corpus_false_retrievals'],4)
            self.assertFalse(r['production_ready']);self.assertTrue(r['integrity_verified'])
            models.assert_not_called();embed.assert_not_called();generate.assert_not_called()

    def test_changed_counts_rates_ranks_and_scope_fail_closed(self):
        for modify in [lambda r:r.update(production_ready=True),lambda r:r.update(generated_answers=True),lambda r:r['metrics']['hybrid'].update(target_hits_at_3=18),lambda r:r['metrics']['lexical'].update(target_recall_at_3=.1),lambda r:r['cases'][0]['hybrid'].update(target_ranks=[0]),lambda r:r['cases'][1]['hybrid'].update(reciprocal_rank_sum=9),lambda r:r.update(complete=False)]:
            r=fixture();modify(r)
            with self.assertRaises(ValueError):validate_report(r,suite())

    def test_changed_labels_passage_sources_lines_and_fingerprints_are_rejected(self):
        for modify in [lambda r:r['cases'][0].update(question='Changed question'),lambda r:r['cases'][0]['hybrid']['retrieved'][0].update(source='../private'),lambda r:r['cases'][0]['hybrid']['retrieved'][0].update(start_line=0),lambda r:r.update(index_sha256='invalid'),lambda r:r['sources'][0].update(path='docs/PRIVATE.md')]:
            r=fixture();modify(r)
            with self.assertRaises(ValueError):validate_report(r,suite())

    def test_unavailable_queries_cannot_be_counted_as_successful_abstentions(self):
        r=fixture();r['cases'][-1]['hybrid']={'available':False,'abstained':None,'retrieved':[],'error_type':'TimeoutError'};r['complete']=False
        r['metrics']['hybrid']=summarize(r['cases'],'hybrid')
        self.assertEqual(validate_report(r,suite())['metrics']['hybrid']['unavailable_cases'],1)
        r['cases'][-1]['hybrid']['abstained']=True
        with self.assertRaises(ValueError):validate_report(r,suite())

    def test_missing_changed_oversized_and_crlf_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(OSError):load_retrieval_evaluation(root)
            for name in [REPORT,SUITE]:
                file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes((ROOT/name).read_text(encoding='utf-8').replace('\n','\r\n').encode())
            self.assertTrue(load_retrieval_evaluation(root)['integrity_verified'])
            (root/REPORT).write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):load_retrieval_evaluation(root)
            (root/REPORT).write_text(' '*200001,encoding='utf-8')
            with self.assertRaises(ValueError):load_retrieval_evaluation(root)

    def test_authenticated_all_roles_read_only_query_rejection_and_sanitized_failure(self):
        with tempfile.TemporaryDirectory() as folder,TestClient(create_app(Path(folder)/'state.sqlite3')) as client:
            path='/api/v1/research/retrieval-diagnostics';self.assertEqual(client.get(path).status_code,401)
            for name,role in [('fixture-admin','admin'),('fixture-viewer','viewer'),('fixture-researcher','researcher')]:
                client.app.state.auth_store.create_user(name,'temporary-retrieval-password',role)
                login=client.post('/api/v1/auth/login',json={'username':name,'password':'temporary-retrieval-password'},headers={'Origin':'http://127.0.0.1:8080'})
                self.assertEqual(login.status_code,200);self.assertEqual(client.get(path).status_code,200)
            self.assertEqual(client.get(path+'?source=private').status_code,422)
            self.assertNotEqual(client.post(path,json={}).status_code,200)
            with patch('services.api.main.load_retrieval_evaluation',side_effect=ValueError('PRIVATE LOCAL PATH')):
                response=client.get(path);self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE',response.text)

    def test_report_reads_do_not_add_database_or_model_history(self):
        with tempfile.TemporaryDirectory() as folder:
            database=Path(folder)/'state.sqlite3'
            with TestClient(create_app(database)) as client:
                client.app.state.auth_store.create_user('fixture-admin','temporary-retrieval-password','admin')
                client.post('/api/v1/auth/login',json={'username':'fixture-admin','password':'temporary-retrieval-password'},headers={'Origin':'http://127.0.0.1:8080'})
                def counts():
                    with closing(sqlite3.connect(database)) as db:
                        tables=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                        return {name:db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in tables}
                before=counts()
                for _ in range(3):self.assertEqual(client.get('/api/v1/research/retrieval-diagnostics').status_code,200)
                self.assertEqual(counts(),before)
