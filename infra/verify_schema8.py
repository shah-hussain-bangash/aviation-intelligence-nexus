"""Host-only synthetic schema-7 upgrade/recovery rehearsal. Never selects live state."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import time
from uuid import uuid4

from services.api.configuration import validate_environment
from services.api.migrations import require_current
from services.api.paths import ROOT, SCHEMA_VERSION
from infra.recovery import backup, restore, checksum
from infra.releases import require_compatible_pair
from infra.state_contracts import CONTRACTS

FIXTURE = ROOT / 'infra/fixtures/schema7.sql'
FIXTURE_SHA256 = '19a82f18d759702069cdff7ad07689a137eccb558c39ee684fa7e5dd171f2eef'
FIXTURE_REVISION = '515cb8c8121aa8a41e09f5e4d05e62280554b955'
TABLES = ('auth_users', 'auth_sessions', 'auth_limits', 'flights', 'imports', 'research_runs',
          'gate_runs', 'knowledge_runs', 'agent_runs')
SOURCES = tuple(dict.fromkeys((*CONTRACTS, 'services/api/main.py', 'infra/releases.py',
                             'infra/verify_schema8.py', 'infra/verify_restore_evidence.py', 'infra/fixtures/schema7.sql')))


def source_hashes():
    return {p: hashlib.sha256((ROOT / p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES}


def source_identity():
    result = {'source_sha256': source_hashes()}
    env = dict(os.environ)
    try:
        def quote(value): return "'" + value.replace("'", "'\\''") + "'"
        count = int(env.get('GIT_CONFIG_COUNT', '0'))
        pairs = [quote(env.pop(f'GIT_CONFIG_KEY_{i}') + '=' + env.pop(f'GIT_CONFIG_VALUE_{i}')) for i in range(count)]
        if count:
            env['GIT_CONFIG_PARAMETERS'] = (env.get('GIT_CONFIG_PARAMETERS', '') + ' ' + ' '.join(pairs)).strip()
            env['GIT_CONFIG_COUNT'] = '0'
        command = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
        result['source_revision'] = subprocess.check_output([*command, 'rev-parse', 'HEAD'], cwd=ROOT, env=env, stderr=subprocess.DEVNULL, text=True, timeout=10).strip()
        result['working_tree_changes'] = bool(subprocess.check_output([*command, 'status', '--porcelain'], cwd=ROOT, env=env, stderr=subprocess.DEVNULL, text=True, timeout=10).strip())
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        result.update(source_revision=None, working_tree_changes=None)
    return result


def fixture_text():
    if FIXTURE.is_symlink() or FIXTURE.stat().st_size > 64000:
        raise ValueError('fixture_not_verified')
    text = FIXTURE.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode()).hexdigest() != FIXTURE_SHA256:
        raise ValueError('fixture_not_verified')
    return text


def snapshot_rows(database, *, audit=False):
    with closing(sqlite3.connect(database)) as db:
        return {table: db.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                for table in (*TABLES, 'security_audit') if audit or table != 'security_audit'}


def seed_fixture(state, sql, password, token, user_id):
    from services.api.auth import HASHER
    state.mkdir()
    database = state / 'ain.sqlite3'
    with closing(sqlite3.connect(database)) as db:
        db.executescript(sql)
        with db:
            db.execute('INSERT INTO auth_users VALUES (?,?,?,?,1)', (user_id, 'synthetic-admin', HASHER.hash(password), 'admin'))
            db.execute('INSERT INTO auth_sessions VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 3600))
            db.execute("INSERT INTO flights(source,source_record_id,flight_date,carrier,origin,destination) VALUES('synthetic_upgrade_fixture','1','2025-01-01','XX','AAA','BBB')")
            db.execute('INSERT INTO research_runs VALUES (?,?,?,?,?,?,?,?,?)',
                       (str(uuid4()), 'synthetic-history', '0' * 64, '{"synthetic":true}', '{"synthetic":true}',
                        'synthetic-placeholder', '0' * 64, '2025-01-01T00:00:00+00:00', user_id))
        require_current(db, 7)
    model = state / 'models/delay-v2'; model.mkdir(parents=True)
    (model / 'model.joblib').write_bytes(b'SYNTHETIC NONEXECUTABLE MODEL PLACEHOLDER\n')
    (model / 'report.json').write_text(json.dumps({'synthetic': True, 'artifact_sha256': checksum(model / 'model.joblib')}), encoding='utf-8')
    knowledge = state / 'knowledge'; knowledge.mkdir()
    payload = {'version': 1, 'synthetic_fixture': True}
    (knowledge / 'index.json').write_text(json.dumps({'payload': payload, 'sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}), encoding='utf-8')


def require(condition):
    if not condition:
        raise ValueError('rehearsal_check_failed')


def run_rehearsal(directory):
    config = validate_environment(os.environ)
    if SCHEMA_VERSION != 8 or config.container or any(os.environ.get(k) == '1' for k in
            ('AIN_AGENT_JOBS', 'AIN_MONITOR_ENABLED', 'AIN_OBSERVER_MOUNTED', 'AIN_INTAKE_OVERVIEW_MOUNTED')):
        raise ValueError('host_research_environment_required')
    sql = fixture_text()  # Verify before creating any case files.
    identity = source_identity()
    directory = Path(directory)
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (directory, *directory.parents)):
        raise ValueError('unredirected_case_directory_required')
    directory.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-schema8-rehearsal-v1', 'passed': False,
              'case_id': directory.name if re.fullmatch('[0-9a-f]{32}', directory.name) else None,
              'checked_at': datetime.now(timezone.utc).isoformat(), **identity,
              'fixture': {'scope': 'synthetic only; placeholder model/index never used for inference',
                          'schema': 7, 'ddl_source_revision': FIXTURE_REVISION, 'canonical_sql_sha256': FIXTURE_SHA256},
              'checks': {}, 'primary_state_accessed': False, 'image_verified': False,
              'image_or_container_started': False, 'production_ready': False}
    stage = 'fixture'
    try:
        from services.api.main import initialize
        from services.api.auth import AuthStore
        password = secrets.token_urlsafe(32); token = secrets.token_urlsafe(32); user_id = str(uuid4())
        state = directory / 'upgrade-state'; database = state / 'ain.sqlite3'
        seed_fixture(state, sql, password, token, user_id)
        before = snapshot_rows(database)
        artifacts = ('models/delay-v2/model.joblib', 'models/delay-v2/report.json', 'knowledge/index.json')
        original_artifacts = {p: checksum(state / p) for p in artifacts}
        stage = 'pre_upgrade_snapshot'
        old_snapshot = directory / 'schema7-before.sqlite3'
        with closing(sqlite3.connect(database)) as src, closing(sqlite3.connect(old_snapshot)) as dst:
            src.backup(dst)
        old_digest = checksum(old_snapshot)
        stage = 'upgrade'
        initialize(database)
        require(snapshot_rows(database) == before)
        with closing(sqlite3.connect(database)) as db:
            require_current(db, 8)
            require(db.execute('SELECT COUNT(*) FROM security_audit').fetchone()[0] == 0)
        auth = AuthStore(database)
        require(auth.session(token)['id'] == user_id)
        auth.login('synthetic-admin', password, request_id=str(uuid4()))
        upgraded = snapshot_rows(database, audit=True)
        report['checks'].update(upgrade_preserves_existing_rows=True, existing_session_survives_upgrade=True,
                                no_historical_events_invented=True, new_security_event_recorded=len(upgraded['security_audit']) == 1)
        stage = 'schema8_recovery'
        manifest = backup(state, directory / 'schema8-backup')
        receipt = restore(directory / 'schema8-backup', directory / 'schema8-restored')
        recovered_db = directory / 'schema8-restored/ain.sqlite3'
        recovered = snapshot_rows(recovered_db, audit=True)
        require(recovered == {**upgraded, 'auth_sessions': [], 'security_audit': recovered['security_audit']})
        require(len(recovered['security_audit']) == len(upgraded['security_audit']) + 1)
        require(recovered['security_audit'][:-1] == upgraded['security_audit'])
        restore_event = recovered['security_audit'][-1]
        require(restore_event[1] == receipt['session_revocation_event_id'])
        require(restore_event[3:] == ('sign_out', 'success', None, None, None))
        require(manifest['database']['row_counts']['security_audit'] == len(upgraded['security_audit']))
        require(receipt['sessions_revoked'])
        require({p: checksum(directory / 'schema8-restored' / p) for p in artifacts} == original_artifacts)
        stage = 'offline_receipt_evidence'
        # This command owns these synthetic states; all their writers are closed.
        # Never use this raw-copy recipe on a live application database.
        evidence_root = directory / 'offline-evidence'; evidence_root.mkdir()
        evidence_backup = evidence_root / 'backup'; evidence_backup.mkdir()
        evidence_restored = evidence_root / 'restored'; evidence_restored.mkdir()
        for entry in manifest['files']:
            name = entry['path']
            for origin, destination in ((directory / 'schema8-backup', evidence_backup),
                                        (directory / 'schema8-restored', evidence_restored)):
                target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin / name, target)
        shutil.copyfile(directory / 'schema8-backup/manifest.json', evidence_backup / 'manifest.json')
        shutil.copyfile(directory / 'schema8-restored/recovery-receipt.json', evidence_restored / 'recovery-receipt.json')
        from infra.verify_restore_evidence import verify_evidence
        evidence = verify_evidence(evidence_backup, evidence_restored, offline_copy=True)
        require(evidence['consistency_verified'])
        (evidence_root / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
        report['checks']['offline_receipt_evidence_consistent'] = True
        restored_auth = AuthStore(recovered_db)
        require(restored_auth.session(token) is None)
        require(restored_auth.session(restored_auth.login('synthetic-admin', password))['id'] == user_id)
        report['checks'].update(schema8_rows_and_audit_restored=True, restored_sessions_revoked=True,
                                restore_revocation_audited=True,
                                restored_credentials_work=True, placeholder_artifact_hashes_preserved=True,
                                upgraded_source_unchanged_by_restore=snapshot_rows(database, audit=True) == upgraded)
        stage = 'schema7_return_point'
        require(checksum(old_snapshot) == old_digest)
        return_state = directory / 'schema7-return-point'; return_state.mkdir()
        returned_db = return_state / 'ain.sqlite3'; shutil.copyfile(old_snapshot, returned_db)
        with closing(sqlite3.connect(returned_db)) as db, db:
            require_current(db, 7)
            require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
            db.execute('DELETE FROM auth_sessions')
        require(snapshot_rows(returned_db) == {**before, 'auth_sessions': []})
        with closing(sqlite3.connect(database)) as db:
            try:
                require_current(db, 7)
            except RuntimeError:
                incompatible_old_service_rejected = True
            else:
                incompatible_old_service_rejected = False
        require(incompatible_old_service_rejected)
        # Synthetic metadata tests rejection only; these are not real pinned images.
        candidate = {'format': 'ain-local-release-v1', 'schema_version': 8, 'source_revision': 'a' * 40,
                     'images': {'api': 'sha256:' + 'a' * 64, 'web': 'sha256:' + 'b' * 64},
                     'contracts': {p: 'f' * 64 for p in CONTRACTS}}
        target = {**candidate, 'schema_version': 7}
        try:
            require_compatible_pair(candidate, target)
        except ValueError:
            rollback_metadata_rejected = True
        else:
            rollback_metadata_rejected = False
        require(rollback_metadata_rejected)
        report['checks'].update(pre_upgrade_snapshot_unchanged=True, schema7_return_point_rows_verified=True,
                                schema7_return_point_sessions_revoked=True, schema7_guard_rejects_upgraded_database=True,
                                incompatible_rollback_metadata_rejected=True)
        stage = 'source_binding'
        report['checks']['source_unchanged_during_rehearsal'] = source_hashes() == identity['source_sha256']
        require(all(report['checks'].values()))
        report.update(passed=True, schema7_return_point_is_pre_upgrade=True, post_upgrade_events_in_schema7_return_point=False,
                      old_image_executed=False, real_prediction_or_rag_parity_measured=False,
                      encrypted_backup=False, independent_recovery_qualified=False)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, KeyError, TypeError):
        report.update(failed_stage=stage, error='synthetic_rehearsal_failed')
    with (directory / 'report.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    return report


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        report = run_rehearsal(ROOT / '.local/schema8-rehearsals' / uuid4().hex)
    except (OSError, ValueError):
        report = {'format': 'ain-schema8-rehearsal-v1', 'passed': False, 'error': 'rehearsal_admission_refused', 'production_ready': False}
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
