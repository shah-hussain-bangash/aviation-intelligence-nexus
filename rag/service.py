"""Hybrid local retrieval with explicit abstention and validated citation references."""
import json
import re
from pathlib import Path
from threading import Lock
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from rag import ollama
from rag.index import INDEX, ROOT, SOURCES, digest, validate_vectors


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=8, max_length=600)
    generate: bool = Field(default=False, strict=True)


def validate_claims(output, evidence):
    if not isinstance(output, dict) or set(output) != {'claims'} or not isinstance(output['claims'], list) or len(output['claims']) > 3:
        raise RuntimeError('Invalid generation structure')
    known = {row['id']: row['text'] for row in evidence}
    claims = output['claims']
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'text', 'citation', 'quote'} or not all(isinstance(v, str) for v in claim.values()):
            raise RuntimeError('Invalid claim fields')
        if not 1 <= len(claim['text']) <= 700 or not 20 <= len(claim['quote']) <= 400:
            raise RuntimeError('Invalid claim length')
        if claim['citation'] not in known or claim['quote'] not in known[claim['citation']]:
            raise RuntimeError('Unsupported citation or quotation')
        numbers = lambda text: {v.replace(',', '') for v in re.findall(r'\d+(?:[.,]\d+)*', text)}
        if not numbers(claim['text']).issubset(numbers(claim['quote'])):
            raise RuntimeError('Claimed number absent from supporting quote')
    return claims


class Knowledge:
    def __init__(self, path=INDEX):
        self.path = Path(path)
        self.cache = None
        self.lock = Lock()

    def load(self):
        raw = self.path.read_bytes()
        if len(raw) > 4_000_000:
            raise RuntimeError('Index exceeds bound')
        envelope = json.loads(raw)
        payload = envelope['payload']
        if envelope['sha256'] != digest(json.dumps(payload, sort_keys=True).encode()) or payload['version'] != 1:
            raise RuntimeError('Index integrity failed')
        if [row['path'] for row in payload['sources']] != list(SOURCES):
            raise RuntimeError('Unexpected corpus')
        for source in payload['sources']:
            if digest((ROOT / source['path']).read_bytes()) != source['sha256']:
                raise RuntimeError('Source changed; rebuild index')
        with self.lock:
            if not self.cache or self.cache[0] != envelope['sha256']:
                vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), sublinear_tf=True)
                sparse = vectorizer.fit_transform([row['heading'] + '\n' + row['text'] for row in payload['chunks']])
                dense = validate_vectors(payload['vectors'], len(payload['chunks']))
                self.cache = (envelope['sha256'], payload, vectorizer, sparse, dense)
            return self.cache

    def status(self):
        try:
            index_hash, payload, *_ = self.load()
            installed = ollama.models()
            return {'index_ready': True, 'sources': len(payload['sources']), 'chunks': len(payload['chunks']),
                'index_sha256': index_hash, 'embedding_model': payload['embedding_model'],
                'embedding_ready': installed.get(ollama.EMBED_MODEL) == payload['embedding_digest'],
                'generation_model': ollama.CHAT_MODEL, 'generation_available': ollama.CHAT_MODEL in installed,
                'scope': 'Public project evidence only; not an airline operations manual', 'research_only': True}
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            return {'index_ready': False, 'embedding_ready': False, 'generation_available': False,
                'message': 'Knowledge index or local model service unavailable; rebuild/restore before searching.', 'research_only': True}

    def query(self, request, source_document=None):
        if source_document is not None and source_document not in SOURCES:
            raise ValueError('Document scope is outside the approved corpus')
        index_hash, payload, vectorizer, sparse, dense = self.load()
        installed = ollama.models()
        if installed.get(ollama.EMBED_MODEL) != payload['embedding_digest']:
            raise RuntimeError('Embedding model changed or unavailable')
        query_dense = validate_vectors(ollama.embed([request.question]), 1)[0]
        lexical = (sparse @ vectorizer.transform([request.question]).T).toarray().ravel()
        semantic = dense @ query_dense
        scores = .65 * semantic + .35 * lexical
        # Conservative lexical anchor prevents broad semantic similarity alone from being presented as evidence.
        ranked = [int(i) for i in np.argsort(-scores) if lexical[i] >= .035 and semantic[i] >= .25
                  and (source_document is None or payload['chunks'][i]['source']==source_document)][:3]
        if source_document is not None and ranked:
            # An explicitly selected small document needs contextual coverage, not just its three best headings.
            ranked=[int(i) for i in np.argsort(-scores) if payload['chunks'][i]['source']==source_document][:8]
        evidence = [{**payload['chunks'][i], 'score': round(float(scores[i]), 4),
            'source_sha256': next(s['sha256'] for s in payload['sources'] if s['path'] == payload['chunks'][i]['source']),
            'source_url': 'https://github.com/zenithdevelopers7-source/aviation-intelligence-nexus/blob/' + payload['revision'] + '/' + payload['chunks'][i]['source'] + '#L' + str(payload['chunks'][i]['start_line'])}
            for i in ranked]
        result = {'question': request.question, 'mode': 'evidence_only' if evidence else 'abstained',
            'evidence': evidence, 'claims': [], 'index_sha256': index_hash,
            'retrieval': 'hybrid dense cosine + TF-IDF; scores are not confidence probabilities',
            'generation': {'requested': request.generate, 'status': 'not_requested'},
            'research_only': True, 'operational_approval': False}
        if request.generate and evidence:
            try:
                generation_digest = installed[ollama.CHAT_MODEL]
                claims = validate_claims(ollama.generate(request.question, [{'id': e['id'], 'text': e['text']} for e in evidence]), evidence)
                result.update(mode='generated' if claims else 'abstained', claims=claims)
                result['generation'] = {'requested': True, 'status': 'completed', 'model': ollama.CHAT_MODEL,
                    'model_digest': generation_digest, 'citation_check': 'ids and exact quotes verified; semantic entailment requires human review'}
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                result['generation'] = {'requested': True, 'status': 'unavailable_or_rejected',
                    'message': 'No validated generated answer was returned. Retrieved evidence remains available.'}
        elif request.generate:
            result['generation']['status'] = 'skipped_no_evidence'
        return result
