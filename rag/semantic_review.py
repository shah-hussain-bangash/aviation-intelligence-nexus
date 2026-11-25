"""Offline, unsigned self-review of frozen generation diagnostics; never auto-label answers."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

from infra.research_model_recovery import ordinary, unique_object
from rag.generation_diagnostics import summarize
from rag.index import ROOT, SOURCES, chunks_for
from rag.retrieval_diagnostics import load_cases

LIMIT = 2_000_000
RATINGS = ('yes', 'no', 'uncertain')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def read_json(path, expected=None):
    raw = ordinary(path, LIMIT).read_bytes()
    if expected is not None:
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected)
                and digest(raw) == expected, 'Exact file SHA-256 required')
    def invalid(value):
        raise ValueError('Nonfinite JSON value')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                      parse_constant=invalid), digest(raw)


def build_packet(report, report_hash):
    require(report.get('format') == 'ain-generation-diagnostics-v1', 'Unsupported diagnostics')
    require(report.get('production_ready') is False and report.get('operational_approval') is False,
            'Research-only diagnostics required')
    cases, suite_hash = load_cases()
    require(report.get('suite_sha256') == suite_hash, 'Current suite differs from recorded suite')
    rows = report.get('cases')
    require(isinstance(rows, list) and len(rows) == len(cases), 'Case inventory mismatch')
    documents, corpus = [], {}
    for source in SOURCES:
        raw = ordinary(ROOT / source, 100_000).read_bytes()
        documents.append({'path': source, 'sha256': digest(raw), 'text': raw.decode('utf-8')})
        corpus.update({c['id']: c for c in chunks_for(source, raw.decode('utf-8'))})
    require(report.get('sources') == [{k: d[k] for k in ('path', 'sha256')} for d in documents],
            'Source bytes differ from recorded corpus')
    reviews = []
    for row, case in zip(rows, cases):
        require(all(row.get(k) == case[k] for k in ('id', 'question', 'targets')), 'Case identity mismatch')
        outcome = row.get('outcome')
        require(outcome in ('generated', 'abstained', 'unavailable_or_rejected', 'retrieval_unavailable'),
                'Unknown outcome')
        retrieved, claims = row.get('retrieved'), row.get('claims')
        require(isinstance(retrieved, list) and len(retrieved) <= 3
                and len({r['id'] for r in retrieved}) == len(retrieved), 'Invalid retrieval inventory')
        evidence = []
        for observed in retrieved:
            chunk = corpus.get(observed['id'])
            require(chunk is not None and observed == {k: chunk[k] for k in ('id', 'source', 'start_line', 'end_line')},
                    'Passage identity differs from recorded corpus')
            evidence.append({**observed, 'text': chunk['text']})
        require(isinstance(claims, list) and len(claims) <= 8, 'Invalid claim inventory')
        require(bool(claims) == (outcome == 'generated'), 'Contradictory claim outcome')
        require(row.get('answer_abstained') == (outcome == 'abstained')
                if outcome in ('generated', 'abstained') else row.get('answer_abstained') is None,
                'Contradictory abstention status')
        for claim in claims:
            require(set(claim) == {'text', 'citation', 'quote', 'source', 'start_line', 'end_line'}, 'Invalid claim fields')
            source = next((e for e in evidence if e['id'] == claim['citation']), None)
            require(source is not None and all(claim[k] == source[k] for k in ('source', 'start_line', 'end_line')),
                    'Claim citation mismatch')
            require(isinstance(claim['text'], str) and 0 < len(claim['text']) <= 4000
                    and isinstance(claim['quote'], str) and claim['quote']
                    and claim['quote'] in source['text'], 'Claim quotation mismatch')
        reviews.append({'id': row['id'], 'case_sha256': digest(canonical(row)), 'evidence': evidence})
    require(report.get('metrics') == summarize(rows), 'Recorded metrics differ from cases')
    return {'format': 'ain-generation-review-packet-v1', 'report_sha256': report_hash,
            'report': report, 'documents': documents, 'reviews': reviews,
            'human_identity_verified': False, 'independent_review': False, 'production_ready': False}


def template(packet, packet_hash):
    annotations = []
    for case, review in zip(packet['report']['cases'], packet['reviews']):
        generated, abstained = case['outcome'] == 'generated', case['outcome'] == 'abstained'
        annotations.append({'id': case['id'], 'case_sha256': review['case_sha256'], 'source_checked': False,
            'question_answered': 'uncertain' if generated else 'not_applicable' if abstained else 'not_evaluable',
            'abstention_appropriate': 'uncertain' if abstained else 'not_applicable' if generated else 'not_evaluable',
            'claims': [{'claim_index': i, 'citation': c['citation'], 'supported': 'uncertain', 'relevant': 'uncertain'}
                       for i, c in enumerate(case['claims'])], 'notes': ''})
    return {'format': 'ain-generation-annotations-v1', 'packet_sha256': packet_hash,
            'reviewer_label': '', 'cases': annotations}


def assess(packet, packet_hash, annotations):
    require(packet == build_packet(packet['report'], packet['report_sha256']), 'Packet contents changed')
    expected = template(packet, packet_hash)
    require(set(annotations) == set(expected) and annotations['format'] == expected['format']
            and annotations['packet_sha256'] == packet_hash, 'Annotation binding mismatch')
    label = annotations['reviewer_label']
    require(isinstance(label, str) and len(label) <= 80, 'Reviewer label exceeds bound')
    require(isinstance(annotations['cases'], list) and len(annotations['cases']) == len(expected['cases']),
            'Every case must be retained')
    results = []
    for row, initial, case in zip(annotations['cases'], expected['cases'], packet['report']['cases']):
        require(isinstance(row, dict) and set(row) == set(initial)
                and all(row[k] == initial[k] for k in ('id', 'case_sha256')), 'Case binding mismatch')
        require(type(row['source_checked']) is bool and isinstance(row['notes'], str)
                and len(row['notes']) <= 2000, 'Invalid review fields')
        require(isinstance(row['claims'], list) and len(row['claims']) == len(initial['claims']), 'Claims must be retained')
        ratings = []
        for claim, original in zip(row['claims'], initial['claims']):
            require(isinstance(claim, dict) and set(claim) == set(original)
                    and type(claim['claim_index']) is int
                    and all(claim[k] == original[k] for k in ('claim_index', 'citation')), 'Claim binding mismatch')
            require(claim['supported'] in RATINGS and claim['relevant'] in RATINGS, 'Invalid claim rating')
            ratings.extend((claim['supported'], claim['relevant']))
        for field in ('question_answered', 'abstention_appropriate'):
            if initial[field] == 'uncertain':
                require(row[field] in RATINGS, 'Invalid decision rating')
                ratings.append(row[field])
            else:
                require(row[field] == initial[field], 'Inapplicable outcome cannot receive credit')
        if case['outcome'] not in ('generated', 'abstained'):
            status = 'not_evaluable'
        elif not label.strip() or not row['source_checked'] or 'uncertain' in ratings:
            status = 'pending'
        else:
            status = 'declared_needs_revision' if 'no' in ratings else 'declared_acceptable'
        results.append({'id': case['id'], 'status': status})
    counts = {status: sum(r['status'] == status for r in results) for status in
              ('pending', 'not_evaluable', 'declared_acceptable', 'declared_needs_revision')}
    return {'format': 'ain-generation-self-review-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'packet_sha256': packet_hash, 'report_sha256': packet['report_sha256'],
            'annotations_sha256': digest(canonical(annotations)), 'reviewer_label': label,
            'counts': counts, 'cases': results, 'all_evaluable_cases_assessed': counts['pending'] == 0,
            'human_identity_verified': False, 'independent_review': False,
            'semantic_benchmark_accuracy_measured': False, 'operational_approval': False,
            'production_ready': False, 'scope': 'Unsigned operator declarations, not authenticated human judgments.'}


def new_output(path):
    require('..' not in Path(path).parts, 'Parent traversal refused')
    path = Path(path).absolute()
    require(path.is_relative_to(ROOT / '.local'), 'Output must stay under private .local')
    require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                    for p in (path, *path.parents)), 'Redirected output refused')
    require(not path.exists(), 'Output already exists')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_new(path, value):
    with new_output(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def export(report_path, report_hash):
    report, observed = read_json(report_path, report_hash)
    packet = build_packet(report, observed)
    folder = ROOT / '.local/generation-review' / uuid4().hex
    packet_path = folder / 'packet.json'
    write_new(packet_path, packet)
    packet_hash = digest(packet_path.read_bytes())
    write_new(folder / 'annotations.json', template(packet, packet_hash))
    # JSON is the exact review source. This text companion is for reading only.
    text = ['AIN — generated-answer self-review', '',
            'Read packet.json for exact claims and full source documents. Edit annotations.json only.',
            'For each evaluable case, check the sources and rate supported/relevant and answered/refusal.',
            'Use yes/no/uncertain. Leave uncertain when undecided. Never rate unavailable runs as correct refusals.',
            'Review labels are unsigned declarations; this does not approve aviation operations.', '',
            f'Packet SHA-256: {packet_hash}', f'Original report SHA-256: {observed}', '']
    for case, review in zip(report['cases'], packet['reviews']):
        text.extend([f"CASE {case['id']} — {case['outcome']}", case['question']])
        for claim in case['claims']:
            text.extend([f"Answer claim: {claim['text']}", f"Citation: {claim['citation']}", f"Quoted text: {claim['quote']}"])
        for passage in review['evidence']:
            text.extend([f"Evidence {passage['id']} | {passage['source']} lines {passage['start_line']}–{passage['end_line']}", passage['text']])
        text.append('')
    with new_output(folder / 'READ_ME.txt').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(text))
    return {'packet': str(packet_path), 'packet_sha256': packet_hash,
            'annotations': str(folder / 'annotations.json'), 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('export')
    create.add_argument('--report', required=True)
    create.add_argument('--report-sha256', required=True)
    check = commands.add_parser('assess')
    check.add_argument('--packet', required=True)
    check.add_argument('--packet-sha256', required=True)
    check.add_argument('--annotations', required=True)
    check.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.action == 'export':
        result = export(args.report, args.report_sha256)
    else:
        packet, observed = read_json(args.packet, args.packet_sha256)
        annotations, _ = read_json(args.annotations)
        result = assess(packet, observed, annotations)
        write_new(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
