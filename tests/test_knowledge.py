from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from auth_helpers import authenticated_client
from rag import index, ollama
from rag.service import Knowledge, Question, validate_claims
from services.api.main import create_app


def fake_embed(texts):
    return np.ones((len(texts), 768)).tolist()


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.index = Path(self.directory.name) / 'index.json'
        self.models = patch.object(ollama, 'models', return_value={ollama.EMBED_MODEL: 'fixture-digest', ollama.CHAT_MODEL: 'chat-fixture'})
        self.embeddings = patch.object(ollama, 'embed', side_effect=fake_embed)
        self.models.start(); self.embeddings.start()
        with patch.object(index, 'INDEX', self.index):
            index.build()
        self.knowledge = Knowledge(self.index)

    def tearDown(self):
        self.embeddings.stop(); self.models.stop(); self.directory.cleanup()

    def test_ingestion_has_exact_source_ranges_and_valid_embeddings(self):
        _, payload, *_ = self.knowledge.load()
        self.assertEqual(len(payload['sources']), 6)
        self.assertEqual(self.knowledge.status()['chunks'], len(payload['chunks']))
        for chunk in payload['chunks']:
            lines = (index.ROOT / chunk['source']).read_text(encoding='utf-8').splitlines()
            self.assertEqual(chunk['text'], '\n'.join(lines[chunk['start_line']-1:chunk['end_line']]))

    def test_hybrid_retrieval_and_no_evidence_abstention(self):
        result = self.knowledge.query(Question(question='What were the May ROC-AUC and false alerts for the second delay model?'))
        self.assertEqual(result['evidence'][0]['source'], 'docs/DELAY_V2.md')
        self.assertEqual(result['mode'], 'evidence_only')
        with patch.object(ollama, 'generate') as generate:
            unknown = self.knowledge.query(Question(question='Explain photosynthesis in chloroplast organelles', generate=True))
            self.assertEqual(unknown['mode'], 'abstained')
            generate.assert_not_called()

    def test_generated_claims_require_matching_quote_citation_and_numbers(self):
        evidence = [{'id':'c1','text':'The May ROC-AUC is 0.6506 in this research experiment.'}]
        valid = {'claims':[{'text':'May ROC-AUC is 0.6506','citation':'c1','quote':evidence[0]['text']}]}
        self.assertEqual(len(validate_claims(valid, evidence)), 1)
        for change in [{'citation':'invented'}, {'quote':'Invented supporting evidence here'}, {'text':'May ROC-AUC is 0.99'}]:
            with self.assertRaises(RuntimeError):
                validate_claims({'claims':[{**valid['claims'][0],**change}]},evidence)

    def test_generation_failure_returns_evidence_without_fabricated_answer(self):
        with patch.object(ollama, 'generate', side_effect=TimeoutError):
            result = self.knowledge.query(Question(question='How does gate allocation prioritize assignment cost?', generate=True))
        self.assertEqual(result['mode'], 'evidence_only')
        self.assertEqual(result['claims'], [])
        self.assertEqual(result['generation']['status'], 'unavailable_or_rejected')

    def test_index_corruption_model_change_and_invalid_vectors_fail_closed(self):
        envelope=json.loads(self.index.read_text()); envelope['payload']['vectors'][0][0]=99
        self.index.write_text(json.dumps(envelope))
        self.assertFalse(self.knowledge.status()['index_ready'])
        with self.assertRaises(RuntimeError): self.knowledge.query(Question(question='How does gate allocation work?'))
        with self.assertRaises(RuntimeError): index.validate_vectors([[0]*768],1)

    def test_changed_source_is_rejected_and_model_digest_change_is_rejected(self):
        envelope=json.loads(self.index.read_text()); envelope['payload']['sources'][0]['sha256']='changed'
        envelope['sha256']=index.digest(json.dumps(envelope['payload'],sort_keys=True).encode())
        self.index.write_text(json.dumps(envelope))
        with self.assertRaises(RuntimeError): self.knowledge.load()
        with patch.object(index,'INDEX',self.index): index.build()
        with patch.object(ollama,'models',return_value={ollama.EMBED_MODEL:'new-digest'}):
            with self.assertRaises(RuntimeError): self.knowledge.query(Question(question='How does gate allocation work?'))

    def test_authenticated_persistence_restart_and_viewer_permissions(self):
        database=Path(self.directory.name)/'test.sqlite3'
        with authenticated_client(create_app(database,knowledge_index=self.index)) as client:
            result=client.post('/api/v1/research/knowledge-query',json={'question':'How does gate allocation prioritize assignment cost?'})
            self.assertEqual(result.status_code,200)
            self.assertEqual(len(client.get('/api/v1/research/knowledge-history').json()['runs']),1)
            client.app.state.auth_store.create_user('knowledge-viewer','temporary-viewer-fixture-123','viewer')
            login=client.post('/api/v1/auth/login',json={'username':'knowledge-viewer','password':'temporary-viewer-fixture-123'})
            client.headers['X-CSRF-Token']=login.json()['csrf_token']
            self.assertEqual(client.post('/api/v1/research/knowledge-query',json={'question':'How does gate allocation work?'}).status_code,403)
            self.assertEqual(client.get('/api/v1/research/knowledge-history').json()['runs'],[])
        with authenticated_client(create_app(database,knowledge_index=self.index)) as client:
            self.assertEqual(client.get('/api/v1/research/knowledge-history').json()['runs'][0]['run_id'],result.json()['run_id'])

    def test_missing_index_and_invalid_requests_have_no_success_result(self):
        with authenticated_client(create_app(Path(self.directory.name)/'test.sqlite3',knowledge_index=Path(self.directory.name)/'missing.json')) as client:
            self.assertFalse(client.get('/api/v1/research/knowledge-status').json()['index_ready'])
            self.assertEqual(client.post('/api/v1/research/knowledge-query',json={'question':'How does gate allocation work?'}).status_code,503)
            self.assertEqual(client.post('/api/v1/research/knowledge-query',json={'question':'short'}).status_code,422)
            self.assertEqual(client.post('/api/v1/research/knowledge-query',json={'question':'How does gate allocation work?','url':'https://example.com'}).status_code,422)
            self.assertEqual(client.get('/api/v1/research/knowledge-history').json()['runs'],[])
