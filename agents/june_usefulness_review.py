"""Read-only export and unsigned human assessment of a retained June HTTP draft."""
import argparse
import hashlib
import json
from pathlib import Path

from agents.june_evidence import valid_observation
from agents.quality import assess_report, report_evidence
from agents.store import sha
from pipelines.synthetic_ingestion import host, local
from rag.semantic_review import canonical, new_output, read_json, require
from services.api.june_evaluation import load_june_evaluation
from services.api.paths import ROOT

CHECKS = frozenset('isolated_api_started owned_gateway_and_api_ready dashboard_security_headers anonymous_denied viewer_submission_denied csrf_enforced origin_enforced researcher_operations_denied worker_and_provider_available authenticated_enqueue owned_completed_draft authenticated_response_headers canonical_june_tool_and_coverage unreviewed_research_only model_identity_recorded same_key_replay_without_provider_calls cross_owner_read_denied admin_named_execution_observed logout_revokes_access fresh_session_reads_same_saved_draft actual_provider_completed_within_bounds isolated_services_stopped execution_source_unchanged'.split())


def validate(receipt):
    require(receipt.get('format') == 'ain-june-authenticated-http-v1'
            and receipt.get('passed') is True and receipt.get('failure_type') is None
            and receipt.get('provider_mode') == 'live_ollama'
            and receipt.get('production_ready') is False
            and receipt.get('genuine_human_usefulness_assessed') is False,
            'A completed live June HTTP receipt is required')
    checks = receipt.get('checks', {})
    require(set(checks) == CHECKS and all(v is True for v in checks.values()), 'Execution checks incomplete')
    require(receipt.get('recorded_june_report_sha256') == load_june_evaluation()['report_sha256'], 'June source changed')
    run = receipt['run']
    require(run['state'] == 'awaiting_review' and run['reviews'] == []
            and run['research_only'] is True and run['operational_approval'] is False
            and run['execution'] == 'local-background-queue-v1', 'Unreviewed research draft required')
    require(run['report_sha256'] == sha({k: run[k] for k in ('request', 'steps', 'claims')})
            and len(run['steps']) == 1 and run['steps'][0]['tool'] == 'june_evidence'
            and valid_observation(run['steps'][0]['observation']) and assess_report(run)['passed'], 'Draft evidence changed')
    chats = [c for c in receipt.get('provider_calls', []) if c.get('route') == 'chat']
    require({'planner', 'generator'} == {c.get('purpose') for c in chats}
            and all(c.get('state') == 'returned' and c.get('done') is True and c.get('done_reason') == 'stop' for c in chats)
            and 1 <= sum(c['purpose'] == 'planner' for c in chats) <= 3
            and 1 <= sum(c['purpose'] == 'generator' for c in chats) <= 2, 'Completed bounded provider calls required')
    return run


def blank(packet, pin):
    return {'format': 'ain-june-usefulness-annotations-v1', 'packet_sha256': pin,
            'reviewer_label': '', 'source_checked': False, 'own_assessment': False,
            'question_answered': '', 'notes': '', 'claims': [
                {'claim_index': i, 'claim_sha256': hashlib.sha256(canonical(c)).hexdigest(),
                 'supported': '', 'relevant': ''} for i, c in enumerate(packet['receipt']['run']['claims'])]}


def assess(packet, pin, value):
    require(set(packet) == {'format', 'receipt_sha256', 'receipt'} and packet['format'] == 'ain-june-usefulness-packet-v1', 'Invalid packet')
    validate(packet['receipt'])
    require(hashlib.sha256(canonical(packet)).hexdigest() == pin, 'Packet fingerprint changed')
    expected = blank(packet, pin)
    require(isinstance(value, dict) and set(value) == set(expected)
            and value['format'] == expected['format'] and value['packet_sha256'] == pin, 'Annotation binding changed')
    require(isinstance(value['reviewer_label'], str) and len(value['reviewer_label']) <= 80
            and isinstance(value['notes'], str) and len(value['notes']) <= 2000
            and type(value['source_checked']) is bool and type(value['own_assessment']) is bool, 'Invalid reviewer fields')
    ratings = ('', 'yes', 'no', 'uncertain')
    decisions = [value['question_answered']]
    require(value['question_answered'] in ratings and isinstance(value['claims'], list)
            and len(value['claims']) == len(expected['claims']), 'Invalid claim inventory')
    for row, original in zip(value['claims'], expected['claims']):
        require(isinstance(row, dict) and set(row) == set(original)
                and type(row['claim_index']) is int and row['claim_index'] == original['claim_index']
                and row['claim_sha256'] == original['claim_sha256']
                and row['supported'] in ratings and row['relevant'] in ratings, 'Claim binding changed')
        decisions.extend((row['supported'], row['relevant']))
    pending = not value['reviewer_label'].strip() or not value['source_checked'] or not value['own_assessment'] or any(v in ('', 'uncertain') for v in decisions)
    return {'status': 'pending' if pending else 'declared_needs_revision' if 'no' in decisions else 'declared_acceptable',
            'packet_sha256': pin, 'annotations_sha256': hashlib.sha256(canonical(value)).hexdigest(),
            'human_identity_verified': False, 'independent_review': False,
            'operational_approval': False, 'production_ready': False}


def prepare(receipt_path, receipt_hash, output):
    host(); source = local(receipt_path)
    require(source.is_relative_to(ROOT / '.local'), 'Use a private retained receipt')
    receipt, observed = read_json(source, receipt_hash); run = validate(receipt)
    packet = {'format': 'ain-june-usefulness-packet-v1', 'receipt_sha256': observed, 'receipt': receipt}
    raw = canonical(packet); pin = hashlib.sha256(raw).hexdigest()
    target = new_output(output); target.mkdir(exist_ok=False)
    (target / 'packet.json').write_bytes(raw)
    (target / 'annotations.json').write_text(json.dumps(blank(packet, pin), indent=2), encoding='utf-8')
    text = ['AIN — June answer usefulness review', '',
            'Temporary synthetic accounts; historical US research. Unsigned self-review only.',
            'Read the objective, each exact finding and its source before rating. Leave uncertain items uncertain.',
            'Do not include passwords or personal information. Edit annotations.json privately.',
            'This does not approve the saved draft, verify reviewer identity or qualify production.', '',
            'Packet SHA-256: ' + pin, 'Execution revision: ' + str(receipt.get('source_revision')),
            'Original receipt SHA-256: ' + observed, '', 'Objective:', run['request']['objective'], '']
    for i, claim in enumerate(run['claims']):
        text.extend([f'Finding {i}:', claim['text'], 'Citation: ' + claim['citation'], ''])
    for evidence in report_evidence(run):text.extend(['Source ' + evidence['id'] + ':', evidence['text'], ''])
    (target / 'review.txt').write_text('\n'.join(text), encoding='utf-8')
    return {'packet_sha256': pin, 'receipt_sha256': observed, 'output': str(target),
            'status': 'pending', 'human_ratings_supplied': False, 'production_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    export = sub.add_parser('prepare'); export.add_argument('--receipt', type=Path, required=True)
    export.add_argument('--receipt-sha256', required=True); export.add_argument('--output', type=Path, required=True)
    review = sub.add_parser('assess'); review.add_argument('--packet', type=Path, required=True)
    review.add_argument('--packet-sha256', required=True); review.add_argument('--annotations', type=Path, required=True)
    review.add_argument('--annotations-sha256', required=True)
    args = parser.parse_args(); host()
    if args.action == 'prepare': result = prepare(args.receipt, args.receipt_sha256, args.output)
    else:
        packet, pin = read_json(args.packet, args.packet_sha256)
        annotations, _ = read_json(args.annotations, args.annotations_sha256)
        result = assess(packet, pin, annotations)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
