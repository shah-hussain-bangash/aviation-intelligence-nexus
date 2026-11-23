"""Offline curated generation checks; exact quotations do not establish semantic correctness."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from rag import ollama
from rag.index import ROOT
from rag.retrieval_diagnostics import SUITE, load_cases, score
from rag.service import Knowledge, Question, validate_claims

CODE_PATHS = ('rag/service.py', 'rag/ollama.py', 'rag/retrieval_diagnostics.py', 'rag/generation_diagnostics.py')


def fingerprints():
    return {p: hashlib.sha256((ROOT / p).read_text(encoding='utf-8').encode()).hexdigest() for p in CODE_PATHS}


def inspect_result(result, case, corpus, index_hash, generation_digest):
    if result['index_sha256'] != index_hash or result['research_only'] is not True or result['operational_approval'] is not False:
        raise ValueError('Unexpected response identity or scope')
    evidence = result['evidence']
    if not isinstance(evidence, list) or len(evidence) > 3 or len({e['id'] for e in evidence}) != len(evidence):
        raise ValueError('Invalid retrieved passages')
    for row in evidence:
        original = corpus.get(row['id'])
        if original is None or any(row[k] != original[k] for k in ('source', 'text', 'start_line', 'end_line')):
            raise ValueError('Retrieved passage provenance changed')
    generation = result['generation']
    if generation['requested'] is not True:
        raise ValueError('Generation was not requested')
    status, claims = generation['status'], result['claims']
    if status == 'completed':
        if not evidence or generation['model'] != ollama.CHAT_MODEL or generation['model_digest'] != generation_digest:
            raise ValueError('Generation model identity changed')
        try:
            validate_claims({'claims': claims}, evidence)
        except (RuntimeError, TypeError, KeyError) as error:
            raise ValueError('Generated claims failed structural verification') from error
        outcome = 'generated' if claims else 'abstained'
        expected_mode = 'generated' if claims else 'abstained'
    elif status == 'skipped_no_evidence':
        if evidence or claims:
            raise ValueError('Contradictory evidence-free abstention')
        outcome, expected_mode = 'abstained', 'abstained'
    elif status == 'unavailable_or_rejected':
        if not evidence or claims:
            raise ValueError('Contradictory unavailable generation')
        outcome, expected_mode = 'unavailable_or_rejected', 'evidence_only'
    else:
        raise ValueError('Unknown generation outcome')
    if result['mode'] != expected_mode:
        raise ValueError('Contradictory response mode')
    by_id = {e['id']: e for e in evidence}
    covered = [any(by_id[c['citation']]['source'] == t['source'] and t['quote'] in c['quote'] for c in claims) for t in case['targets']]
    # Export only the known public corpus and schema fields; never service errors or arbitrary metadata.
    public_claims = [{**{k: c[k] for k in ('text', 'citation', 'quote')},
                      'source': by_id[c['citation']]['source'],
                      'start_line': by_id[c['citation']]['start_line'],
                      'end_line': by_id[c['citation']]['end_line']} for c in claims]
    return {'outcome': outcome, 'generation_status': status,
            'answer_abstained': outcome == 'abstained' if outcome != 'unavailable_or_rejected' else None,
            'retrieval': score(case['targets'], evidence),
            'retrieved': [{k: e[k] for k in ('id', 'source', 'start_line', 'end_line')} for e in evidence],
            'claims': public_claims, 'target_quote_covered': covered,
            'human_review': {'status': 'pending', 'semantic_correctness': None, 'question_answered': None}}


def summarize(rows):
    evaluated = [r for r in rows if r['outcome'] in ('generated', 'abstained')]
    positive = [r for r in evaluated if r['targets']]
    negative = [r for r in evaluated if not r['targets']]
    targets = sum(len(r['targets']) for r in positive)
    covered = sum(sum(r['target_quote_covered']) for r in positive)
    return {'total_cases': len(rows), 'retrieval_unavailable_cases': sum(r['outcome'] == 'retrieval_unavailable' for r in rows),
            'generation_unavailable_or_rejected_cases': sum(r['outcome'] == 'unavailable_or_rejected' for r in rows),
            'evaluated_answerable_cases': len(positive), 'evaluated_out_of_corpus_cases': len(negative),
            'generated_answers': sum(r['outcome'] == 'generated' for r in rows),
            'structurally_verified_claims': sum(len(r['claims']) for r in rows),
            'evaluated_gold_targets': targets, 'gold_quotes_in_generated_citations': covered,
            'gold_quote_coverage': covered / targets if targets else None,
            'answerable_abstentions': sum(r['outcome'] == 'abstained' for r in positive),
            'outside_answer_abstentions': sum(r['outcome'] == 'abstained' for r in negative),
            'outside_generated_answers': sum(r['outcome'] == 'generated' for r in negative),
            'human_review_pending_cases': len(rows)}


def evaluate(knowledge=None, suite_path=SUITE, progress=None):
    cases, suite_hash = load_cases(suite_path)
    knowledge = knowledge or Knowledge()
    index_hash, payload, *_ = knowledge.load()
    corpus = {c['id']: c for c in payload['chunks']}
    if any(not any(t['source'] == c['source'] and t['quote'] in c['text'] for c in corpus.values()) for case in cases for t in case['targets']):
        raise ValueError('A gold label is absent from indexed passages')
    models = ollama.models()
    if models.get(ollama.EMBED_MODEL) != payload['embedding_digest'] or not models.get(ollama.CHAT_MODEL):
        raise RuntimeError('Required frozen local models unavailable')
    generator_digest, code = models[ollama.CHAT_MODEL], fingerprints()
    rows = []
    started = time.monotonic()
    for case in cases:
        begin = time.monotonic()
        # Only provider/retrieval failures are unavailable; contradictory returned evidence aborts the run.
        try:
            result = knowledge.query(Question(question=case['question'], generate=True))
        except (OSError, RuntimeError):
            result = None
        if result is None:
            observed = {'outcome': 'retrieval_unavailable', 'generation_status': 'not_observed', 'answer_abstained': None,
                        'retrieval': {'available': False, 'abstained': None}, 'retrieved': [], 'claims': [],
                        'target_quote_covered': [False for _ in case['targets']],
                        'human_review': {'status': 'pending', 'semantic_correctness': None, 'question_answered': None}}
        else:
            observed = inspect_result(result, case, corpus, index_hash, generator_digest)
        row = {**case, **observed, 'elapsed_ms': round((time.monotonic() - begin) * 1000, 2)}
        rows.append(row)
        if progress:
            progress(row)
    after = ollama.models()
    if knowledge.load()[0] != index_hash or load_cases(suite_path)[1] != suite_hash or fingerprints() != code or any(after.get(m) != models[m] for m in (ollama.EMBED_MODEL, ollama.CHAT_MODEL)):
        raise ValueError('Index, suite, code or local model identity changed during evaluation')
    return {'format': 'ain-generation-diagnostics-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'Same curated 24-case development suite when using the default suite; no independent held-out labels, semantic accuracy or security qualification.',
            'suite_sha256': suite_hash, 'index_sha256': index_hash, 'corpus_revision': payload['revision'],
            'sources': payload['sources'], 'passages': len(corpus), 'code_sha256': code,
            'embedding_model': ollama.EMBED_MODEL, 'embedding_digest': models[ollama.EMBED_MODEL],
            'generation_model': ollama.CHAT_MODEL, 'generation_digest': generator_digest,
            'metrics': summarize(rows), 'cases': rows,
            'complete': all(r['outcome'] in ('generated', 'abstained') for r in rows),
            'elapsed_ms': round((time.monotonic() - started) * 1000, 2),
            'metric_denominators': 'Quote coverage and answer abstention use completed/skipped-no-evidence cases only; provider failures and rejected generation are not correct abstentions. Exact gold-quote copying is not semantic correctness.',
            'semantic_answer_accuracy_measured': False, 'human_review_complete': False,
            'ranking_prompt_or_threshold_changes': False, 'operational_approval': False, 'production_ready': False}


def run_to_file(output):
    supplied = Path(output)
    target = supplied.resolve()
    journal = target.with_suffix(target.suffix + '.progress.jsonl')
    if not target.is_relative_to(ROOT / '.local') or target.exists() or journal.exists() or any(p.is_symlink() for p in (supplied, *supplied.parents)):
        raise ValueError('Use a new output file under this checkout .local; existing reports and journals are retained')
    target.parent.mkdir(parents=True, exist_ok=True)
    with journal.open('x', encoding='utf-8') as stream:
        def record(value):
            stream.write(json.dumps(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
        record({'event': 'started', 'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': 'Offline curated generation checks; no serving changes'})
        try:
            report = evaluate(progress=lambda row: record({'event': 'case', 'result': row}))
            with target.open('x', encoding='utf-8') as final:
                final.write(json.dumps(report, indent=2) + '\n')
            record({'event': 'completed', 'complete': report['complete']})
        except Exception as error:
            record({'event': 'failed', 'error_type': type(error).__name__})
            raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = run_to_file(args.output)
    print(json.dumps({'metrics': report['metrics'], 'complete': report['complete'], 'elapsed_ms': report['elapsed_ms'], 'human_review_complete': False, 'production_ready': False}))
    raise SystemExit(0 if report['complete'] else 2)


if __name__ == '__main__':
    main()
