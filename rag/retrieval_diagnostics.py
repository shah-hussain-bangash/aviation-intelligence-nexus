"""Curated passage-level diagnostics of unchanged local retrieval; no generation or tuning."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from rag.index import ROOT, SOURCES
from rag.service import Knowledge, Question

SUITE = ROOT / 'rag/retrieval_cases.json'


def load_cases(path=SUITE):
    path = Path(path)
    if path.stat().st_size > 100000:
        raise ValueError('Oversized evaluation suite')
    raw = path.read_text(encoding='utf-8')
    suite = json.loads(raw)
    cases = suite['cases']
    if suite.get('format') != 'ain-retrieval-cases-v1' or not isinstance(cases, list) or not 2 <= len(cases) <= 64:
        raise ValueError('Unsupported evaluation suite')
    seen = set()
    for case in cases:
        if set(case) != {'id', 'question', 'targets'} or not isinstance(case['id'], str) or not case['id'] or case['id'] in seen:
            raise ValueError('Invalid or repeated case identity')
        seen.add(case['id'])
        Question(question=case['question'], generate=False)
        if not isinstance(case['targets'], list) or len(case['targets']) > 3:
            raise ValueError('Invalid evidence targets')
        for target in case['targets']:
            if set(target) != {'source', 'quote'} or target['source'] not in SOURCES or not isinstance(target['quote'], str) or len(target['quote']) < 12:
                raise ValueError('Invalid source/quote target')
            if target['quote'] not in (ROOT / target['source']).read_text(encoding='utf-8'):
                raise ValueError('Target quotation is absent from its declared document')
    if not any(c['targets'] for c in cases) or not any(not c['targets'] for c in cases):
        raise ValueError('Answerable and out-of-corpus cases are both required')
    return cases, hashlib.sha256(raw.encode()).hexdigest()


def score(targets, evidence):
    if not isinstance(evidence, list) or len(evidence) > 3:
        raise ValueError('Expected at most three observed passages')
    ranks = [next((rank for rank, row in enumerate(evidence, 1)
                   if row['source'] == target['source'] and target['quote'] in row['text']), None)
             for target in targets]
    return {'target_ranks': ranks, 'target_hits': sum(r is not None for r in ranks),
            'reciprocal_rank_sum': sum(1 / r for r in ranks if r is not None),
            'all_targets_found': bool(targets) and all(r is not None for r in ranks),
            'abstained': not evidence, 'available': True}


def summarize(rows, method):
    answerable = [r for r in rows if r['targets'] and r[method]['available']]
    unsupported = [r for r in rows if not r['targets'] and r[method]['available']]
    targets = sum(len(r['targets']) for r in answerable)
    return {'total_cases': len(rows), 'unavailable_cases': sum(not r[method]['available'] for r in rows),
            'evaluated_answerable_cases': len(answerable), 'evaluated_gold_targets': targets,
            'target_hits_at_3': sum(r[method]['target_hits'] for r in answerable),
            'target_recall_at_3': sum(r[method]['target_hits'] for r in answerable) / targets if targets else None,
            'mean_target_reciprocal_rank_at_3': sum(r[method]['reciprocal_rank_sum'] for r in answerable) / targets if targets else None,
            'all_targets_found_cases': sum(r[method]['all_targets_found'] for r in answerable),
            'evaluated_out_of_corpus_cases': len(unsupported),
            'out_of_corpus_abstentions': sum(r[method]['abstained'] for r in unsupported),
            'out_of_corpus_false_retrievals': sum(not r[method]['abstained'] for r in unsupported)}


def evaluate(knowledge=None, suite_path=SUITE):
    cases, suite_hash = load_cases(suite_path)
    knowledge = knowledge or Knowledge()
    index_hash, payload, vectorizer, sparse, _ = knowledge.load()
    corpus = {c['id']: c for c in payload['chunks']}
    # Validate labels against indexed passages, not just a document containing a distant quote.
    if any(not any(t['source'] == c['source'] and t['quote'] in c['text'] for c in corpus.values()) for case in cases for t in case['targets']):
        raise ValueError('A gold quote does not fit in an indexed passage')
    rows = []
    started = time.monotonic()
    for case in cases:
        begin = time.monotonic()
        try:
            observed = knowledge.query(Question(question=case['question'], generate=False))
            if observed['index_sha256'] != index_hash or observed['claims'] or observed['generation']['requested'] is not False:
                raise ValueError('Unexpected index or generation behavior')
            evidence = observed['evidence']
            if observed['mode'] != ('evidence_only' if evidence else 'abstained'):
                raise ValueError('Contradictory retrieval response')
            for row in evidence:
                original = corpus.get(row['id'])
                if original is None or any(row[k] != original[k] for k in ('source', 'text', 'start_line', 'end_line')):
                    raise ValueError('Retrieved passage provenance differs from the loaded corpus')
        except (OSError, RuntimeError) as error:
            observed = None
            failure_type = type(error).__name__
        lexical = (sparse @ vectorizer.transform([case['question']]).T).toarray().ravel()
        indices = [int(i) for i in np.argsort(-lexical) if lexical[i] >= .035][:3]
        baseline = [payload['chunks'][i] for i in indices]
        project = lambda group: [{k: e[k] for k in ('id', 'source', 'start_line', 'end_line')} for e in group]
        rows.append({**case, 'hybrid': ({**score(case['targets'], evidence), 'retrieved': project(evidence)} if observed is not None else {'available': False, 'abstained': None, 'error_type': failure_type, 'retrieved': []}),
                     'lexical': {**score(case['targets'], baseline), 'retrieved': project(baseline)},
                     'case_elapsed_ms': round((time.monotonic() - begin) * 1000, 2)})
    if knowledge.load()[0] != index_hash or load_cases(suite_path)[1] != suite_hash:
        raise ValueError('Index or suite changed during evaluation')
    return {'format': 'ain-retrieval-diagnostics-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Curated development questions about six public project documents; not independently labeled, held-out, representative airline QA or a prompt-injection evaluation.',
            'suite_sha256': suite_hash, 'index_sha256': index_hash, 'corpus_revision': payload['revision'],
            'embedding_model': payload['embedding_model'], 'embedding_digest': payload['embedding_digest'],
            'sources': payload['sources'], 'passages': len(payload['chunks']),
            'methods': {'hybrid': 'Unchanged Knowledge.query with generation disabled; current 65/35 dense/TF-IDF ranking and both existing gates.',
                        'lexical': 'Same TF-IDF vectors and lexical gate 0.035; top three, no semantic gate. This is a diagnostic baseline, not threshold-matched abstention.'},
            'metrics': {method: summarize(rows, method) for method in ('hybrid', 'lexical')},
            'cases': rows, 'complete': all(r['hybrid']['available'] for r in rows),
            'metric_denominators': 'Ranking and abstention metrics include available cases only; unavailable cases are separately counted and never treated as abstentions.',
            'elapsed_ms': round((time.monotonic() - started) * 1000, 2),
            'generated_answers': 0, 'ranking_or_threshold_changes': False,
            'semantic_answer_accuracy_measured': False, 'operational_approval': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if not target.is_relative_to(ROOT / '.local') or target.exists() or any(p.is_symlink() for p in [Path(args.output), *Path(args.output).parents]):
        raise ValueError('Use a new private output file under this checkout .local directory')
    report = evaluate()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'metrics': report['metrics'], 'cases': len(report['cases']), 'elapsed_ms': report['elapsed_ms'], 'production_ready': False}))


if __name__ == '__main__':
    main()
