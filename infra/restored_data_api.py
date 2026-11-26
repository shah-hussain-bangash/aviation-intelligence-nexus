"""Exercise normal HTTP authentication/read access on a COPY of qualified restored state."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
from http.cookiejar import CookieJar
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
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler
from uuid import uuid4

from infra.rehearsal_admission import require
from infra.research_model_recovery import ordinary, unique_object
from infra.recovery import checksum, FILES
from infra.state_contracts import CONTRACTS, contract_digest, current_contract_digest
from infra.verify_schema8 import source_identity
from services.api.paths import ROOT
from rag.ollama import NoRedirect

SCENARIO = {'carrier': 'AA', 'origin': 'JFK', 'destination': 'LAX',
            'flight_date': '2025-05-15', 'scheduled_departure': '09:00'}
RETRIEVAL_QUERIES = ({'question': 'When do local research sessions expire?', 'generate': False},
                     {'question': 'Explain photosynthesis in chloroplast organelles', 'generate': False})


@contextmanager
def missing_owned_index(case, expected_sha256):
    """Move only an owned case's pinned index aside; retain bytes and never overwrite on restore."""
    case = Path(case).absolute()
    require(case.parent == (ROOT / '.local/restored-api').absolute()
            and re.fullmatch('[0-9a-f]{32}', case.name), 'owned_index_case_required')
    index = ordinary(case / 'state/knowledge/index.json', 4_000_000)
    retained = case / 'retained-knowledge-index.json'
    require(index.resolve().is_relative_to(case.resolve()) and retained.resolve().parent == case.resolve(), 'owned_index_paths_required')
    require(checksum(index) == expected_sha256, 'owned_index_pin_mismatch')
    require(not retained.exists() and not retained.is_symlink() and not getattr(retained, 'is_junction', lambda: False)(),
            'retained_index_path_occupied')
    index.rename(retained)
    try:
        yield
    finally:
        require(not index.exists() and not index.is_symlink() and not getattr(index, 'is_junction', lambda: False)(),
                'index_restore_would_overwrite')
        require(checksum(ordinary(retained, 4_000_000)) == expected_sha256, 'retained_index_changed')
        retained.rename(index)
        require(checksum(index) == expected_sha256, 'owned_index_restore_pin_mismatch')


def retrieval_knowledge(state):
    from rag.index import SOURCES, chunks_for
    from rag.service import Knowledge
    from rag import ollama
    require(os.environ.get('AIN_OLLAMA_HOST') == '127.0.0.1', 'loopback_retrieval_provider_required')
    knowledge = Knowledge(state / 'knowledge/index.json')
    index_hash, payload, *_ = knowledge.load()
    expected = []
    for name in SOURCES:
        expected.extend(chunks_for(name, (ROOT / name).read_text(encoding='utf-8')))
    require(payload['chunks'] == expected, 'retrieval_corpus_binding_failed')
    require(ollama.models().get(ollama.EMBED_MODEL) == payload['embedding_digest'], 'retrieval_model_identity_failed')
    return knowledge, index_hash, payload['embedding_digest']


def admit(report_path, report_sha256, expected_revision):
    require(isinstance(report_sha256, str) and re.fullmatch('[0-9a-f]{64}', report_sha256), 'full_report_pin_required')
    require(isinstance(expected_revision, str) and re.fullmatch('[0-9a-f]{40}', expected_revision), 'full_recovery_revision_required')
    path = ordinary(report_path, 1024 * 1024)
    require(path.name == 'report.json' and path.parent.parent == (ROOT / '.local/full-snapshot-recovery').absolute()
            and re.fullmatch('[0-9a-f]{32}', path.parent.name), 'qualified_private_case_required')
    require(checksum(path) == report_sha256, 'recovery_report_pin_mismatch')
    report = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    require(isinstance(report, dict) and report.get('format') == 'ain-full-snapshot-recovery-v1'
            and report.get('passed') is True and report.get('production_ready') is False, 'successful_recovery_required')
    require(report.get('primary_state_accessed') is False and report.get('source_snapshot_migrated') is False
            and report.get('restored_schema_version') == 8, 'recovery_scope_mismatch')
    identity = report['toolkit_identity']
    require(identity['source_revision'] == expected_revision and identity['working_tree_changes'] is False, 'recovery_revision_mismatch')
    require(report['verifier_sha256'] == checksum(ROOT / 'infra/full_snapshot_recovery.py'), 'recovery_verifier_changed')
    require(contract_digest({name: identity['source_sha256'][name] for name in CONTRACTS}) == current_contract_digest(), 'selected_state_contracts_changed')
    require(report['offline_consistency']['consistency_verified'] is True
            and report['restoration']['session_revocation_event_id'] == report['offline_consistency']['session_revocation_event_id'], 'recovery_evidence_binding_invalid')
    source = path.parent / 'restored'
    require(isinstance(report['artifact_sha256'], dict) and 'ain.sqlite3' not in report['artifact_sha256'], 'artifact_inventory_invalid')
    files = {'ain.sqlite3': report['offline_consistency']['restored_database_sha256'], **report['artifact_sha256']}
    require(set(files).issubset(FILES) and report['restored_table_fingerprints']['auth_sessions']['rows'] == 0, 'restored_inventory_invalid')
    for name, pin in files.items():
        require(isinstance(pin, str) and re.fullmatch('[0-9a-f]{64}', pin), 'restored_file_pin_invalid')
        file = ordinary(source / name, 2 * 1024 ** 3 if name == 'ain.sqlite3' else 4_000_000)
        require(checksum(file) == pin, 'qualified_restored_file_changed')
    for suffix in ('-wal', '-shm', '-journal'):
        p = Path(str(source / 'ain.sqlite3') + suffix)
        require(not p.exists() and not p.is_symlink(), 'qualified_state_sidecar_present')
    return report, source, files


def row_digest(rows):
    digest = hashlib.sha256(); count = 0
    for row in rows:
        digest.update(json.dumps(tuple(row), separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode() + b'\n')
        count += 1
    return {'rows': count, 'sha256': digest.hexdigest()}


def prepare(case, password):
    from services.api.paths import STATE
    from services.api.main import initialize
    from services.api.auth import AuthStore
    case = Path(case).resolve()
    require(case.parent == (ROOT / '.local/restored-api').resolve() and STATE == case / 'state', 'isolated_probe_state_required')
    plan = json.loads((case / 'plan.json').read_text())
    require(checksum(STATE / 'ain.sqlite3') == plan['files']['ain.sqlite3'], 'copy_database_pin_mismatch')
    initialize(STATE / 'ain.sqlite3')
    with closing(sqlite3.connect(STATE / 'ain.sqlite3')) as db:
        db.row_factory = sqlite3.Row
        expected = dict(db.execute("SELECT COUNT(*) AS records,MIN(flight_date) AS first_date,MAX(flight_date) AS last_date,COUNT(DISTINCT carrier) AS carriers FROM flights WHERE source='BTS_REPORTING_CARRIER'").fetchone())
        monthly = [dict(row) for row in db.execute("SELECT substr(flight_date,1,7) AS period,COUNT(*) AS records FROM flights WHERE source='BTS_REPORTING_CARRIER' GROUP BY substr(flight_date,1,7) ORDER BY 1")]
        require(expected['records'] > 0, 'retained_bts_records_required')
        migration = row_digest(db.execute('SELECT version,applied_at FROM schema_migrations ORDER BY version'))
    auth = AuthStore(STATE / 'ain.sqlite3')
    for username, role in zip(plan['usernames'], ('researcher', 'viewer')): auth.create_user(username, password, role)
    result = {'expected_dataset': expected, 'expected_monthly': monthly, 'migration_fingerprint': migration}
    if plan.get('with_prediction'):
        from services.api.prediction import ResearchPredictor, Scenario
        result['expected_prediction'] = ResearchPredictor(STATE / 'models/delay-v2').predict(Scenario.model_validate(SCENARIO))
    if plan.get('with_retrieval'):
        from rag.service import Question
        knowledge, index_hash, embedding_digest = retrieval_knowledge(STATE)
        answers = [knowledge.query(Question(**query)) for query in RETRIEVAL_QUERIES]
        require(answers[0]['evidence'] and not answers[1]['evidence'], 'retrieval_evidence_or_abstention_failed')
        require(any(e['source'] == 'docs/LOCAL_IDENTITY.md' for e in answers[0]['evidence']), 'expected_identity_source_missing')
        result['expected_retrieval'] = {'results': answers, 'index_sha256': index_hash, 'embedding_digest': embedding_digest}
    return result


def inspect_after(case):
    from services.api.paths import STATE
    from infra.full_snapshot_recovery import fingerprints
    case = Path(case).resolve()
    require(case.parent == (ROOT / '.local/restored-api').resolve() and STATE == case / 'state', 'isolated_probe_state_required')
    plan = json.loads((case / 'plan.json').read_text())
    with closing(sqlite3.connect(STATE / 'ain.sqlite3')) as db:
        require(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0, 'probe_checkpoint_failed')
        originals = row_digest(db.execute('SELECT * FROM auth_users WHERE username NOT IN (?,?) ORDER BY id', plan['usernames']))
        old = plan['original_tables']['auth_users']
        require(originals == {'rows': old['rows'], 'sha256': old['sha256']}, 'original_accounts_changed')
        audit_count = plan['original_tables']['security_audit']['rows']
        audit = row_digest(db.execute('SELECT * FROM security_audit ORDER BY sequence LIMIT ?', (audit_count,)))
        require(audit == {'rows': audit_count, 'sha256': plan['original_tables']['security_audit']['sha256']}, 'historical_audit_changed')
        migration = row_digest(db.execute('SELECT version,applied_at FROM schema_migrations ORDER BY version'))
        require(migration == plan['migration_fingerprint'], 'migration_history_changed')
        if plan.get('with_prediction'):
            from services.api.history import ResearchHistory
            owner = db.execute('SELECT id FROM auth_users WHERE username=?', (plan['usernames'][0],)).fetchone()[0]
            original_runs = row_digest(db.execute('SELECT * FROM research_runs WHERE owner_id IS NOT ? ORDER BY id', (owner,)))
            expected = plan['original_tables']['research_runs']
            require(original_runs == {'rows': expected['rows'], 'sha256': expected['sha256']}, 'original_research_rows_changed')
            rows = db.execute('SELECT request_key,input_sha256,scenario_json,result_json,model_version,artifact_sha256 FROM research_runs WHERE owner_id=?', (owner,)).fetchall()
            require(len(rows) == 1, 'probe_prediction_count_unexpected')
            key, input_hash, scenario, result, version, artifact = rows[0]
            saved = plan['prediction_probe']
            require(key == saved['request_key'] and input_hash == ResearchHistory.input_hash(SCENARIO)
                    and json.loads(scenario) == SCENARIO and json.loads(result) == saved['result']
                    and version == 'delay-v2' and artifact == plan['files']['models/delay-v2/model.joblib'], 'stored_prediction_binding_failed')
        if plan.get('with_retrieval'):
            owner = db.execute('SELECT id FROM auth_users WHERE username=?', (plan['usernames'][0],)).fetchone()[0]
            original = row_digest(db.execute('SELECT * FROM knowledge_runs WHERE owner_id IS NOT ? ORDER BY id', (owner,)))
            expected = plan['original_tables']['knowledge_runs']
            require(original == {'rows': expected['rows'], 'sha256': expected['sha256']}, 'original_knowledge_rows_changed')
            saved = plan['retrieval_probe']
            rows = db.execute('SELECT id,result_json,created_at FROM knowledge_runs WHERE owner_id=? ORDER BY rowid', (owner,)).fetchall()
            count = 3 if plan.get('with_retrieval_recovery') else 2
            require(len(rows) == count and len(saved) == count, 'probe_retrieval_count_unexpected')
            require(all(row[0] == result['run_id'] and json.loads(row[1]) == result and row[2] == result['saved_at']
                        for row, result in zip(rows, saved)), 'stored_retrieval_binding_failed')
            _, index_hash, embedding_digest = retrieval_knowledge(STATE)
            require(index_hash == plan['retrieval_identity']['index_sha256']
                    and embedding_digest == plan['retrieval_identity']['embedding_digest'], 'retrieval_identity_changed')
    after = fingerprints(STATE / 'ain.sqlite3')
    for table, expected in plan['original_tables'].items():
        if table not in ('auth_users', 'auth_sessions', 'auth_limits', 'security_audit') and not (plan.get('with_prediction') and table == 'research_runs') and not (plan.get('with_retrieval') and table == 'knowledge_runs'):
            require(after['tables'][table] == expected, 'retained_business_rows_changed')
    require(after['tables']['auth_users']['rows'] == old['rows'] + 2
            and after['tables']['auth_sessions']['rows'] == 0
            and after['tables']['security_audit']['rows'] == audit_count + 6, 'probe_identity_changes_unexpected')
    require(all(checksum(STATE / name) == pin for name, pin in plan['files'].items() if name != 'ain.sqlite3'), 'copied_artifacts_changed')
    checks = {'original_accounts_preserved': True,
            'historical_audit_and_migrations_preserved': True, 'probe_sessions_closed': True,
            'expected_probe_accounts_and_events_only': True, 'artifact_bytes_preserved': True,
            'flight_records': after['tables']['flights']['rows']}
    if plan.get('with_prediction'):
        require(after['tables']['research_runs']['rows'] == plan['original_tables']['research_runs']['rows'] + 1, 'unexpected_research_row_count')
        checks.update(original_business_rows_preserved=True, one_bound_probe_prediction_only=True)
    elif not plan.get('with_retrieval'): checks['business_table_fingerprints_preserved'] = True
    if plan.get('with_retrieval'):
        count = 3 if plan.get('with_retrieval_recovery') else 2
        require(after['tables']['knowledge_runs']['rows'] == plan['original_tables']['knowledge_runs']['rows'] + count, 'unexpected_knowledge_row_count')
        checks.update(original_business_rows_preserved=True, bound_probe_retrieval_rows=count,
                      retrieval_index_and_provider_identity_preserved=True)
        if count == 2: checks['two_bound_probe_retrievals_only'] = True
        else: checks['three_bound_probe_retrievals_only'] = True
    return checks


def client(): return build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(CookieJar()))


def request(opener, base, path, *, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    h = {'Accept': 'application/json', **(headers or {})}
    if data is not None: h['Content-Type'] = 'application/json'
    try: response = opener.open(Request(base + path, data=data, headers=h), timeout=15)
    except HTTPError as error: response = error
    with response:
        raw = response.read(2 * 1024 * 1024 + 1); require(len(raw) <= 2 * 1024 * 1024, 'probe_response_oversized')
        try: parsed = json.loads(raw)
        except (ValueError, UnicodeDecodeError): parsed = None
        return response.status, response.headers, raw, parsed


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    require(process.poll() is not None, 'owned_service_stop_unverified')


def wait_ready(opener, base, processes):
    deadline = time.monotonic() + 40
    while True:
        require(all(p.poll() is None for p in processes), 'owned_service_exited')
        try:
            ready = request(opener, base, '/__ain/ready')
            if ready[0] == 200 and ready[3]['backend_ready'] is True: return
        except (OSError, ValueError, TypeError, KeyError): pass
        require(time.monotonic() < deadline, 'owned_services_not_ready'); time.sleep(.2)


def run_check(report_path, report_sha256, expected_revision, *, web_port=18180, api_port=18102,
              with_prediction=False, trusted_local_model=False, with_retrieval=False, with_retrieval_recovery=False):
    require(type(with_prediction) is bool and (not with_prediction or trusted_local_model is True), 'explicit_trusted_local_model_required')
    require(type(with_retrieval) is bool and not (with_prediction and with_retrieval), 'separate_retrieval_or_prediction_case_required')
    require(type(with_retrieval_recovery) is bool and (not with_retrieval_recovery or with_retrieval),
            'retrieval_recovery_requires_retrieval_mode')
    for port in (web_port, api_port): require(type(port) is int and 1024 <= port <= 65535, 'unprivileged_port_required')
    require(web_port != api_port, 'distinct_probe_ports_required')
    qualification, source, files = admit(report_path, report_sha256, expected_revision)
    if with_prediction:
        require({'models/delay-v2/model.joblib', 'models/delay-v2/report.json'}.issubset(files), 'prediction_model_pair_required')
    if with_retrieval: require('knowledge/index.json' in files, 'retrieval_index_required')
    for port in (web_port, api_port):
        with socket.socket() as probe: probe.bind(('127.0.0.1', port))
    require(shutil.disk_usage(ROOT).free >= sum((source / n).stat().st_size for n in files) * 2 + 512 * 1024 ** 2, 'probe_disk_budget_insufficient')
    case = ROOT / '.local/restored-api' / uuid4().hex
    state = case / 'state'; state.mkdir(parents=True, exist_ok=False)
    usernames = ['probe_' + case.name[:12] + suffix for suffix in ('_research', '_viewer')]
    plan = {'files': files, 'usernames': usernames, 'original_tables': qualification['restored_table_fingerprints'],
            'with_prediction': with_prediction, 'with_retrieval': with_retrieval,
            'with_retrieval_recovery': with_retrieval_recovery}
    env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
    env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
               AIN_SESSION_COOKIE='ain_test_session', AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'),
               AIN_BIND_HOST='127.0.0.1', AIN_API_HOST='127.0.0.1', AIN_API_PORT=str(api_port), PORT=str(web_port))
    if with_retrieval: env['AIN_OLLAMA_HOST'] = '127.0.0.1'
    report = {'format': 'ain-restored-data-api-v1', 'passed': False, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'toolkit_identity': source_identity(), 'verifier_sha256': checksum(Path(__file__)),
              'recovery_revision': expected_revision, 'recovery_report_sha256': report_sha256,
              'primary_state_accessed': False, 'qualified_source_modified': False,
              'probe_plaintext_passwords_persisted': False, 'actual_existing_password_tested': False,
              'prediction_requested': with_prediction, 'retrieval_requested': with_retrieval,
              'retrieval_recovery_requested': with_retrieval_recovery,
              'inference_executed': False, 'embedding_inference_executed': False,
              'model_retrained': False, 'model_accuracy_evaluated': False, 'production_ready': False, 'checks': {}}
    processes = []; logs = []; stage = 'private_copy'

    def worker(function, password=None):
        code = ('import json,sys;from infra.restored_data_api import ' + function + ';print(json.dumps(' + function + '(sys.argv[1]' + (',json.loads(sys.stdin.read())["password"]' if password is not None else '') + ')))')
        result = subprocess.run([sys.executable, '-c', code, str(case)], cwd=ROOT, env=env,
                                input=json.dumps({'password': password}) if password is not None else None,
                                capture_output=True, text=True, timeout=300)
        require(result.returncode == 0, 'probe_worker_failed')
        return json.loads(result.stdout)
    try:
        for name, pin in files.items():
            target = state / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target); require(checksum(target) == pin, 'probe_copy_mismatch')
        (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        password = secrets.token_urlsafe(32); baseline = worker('prepare', password)
        if with_prediction: report['inference_executed'] = True
        if with_retrieval:
            report.update(inference_executed=True, embedding_inference_executed=True)
        plan.update(baseline); (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        stage = 'owned_services'
        commands = ([sys.executable, '-m', 'uvicorn', 'services.api.main:app', '--host', '127.0.0.1', '--port', str(api_port),
                     '--workers', '1', '--log-config', 'infra/request-logging.json', '--no-access-log'], ['node', 'scripts/dev.mjs'])
        for label, command in zip(('api', 'gateway'), commands):
            log = (case / (label + '.log')).open('w', encoding='utf-8'); logs.append(log)
            processes.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        base = 'http://127.0.0.1:' + str(web_port); opener = client()
        wait_ready(opener, base, processes)
        stage = 'authenticated_reads'
        status, headers, html, _ = request(opener, base, '/')
        require(status == 200 and b'Aviation' in html and headers.get('Content-Security-Policy'), 'dashboard_or_headers_failed')
        require(request(opener, base, '/api/v1/research/summary')[0] == 401, 'anonymous_read_not_denied')
        if with_retrieval:
            require(request(opener, base, '/api/v1/research/knowledge-history')[0] == 401
                    and request(opener, base, '/api/v1/research/knowledge-query', body=RETRIEVAL_QUERIES[0], headers={'Origin': base})[0] == 401,
                    'anonymous_retrieval_not_denied')
        origin = {'Origin': base}
        for username, role in zip(usernames, ('researcher', 'viewer')):
            actor = client()
            status, headers, _, login = request(actor, base, '/api/v1/auth/login', body={'username': username, 'password': password}, headers=origin)
            require(status == 200 and login['user']['role'] == role, 'probe_login_failed')
            cookie = headers.get('Set-Cookie', '')
            require(cookie.startswith('ain_test_session=') and 'HttpOnly' in cookie and 'SameSite=strict' in cookie, 'test_cookie_boundary_failed')
            authorized = {**origin, 'X-CSRF-Token': login['csrf_token']}
            result = request(actor, base, '/api/v1/research/summary')
            require(result[0] == 200, 'retained_summary_failed'); dataset = result[3]['dataset']
            require(all(dataset[k] == v for k, v in baseline['expected_dataset'].items()), 'retained_summary_mismatch')
            require([{'period': x['period'], 'records': x['records']} for x in dataset['monthly']] == baseline['expected_monthly'], 'monthly_summary_mismatch')
            require(request(actor, base, '/api/v1/research/history')[3]['runs'] == [], 'original_owner_history_exposed')
            require(request(actor, base, '/api/v1/research/security-audit')[0] == 403, 'admin_audit_boundary_failed')
            if with_retrieval:
                require(request(actor, base, '/api/v1/research/knowledge-history')[3]['runs'] == [], 'original_knowledge_history_exposed')
            if with_retrieval and role == 'researcher':
                saved_queries = []
                for query, expected in zip(RETRIEVAL_QUERIES, baseline['expected_retrieval']['results']):
                    result = request(actor, base, '/api/v1/research/knowledge-query', body=query, headers=authorized)
                    require(result[0] == 200, 'authenticated_retrieval_failed')
                    saved_result = result[3]
                    require(all(saved_result.get(k) == v for k, v in expected.items()), 'retrieval_direct_parity_failed')
                    require(saved_result['claims'] == [] and saved_result['generation'] == {'requested': False, 'status': 'not_requested'}
                            and saved_result['research_only'] is True and saved_result['operational_approval'] is False
                            and saved_result['actor'] == username, 'retrieval_scope_failed')
                    saved_queries.append(saved_result)
                plan['retrieval_probe'] = saved_queries
                plan['retrieval_identity'] = {k: baseline['expected_retrieval'][k] for k in ('index_sha256', 'embedding_digest')}
                (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
                stop_owned(processes[0])
                processes[0] = subprocess.Popen(commands[0], cwd=ROOT, env=env, stdout=logs[0], stderr=subprocess.STDOUT,
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                wait_ready(actor, base, processes)
                require(request(actor, base, '/api/v1/research/knowledge-history')[3]['runs'] == list(reversed(saved_queries)),
                        'retrieval_history_not_preserved_across_api_restart')
                if with_retrieval_recovery:
                    with missing_owned_index(case, files['knowledge/index.json']):
                        unavailable = request(actor, base, '/api/v1/research/knowledge-query', body=RETRIEVAL_QUERIES[0], headers=authorized)
                        require(unavailable[0] == 503 and unavailable[3] == {
                            'error': 'knowledge_unavailable', 'message': 'No saved result returned. Check the index, local models and database.'},
                            'missing_index_response_not_sanitized')
                        require(request(actor, base, '/api/v1/research/knowledge-history')[3]['runs'] == list(reversed(saved_queries)),
                                'failed_query_saved_or_history_changed')
                        require(request(actor, base, '/')[0] == 200, 'dashboard_not_live_during_index_outage')
                    recovered = request(actor, base, '/api/v1/research/knowledge-query', body=RETRIEVAL_QUERIES[0], headers=authorized)
                    require(recovered[0] == 200 and all(recovered[3].get(k) == v for k, v in baseline['expected_retrieval']['results'][0].items()),
                            'restored_index_retrieval_failed')
                    require(recovered[3]['actor'] == username and recovered[3]['run_id'] not in [r['run_id'] for r in saved_queries],
                            'recovered_query_identity_failed')
                    saved_queries.append(recovered[3])
                    plan['retrieval_probe'] = saved_queries
                    (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
                    require(request(actor, base, '/api/v1/research/knowledge-history')[3]['runs'] == list(reversed(saved_queries)),
                            'recovered_query_not_saved')
                    report['retrieval_recovery_checks'] = {'missing_index_returns_exact_sanitized_503': True,
                        'failed_query_adds_no_history': True, 'dashboard_stays_live': True,
                        'restored_index_retrieves_and_saves_bound_result': True}
                    report['retrieval_recovery'] = {'fault': 'owned_copy_index_temporarily_missing', 'query_outage_status': 503,
                        'dashboard_outage_status': 200, 'index_bytes_restored': True,
                        'shared_provider_stopped': False, 'failed_query_saved': False}
                queries = list(RETRIEVAL_QUERIES) + ([RETRIEVAL_QUERIES[0]] if with_retrieval_recovery else [])
                report['retrieval'] = {**plan['retrieval_identity'], 'queries': queries,
                                       'evidence_counts': [len(r['evidence']) for r in saved_queries],
                                       'run_ids': [r['run_id'] for r in saved_queries], 'generation_requested': False,
                                       'owned_api_restart_exercised': True, 'research_only': True}
                report['retrieval_checks'] = {'direct_copy_parity': True, 'positive_evidence_and_unrelated_abstention': True,
                        'no_generation_or_claims': True, 'saved_history_and_session_survive_owned_restart': True}
            if with_retrieval and role == 'viewer':
                denied = request(actor, base, '/api/v1/research/knowledge-query', body=RETRIEVAL_QUERIES[0], headers=authorized)
                require(denied[0] == 403 and 'evidence' not in denied[3], 'viewer_retrieval_mutation_not_denied')
                report['retrieval_checks']['viewer_cannot_query_or_read_researcher_history'] = True
            if with_prediction and role == 'researcher':
                key = str(uuid4()); keyed = {**authorized, 'Idempotency-Key': key}
                first = request(actor, base, '/api/v1/research/predict', body=SCENARIO, headers=keyed)
                require(first[0] == 200 and first[3]['replayed'] is False, 'authenticated_prediction_failed')
                saved = first[3]
                require(all(saved[k] == v for k, v in baseline['expected_prediction'].items()), 'prediction_parity_failed')
                require(saved['research_only'] is True and saved['operational_serving_approved'] is False
                        and saved['artifact_sha256'] == files['models/delay-v2/model.joblib'], 'prediction_scope_or_artifact_changed')
                replay = request(actor, base, '/api/v1/research/predict', body=SCENARIO, headers=keyed)
                require(replay[0] == 200 and replay[3] == {**saved, 'replayed': True}, 'prediction_replay_failed')
                conflict = request(actor, base, '/api/v1/research/predict', body={**SCENARIO, 'scheduled_departure': '10:00'}, headers=keyed)
                require(conflict[0] == 409 and 'arrival_delay_15_probability' not in conflict[3], 'conflicting_request_key_not_denied')
                require(request(actor, base, '/api/v1/research/predict', body={**SCENARIO, 'arrival_delay_minutes': 999}, headers=authorized)[0] == 422, 'target_label_input_accepted')
                plan['prediction_probe'] = {'request_key': key, 'result': saved}
                (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
                stop_owned(processes[0])
                processes[0] = subprocess.Popen(commands[0], cwd=ROOT, env=env, stdout=logs[0], stderr=subprocess.STDOUT,
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                wait_ready(actor, base, processes)
                persisted = request(actor, base, '/api/v1/research/predict', body=SCENARIO, headers=keyed)
                require(persisted[0] == 200 and persisted[3] == {**saved, 'replayed': True}, 'prediction_not_preserved_across_api_restart')
                require(request(actor, base, '/api/v1/research/history')[3]['runs'] == [saved], 'owner_prediction_history_mismatch')
                report['prediction'] = {'scenario_kind': 'historical_research_schedule', 'scenario': SCENARIO,
                                        'probability': saved['arrival_delay_15_probability'], 'artifact_sha256': saved['artifact_sha256'],
                                        'run_id': saved['run_id'], 'research_only': True, 'operational_serving_approved': False,
                                        'owned_api_restart_exercised': True}
                report['prediction_checks'] = {'pinned_artifact_prediction_matches_direct_copy': True,
                        'request_key_replay_same_saved_run': True, 'changed_payload_conflict_denied': True,
                        'label_input_rejected_without_history': True, 'history_and_session_survive_owned_api_restart': True}
            if role == 'viewer': require(request(actor, base, '/api/v1/research/predict', body={}, headers=authorized)[0] == 403, 'viewer_mutation_not_denied')
            if with_prediction and role == 'viewer':
                denied = request(actor, base, '/api/v1/research/predict', body=SCENARIO, headers={**authorized, 'Idempotency-Key': plan['prediction_probe']['request_key']})
                require(denied[0] == 403 and 'arrival_delay_15_probability' not in denied[3], 'viewer_replayed_foreign_prediction')
                report['prediction_checks']['viewer_cannot_replay_or_read_researcher_prediction'] = True
            require(request(actor, base, '/api/v1/auth/logout', body={}, headers=origin)[0] == 403, 'csrf_not_enforced')
            require(request(actor, base, '/api/v1/auth/logout', body={}, headers={**authorized, 'Origin': 'https://untrusted.example'})[0] == 403, 'origin_not_enforced')
            require(request(actor, base, '/api/v1/auth/logout', body={}, headers=authorized)[0] == 200, 'probe_logout_failed')
            require(request(actor, base, '/api/v1/auth/session')[3]['authenticated'] is False, 'probe_session_not_closed')
        report['checks'].update(database_backed_readiness=True, dashboard_and_security_headers=True,
                                anonymous_reads_denied=True, normal_test_cookie_login_logout=True,
                                researcher_and_viewer_see_expected_retained_summary=True,
                                original_owner_history_hidden=True, admin_audit_and_viewer_mutation_denied=True,
                                origin_and_csrf_enforced=True)
        report['dataset_records'] = baseline['expected_dataset']['records']
        report['monthly_records'] = baseline['expected_monthly']
        for process in reversed(processes): stop_owned(process)
        stage = 'state_preservation'; report['copy_state_checks'] = worker('inspect_after')
        admit(report_path, report_sha256, expected_revision)
        report['checks']['qualified_source_and_copied_business_state_preserved'] = True
        report['passed'] = True
    except Exception:
        report.update(passed=False, failed_stage=stage, error='restored_data_api_unverified')
    finally:
        try:
            for process in reversed(processes): stop_owned(process)
            report['owned_services_stopped'] = True
        except (OSError, ValueError, subprocess.SubprocessError):
            report.update(passed=False, owned_services_stopped=False, error='owned_service_cleanup_unverified')
        for log in logs: log.close()
        report['scope'] = ('Native gateway/API rehearsal on another private copy with disposable accounts; '
                           'optional trusted historical prediction writes one probe run; evidence-only retrieval writes two, or three with index recovery; '
                           'no existing password, model training/accuracy evaluation, generated answer, browser interaction, live deployment or off-host qualification.')
        target = case / 'report.json'; target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'report': str(target), 'owned_services_stopped': report['owned_services_stopped'], 'production_ready': False}, indent=2))
    return report, target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery-report', type=Path, required=True); parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--expected-recovery-revision', required=True)
    parser.add_argument('--web-port', type=int, default=18180); parser.add_argument('--api-port', type=int, default=18102)
    parser.add_argument('--with-prediction', action='store_true'); parser.add_argument('--trusted-local-model', action='store_true')
    parser.add_argument('--with-retrieval', action='store_true')
    parser.add_argument('--with-retrieval-recovery', action='store_true')
    args = parser.parse_args()
    try:
        report, _ = run_check(args.recovery_report, args.report_sha256, args.expected_recovery_revision,
                             web_port=args.web_port, api_port=args.api_port,
                             with_prediction=args.with_prediction, trusted_local_model=args.trusted_local_model,
                             with_retrieval=args.with_retrieval, with_retrieval_recovery=args.with_retrieval_recovery)
        return 0 if report['passed'] else 2
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'restored_data_api_admission_refused', 'production_ready': False})); return 2


if __name__ == '__main__': raise SystemExit(main())
