"""Pinned recorded retrieval diagnostics; no model calls, queries, fitting or live-health claim."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from services.api.paths import ROOT
from rag.index import SOURCES
from rag.retrieval_diagnostics import summarize

REPORT = 'docs/reports/Retrieval_Diagnostics.json'
REPORT_SHA256 = 'eb8a40b32b0d30af8d1f2e7a8815fd220808f28bf53a019ef6d12258b6e0c57f'
SUITE = 'rag/retrieval_cases.json'
SUITE_SHA256 = '2c1ecd454f8011d18613a6d41690cb4ef9a3413eb2dfaa5cc2ad3a14c28b7eba'


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid retrieval value')
    return value


def near(left, right):
    if not math.isclose(finite(left), finite(right), abs_tol=1e-9, rel_tol=1e-9):
        raise ValueError('Inconsistent retrieval arithmetic')


def validate_report(report, suite):
    if report['format'] != 'ain-retrieval-diagnostics-v1' or report['suite_sha256'] != SUITE_SHA256 or report['generated_answers'] != 0 or type(report['generated_answers']) is not int or any(report[k] is not False for k in ['ranking_or_threshold_changes', 'semantic_answer_accuracy_measured', 'operational_approval', 'production_ready']):
        raise ValueError('Invalid recorded retrieval scope')
    if suite['format'] != 'ain-retrieval-cases-v1' or len(report['cases']) != 24 or len(suite['cases']) != 24 or type(report['complete']) is not bool:
        raise ValueError('Incomplete retrieval suite')
    if not isinstance(report['corpus_revision'], str) or not re.fullmatch('[0-9a-f]{40}', report['corpus_revision']):
        raise ValueError('Invalid recorded corpus revision')
    for value in [report['index_sha256'], report['embedding_digest'], *[s['sha256'] for s in report['sources']]]:
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):raise ValueError('Invalid retrieval fingerprint')
    if [s['path'] for s in report['sources']] != list(SOURCES) or report['passages'] != 31 or type(report['passages']) is not int:
        raise ValueError('Unexpected recorded corpus')
    if datetime.fromisoformat(report['checked_at']).tzinfo is None:raise ValueError('Missing evaluation timezone')
    finite(report['elapsed_ms'])
    for key in ['scope', 'metric_denominators']:
        if not isinstance(report[key], str) or not report[key]:raise ValueError('Missing evaluation limitations')
    for row, gold in zip(report['cases'], suite['cases']):
        if {k: row[k] for k in ['id','question','targets']} != gold:raise ValueError('Evaluation labels changed')
        finite(row['case_elapsed_ms'])
        for method in ['hybrid','lexical']:
            result = row[method]
            if type(result['available']) is not bool:raise ValueError('Invalid availability')
            if not result['available']:
                if result['abstained'] is not None or result['retrieved'] != []:raise ValueError('Unavailable is not an abstention')
                continue
            retrieved = result['retrieved'];ranks = result['target_ranks']
            if not isinstance(retrieved, list) or len(retrieved) > 3 or len(ranks) != len(row['targets']):raise ValueError('Invalid passage count')
            for item in retrieved:
                if item['source'] not in SOURCES or not re.fullmatch('[0-9a-f]{20}', item['id']) or type(item['start_line']) is not int or type(item['end_line']) is not int or not 1 <= item['start_line'] <= item['end_line'] <= 100000:
                    raise ValueError('Invalid passage provenance')
            for rank, target in zip(ranks, row['targets']):
                if rank is not None and (type(rank) is not int or not 1 <= rank <= len(retrieved) or retrieved[rank-1]['source'] != target['source']):raise ValueError('Invalid target rank')
            hits = sum(r is not None for r in ranks)
            if type(result['target_hits']) is not int or result['target_hits'] != hits or result['all_targets_found'] is not (bool(ranks) and hits == len(ranks)) or result['abstained'] is not (not retrieved):
                raise ValueError('Contradictory retrieval result')
            near(result['reciprocal_rank_sum'], sum(1/r for r in ranks if r is not None))
    if report['complete'] is not all(row['hybrid']['available'] for row in report['cases']):raise ValueError('Invalid completion claim')
    for method in ['hybrid','lexical']:
        expected = summarize(report['cases'], method);actual = report['metrics'][method]
        if set(actual) != set(expected):raise ValueError('Incomplete retrieval metrics')
        for key, value in expected.items():
            if value is None:
                if actual[key] is not None:raise ValueError('Unavailable metric must be null')
            elif type(value) is int:
                if type(actual[key]) is not int or actual[key] != value:raise ValueError('Invalid metric count')
            else:near(actual[key], value)
    return report


def load_retrieval_evaluation(root=ROOT):
    root = Path(root);values = []
    for name, expected in [(REPORT, REPORT_SHA256), (SUITE, SUITE_SHA256)]:
        file = root / name
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()) or file.stat().st_size > 200000:raise ValueError('Invalid fixed evidence file')
        text = file.read_text(encoding='utf-8')
        if hashlib.sha256(text.encode()).hexdigest() != expected:raise ValueError('Recorded retrieval evidence changed')
        values.append(json.loads(text))
    report = validate_report(*values)
    return {**report, 'integrity_verified': True, 'report_sha256': REPORT_SHA256}
