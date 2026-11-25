"""Exercise normal HTTP authentication/read access on a COPY of qualified restored state."""
import argparse
from contextlib import closing
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
    return {'expected_dataset': expected, 'expected_monthly': monthly, 'migration_fingerprint': migration}


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
    after = fingerprints(STATE / 'ain.sqlite3')
    for table, expected in plan['original_tables'].items():
        if table not in ('auth_users', 'auth_sessions', 'auth_limits', 'security_audit'):
            require(after['tables'][table] == expected, 'retained_business_rows_changed')
    require(after['tables']['auth_users']['rows'] == old['rows'] + 2
            and after['tables']['auth_sessions']['rows'] == 0
            and after['tables']['security_audit']['rows'] == audit_count + 6, 'probe_identity_changes_unexpected')
    require(all(checksum(STATE / name) == pin for name, pin in plan['files'].items() if name != 'ain.sqlite3'), 'copied_artifacts_changed')
    return {'original_accounts_preserved': True, 'business_table_fingerprints_preserved': True,
            'historical_audit_and_migrations_preserved': True, 'probe_sessions_closed': True,
            'expected_probe_accounts_and_events_only': True, 'artifact_bytes_preserved': True,
            'flight_records': after['tables']['flights']['rows']}


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


def run_check(report_path, report_sha256, expected_revision, *, web_port=18180, api_port=18102):
    for port in (web_port, api_port): require(type(port) is int and 1024 <= port <= 65535, 'unprivileged_port_required')
    require(web_port != api_port, 'distinct_probe_ports_required')
    qualification, source, files = admit(report_path, report_sha256, expected_revision)
    for port in (web_port, api_port):
        with socket.socket() as probe: probe.bind(('127.0.0.1', port))
    require(shutil.disk_usage(ROOT).free >= sum((source / n).stat().st_size for n in files) * 2 + 512 * 1024 ** 2, 'probe_disk_budget_insufficient')
    case = ROOT / '.local/restored-api' / uuid4().hex
    state = case / 'state'; state.mkdir(parents=True, exist_ok=False)
    usernames = ['probe_' + case.name[:12] + suffix for suffix in ('_research', '_viewer')]
    plan = {'files': files, 'usernames': usernames, 'original_tables': qualification['restored_table_fingerprints']}
    env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
    env.update(AIN_ENV='test', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
               AIN_SESSION_COOKIE='ain_test_session', AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'),
               AIN_BIND_HOST='127.0.0.1', AIN_API_HOST='127.0.0.1', AIN_API_PORT=str(api_port), PORT=str(web_port))
    report = {'format': 'ain-restored-data-api-v1', 'passed': False, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'toolkit_identity': source_identity(), 'verifier_sha256': checksum(Path(__file__)),
              'recovery_revision': expected_revision, 'recovery_report_sha256': report_sha256,
              'primary_state_accessed': False, 'qualified_source_modified': False,
              'probe_plaintext_passwords_persisted': False, 'actual_existing_password_tested': False,
              'inference_executed': False, 'production_ready': False, 'checks': {}}
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
        plan.update(baseline); (case / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
        stage = 'owned_services'
        commands = ([sys.executable, '-m', 'uvicorn', 'services.api.main:app', '--host', '127.0.0.1', '--port', str(api_port),
                     '--workers', '1', '--log-config', 'infra/request-logging.json', '--no-access-log'], ['node', 'scripts/dev.mjs'])
        for label, command in zip(('api', 'gateway'), commands):
            log = (case / (label + '.log')).open('w', encoding='utf-8'); logs.append(log)
            processes.append(subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        base = 'http://127.0.0.1:' + str(web_port); opener = client(); deadline = time.monotonic() + 40
        while True:
            require(all(p.poll() is None for p in processes), 'owned_service_exited')
            try:
                ready = request(opener, base, '/__ain/ready')
                if ready[0] == 200 and ready[3]['backend_ready'] is True: break
            except (OSError, ValueError, TypeError, KeyError): pass
            require(time.monotonic() < deadline, 'owned_services_not_ready'); time.sleep(.2)
        stage = 'authenticated_reads'
        status, headers, html, _ = request(opener, base, '/')
        require(status == 200 and b'Aviation' in html and headers.get('Content-Security-Policy'), 'dashboard_or_headers_failed')
        require(request(opener, base, '/api/v1/research/summary')[0] == 401, 'anonymous_read_not_denied')
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
            if role == 'viewer': require(request(actor, base, '/api/v1/research/predict', body={}, headers=authorized)[0] == 403, 'viewer_mutation_not_denied')
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
        report['scope'] = 'Native gateway/API rehearsal on another private copy with disposable researcher/viewer accounts; no existing password, model inference, browser interaction, live deployment or off-host qualification.'
        target = case / 'report.json'; target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'report': str(target), 'owned_services_stopped': report['owned_services_stopped'], 'production_ready': False}, indent=2))
    return report, target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery-report', type=Path, required=True); parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--expected-recovery-revision', required=True)
    parser.add_argument('--web-port', type=int, default=18180); parser.add_argument('--api-port', type=int, default=18102)
    args = parser.parse_args()
    try:
        report, _ = run_check(args.recovery_report, args.report_sha256, args.expected_recovery_revision, web_port=args.web_port, api_port=args.api_port)
        return 0 if report['passed'] else 2
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        print(json.dumps({'passed': False, 'error': 'restored_data_api_admission_refused', 'production_ready': False})); return 2


if __name__ == '__main__': raise SystemExit(main())
