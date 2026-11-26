"""Normal authenticated search using a copied repaired index and fresh synthetic account state."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
from uuid import uuid4

from infra.rehearsal_admission import require
from infra.research_model_recovery import ordinary, unique_object
from infra.recover_retrieval_index import unredirected
from infra.recovery import checksum
from infra.verify_schema8 import source_identity
from infra.restored_data_api import client, request, stop_owned, wait_ready, retrieval_knowledge, RETRIEVAL_QUERIES
from services.api.paths import ROOT


def read_json(path, limit):
    raw = ordinary(path, limit).read_text(encoding='utf-8')
    def invalid(value): raise ValueError('nonfinite_repair_metadata')
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid)


def admit(report_path, report_sha256, expected_revision):
    require(isinstance(report_sha256, str) and re.fullmatch('[0-9a-f]{64}', report_sha256), 'full_repair_report_pin_required')
    require(isinstance(expected_revision, str) and re.fullmatch('[0-9a-f]{40}', expected_revision), 'full_repair_revision_required')
    path = ordinary(report_path, 1_000_000)
    require(path.name == 'report.json' and path.parent.parent == (ROOT / '.local/index-repairs').absolute()
            and re.fullmatch('[0-9a-f]{32}', path.parent.name), 'private_repair_receipt_required')
    require(checksum(path) == report_sha256, 'repair_receipt_pin_mismatch')
    report = read_json(path, 1_000_000)
    require(isinstance(report, dict) and report.get('format') == 'ain-owned-index-repair-v1' and report.get('passed') is True
            and report.get('production_ready') is False and report.get('retained_source_preserved') is True
            and report.get('offline_asserted') is True and report.get('database_accessed') is False
            and report.get('provider_contacted') is False,
            'successful_repair_required')
    require(report['toolkit_identity']['source_revision'] == expected_revision
            and report['toolkit_identity']['working_tree_changes'] is False
            and report['repair_tool_sha256'] == checksum(ROOT / 'infra/recover_retrieval_index.py'), 'repair_tool_binding_changed')
    require(isinstance(report.get('case_id'), str) and re.fullmatch('[0-9a-f]{32}', report['case_id']), 'repair_case_identity_invalid')
    source_case = ROOT / '.local/restored-api' / report['case_id']
    plan_path = ordinary(source_case / 'plan.json', 1_000_000)
    require(checksum(plan_path) == report['plan_sha256'], 'repaired_plan_changed')
    plan = read_json(plan_path, 1_000_000)
    require(isinstance(plan, dict) and plan.get('with_retrieval') is True and plan.get('with_retrieval_recovery') is True
            and plan.get('with_prediction') is False, 'repaired_plan_scope_changed')
    pin = report['restored_file_sha256']
    require(isinstance(pin, str) and re.fullmatch('[0-9a-f]{64}', pin)
            and pin == report['retained_index_sha256'] == plan['files']['knowledge/index.json'], 'repaired_index_identity_invalid')
    index = ordinary(source_case / 'state/knowledge/index.json', 4_000_000)
    retained = ordinary(source_case / 'retained-knowledge-index.json', 4_000_000)
    require(checksum(index) == pin == checksum(retained) and not os.path.samefile(index, retained), 'repaired_artifact_changed')
    from rag.index import ROOT as CORPUS_ROOT, SOURCES, chunks_for
    from rag.service import Knowledge
    index_hash, payload, *_ = Knowledge(index).load()
    chunks = [chunk for name in SOURCES for chunk in chunks_for(name, (CORPUS_ROOT / name).read_text(encoding='utf-8'))]
    require(payload['chunks'] == chunks and index_hash == report['index_sha256'], 'repaired_corpus_binding_failed')
    return index, pin


def owned_case(case):
    from services.api.paths import STATE
    case = Path(case).absolute()
    require(case.parent == (ROOT / '.local/repaired-search').absolute() and re.fullmatch('[0-9a-f]{32}', case.name)
            and STATE == case / 'state' and os.environ.get('AIN_DB_PATH') == str(STATE / 'ain.sqlite3'), 'isolated_repaired_search_state_required')
    unredirected(case)
    return case, STATE


def prepare_case(case):
    case, state = owned_case(case)
    require(not (state / 'ain.sqlite3').exists(), 'fresh_synthetic_database_required')
    plan = read_json(case / 'plan.json', 1_000_000)
    require(checksum(state / 'knowledge/index.json') == plan['index_file_sha256'], 'copied_repaired_index_changed')
    password = json.loads(sys.stdin.read(1000))['password']
    from services.api.main import initialize
    from services.api.auth import AuthStore
    from rag.service import Question
    initialize(state / 'ain.sqlite3')
    auth = AuthStore(state / 'ain.sqlite3')
    for username, role in (('synthetic-admin', 'admin'), ('synthetic-researcher', 'researcher'), ('synthetic-viewer', 'viewer')):
        auth.create_user(username, password, role)
    knowledge, index_hash, digest = retrieval_knowledge(state)
    results = [knowledge.query(Question(**query)) for query in RETRIEVAL_QUERIES]
    require(results[0]['evidence'] and not results[1]['evidence']
            and any(row['source'] == 'docs/LOCAL_IDENTITY.md' for row in results[0]['evidence']), 'repaired_direct_probe_failed')
    return {'index_sha256': index_hash, 'embedding_digest': digest, 'results': results}


def inspect_case(case):
    case, state = owned_case(case)
    plan = read_json(case / 'plan.json', 1_000_000)
    with closing(sqlite3.connect(state / 'ain.sqlite3')) as db:
        require(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0, 'synthetic_checkpoint_failed')
        require(db.execute('SELECT COUNT(*) FROM auth_users').fetchone()[0] == 3
                and db.execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0] == 0
                and db.execute('SELECT COUNT(*) FROM security_audit').fetchone()[0] == 7, 'synthetic_identity_counts_changed')
        require(all(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
                    for table in ('flights', 'imports', 'research_runs', 'gate_runs', 'agent_runs')), 'unexpected_synthetic_business_rows')
        owner = db.execute("SELECT id FROM auth_users WHERE username='synthetic-researcher'").fetchone()[0]
        rows = db.execute('SELECT id,owner_id,result_json,created_at FROM knowledge_runs ORDER BY rowid').fetchall()
        require(len(rows) == 2 and len(plan['saved_results']) == 2, 'synthetic_knowledge_count_changed')
        require(all(row[0] == result['run_id'] and row[1] == owner and json.loads(row[2]) == result
                    and row[3] == result['saved_at'] for row, result in zip(rows, plan['saved_results'])), 'synthetic_saved_result_binding_failed')
    require(checksum(state / 'knowledge/index.json') == plan['index_file_sha256'], 'used_repaired_index_changed')
    return {'exactly_two_owner_bound_runs': True, 'three_synthetic_accounts_only': True,
            'sessions_closed_and_seven_account_events': True, 'no_flight_or_other_business_rows': True,
            'copied_index_preserved': True}


def run_check(report_path, report_sha256, expected_revision, *, web_port=18280, api_port=18202):
    for port in (web_port, api_port): require(type(port) is int and 1024 <= port <= 65535, 'unprivileged_test_ports_required')
    require(web_port != api_port, 'distinct_test_ports_required')
    source, pin = admit(report_path, report_sha256, expected_revision)
    for port in (web_port, api_port):
        with socket.socket() as probe: probe.bind(('127.0.0.1', port))
    case = ROOT / '.local/repaired-search' / uuid4().hex; unredirected(case)
    state = case / 'state'; (state / 'knowledge').mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, state / 'knowledge/index.json')
    require(checksum(state / 'knowledge/index.json') == pin, 'new_index_copy_failed')
    plan = {'scope': 'synthetic_accounts_and_empty_database; copied_repaired_public_document_index', 'index_file_sha256': pin}
    (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
    env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0', AIN_SESSION_COOKIE='ain_test_session',
        AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'), AIN_BIND_HOST='127.0.0.1',
        AIN_API_HOST='127.0.0.1', AIN_API_PORT=str(api_port), AIN_OLLAMA_HOST='127.0.0.1', PORT=str(web_port))
    password = secrets.token_urlsafe(32)
    def worker(name):
        code = 'import json,sys;from infra.verify_repaired_search import ' + name + ';print(json.dumps(' + name + '(sys.argv[1])))'
        result = subprocess.run([sys.executable, '-c', code, str(case)], cwd=ROOT, env=env,
            input=json.dumps({'password': password}) if name == 'prepare_case' else '', capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, 'repaired_search_worker_failed')
        return json.loads(result.stdout)
    report = {'format': 'ain-repaired-search-api-v1', 'passed': False, 'checked_at': datetime.now(timezone.utc).isoformat(),
        'toolkit_identity': source_identity(), 'verifier_sha256': checksum(Path(__file__)), 'repair_report_sha256': report_sha256,
        'repair_revision': expected_revision, 'index_file_sha256': pin, 'checks': {}, 'fixture_flight_records': 0,
        'original_database_accessed': False, 'generation_requested': False, 'flight_prediction_requested': False,
        'embedding_inference_executed': False, 'plaintext_passwords_persisted': False, 'production_ready': False}
    processes, logs = [], []
    stage = 'prepare_synthetic_state'
    try:
        baseline = worker('prepare_case')
        report.update(index_sha256=baseline['index_sha256'], embedding_digest=baseline['embedding_digest'], embedding_inference_executed=True)
        commands = ([sys.executable, '-m', 'uvicorn', 'services.api.main:app', '--host', '127.0.0.1', '--port', str(api_port),
                     '--workers', '1', '--log-config', 'infra/request-logging.json', '--no-access-log'], ['node', 'scripts/dev.mjs'])
        stage = 'owned_services'
        for label, command in zip(('api', 'gateway'), commands):
            log = (case / (label + '.log')).open('w', encoding='utf-8'); logs.append(log)
            processes.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        base = 'http://127.0.0.1:' + str(web_port)
        wait_ready(client(), base, processes)
        stage = 'authenticated_repaired_search'
        require(request(client(), base, '/')[0] == 200 and request(client(), base, '/api/v1/research/knowledge-history')[0] == 401,
                'dashboard_or_anonymous_boundary_failed')
        for role in ('researcher', 'viewer'):
            actor = client(); origin = {'Origin': base}
            login = request(actor, base, '/api/v1/auth/login', body={'username': 'synthetic-' + role, 'password': password}, headers=origin)
            require(login[0] == 200 and login[3]['user']['role'] == role and login[1].get('Set-Cookie', '').startswith('ain_test_session='), 'normal_test_login_failed')
            authorized = {**origin, 'X-CSRF-Token': login[3]['csrf_token']}
            require(request(actor, base, '/api/v1/research/knowledge-history')[3]['runs'] == [], 'initial_owner_history_not_empty')
            if role == 'researcher':
                saved = []
                for query, expected in zip(RETRIEVAL_QUERIES, baseline['results']):
                    result = request(actor, base, '/api/v1/research/knowledge-query', body=query, headers=authorized)
                    require(result[0] == 200 and all(result[3].get(k) == v for k, v in expected.items()), 'repaired_http_direct_parity_failed')
                    require(result[3]['claims'] == [] and result[3]['generation'] == {'requested': False, 'status': 'not_requested'}
                            and result[3]['research_only'] is True and result[3]['operational_approval'] is False, 'repaired_search_scope_changed')
                    saved.append(result[3])
                plan['saved_results'] = saved; (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
                stop_owned(processes[0])
                processes[0] = subprocess.Popen(commands[0], cwd=ROOT, env=env, stdout=logs[0], stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                wait_ready(actor, base, processes)
                require(request(actor, base, '/api/v1/research/knowledge-history')[3]['runs'] == list(reversed(saved)), 'repaired_history_restart_failed')
                report['evidence_counts'] = [len(row['evidence']) for row in saved]
                report['run_ids'] = [row['run_id'] for row in saved]
            else:
                denied = request(actor, base, '/api/v1/research/knowledge-query', body=RETRIEVAL_QUERIES[0], headers=authorized)
                require(denied[0] == 403 and 'evidence' not in denied[3], 'viewer_search_boundary_failed')
            require(request(actor, base, '/api/v1/auth/logout', body={}, headers=origin)[0] == 403, 'repaired_csrf_boundary_failed')
            require(request(actor, base, '/api/v1/auth/logout', body={}, headers=authorized)[0] == 200
                    and request(actor, base, '/api/v1/auth/session')[3]['authenticated'] is False, 'repaired_logout_failed')
        report['checks'] = dict(authenticated_query_matches_direct_repaired_copy=True, unrelated_query_abstains=True,
            session_and_history_survive_owned_restart=True, viewer_cannot_read_owner_or_mutate=True, normal_login_csrf_logout=True)
        for process in reversed(processes): stop_owned(process)
        stage = 'synthetic_state_and_source_preservation'
        report['state_checks'] = worker('inspect_case')
        admit(report_path, report_sha256, expected_revision)
        report['checks']['original_repair_inputs_preserved'] = True
        report['passed'] = True
    except Exception:
        report.update(error='repaired_search_unverified', failed_stage=stage)
    finally:
        cleanup_failed = False
        for process in reversed(processes):
            try: stop_owned(process)
            except (OSError, ValueError, subprocess.SubprocessError): cleanup_failed = True
        report['owned_services_stopped'] = not cleanup_failed
        if cleanup_failed: report.update(passed=False, error='owned_cleanup_unverified')
        for log in logs: log.close()
    report['scope'] = 'Copied repaired public-document index, fresh synthetic accounts and empty database; no original account/database, generation, model-weight recovery, deployment or production qualification.'
    path = case / 'report.json'; path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'report': str(path), 'production_ready': False}))
    return report, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair-report', required=True, type=Path); parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--expected-repair-revision', required=True)
    parser.add_argument('--web-port', type=int, default=18280); parser.add_argument('--api-port', type=int, default=18202)
    args = parser.parse_args()
    try:
        report, _ = run_check(args.repair_report, args.report_sha256, args.expected_repair_revision, web_port=args.web_port, api_port=args.api_port)
        return 0 if report['passed'] else 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'repaired_search_admission_refused', 'production_ready': False})); return 2


if __name__ == '__main__': raise SystemExit(main())
