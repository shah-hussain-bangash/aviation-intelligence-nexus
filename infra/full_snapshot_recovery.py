"""Restore a pinned offline snapshot in private copies; never select live state."""
from contextlib import closing
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from uuid import UUID, uuid4

from infra.rehearsal_admission import require
from infra.research_model_recovery import ordinary, unique_object
from infra.recovery import FILES, TABLES as SNAPSHOT_TABLES, checksum
from infra.schema_preflight import COLUMNS, PRIMARY
from infra.verify_schema8 import source_identity
from services.api.migrations import history_version
from services.api.paths import ROOT

BASE_TABLES = tuple(t for t in COLUMNS if t not in ('schema_migrations', 'security_audit'))
MAX_BYTES = 2 * 1024 ** 3


def admit(snapshot, manifest_sha256, *, offline_snapshot=False):
    require(offline_snapshot is True, 'offline_snapshot_acknowledgement_required')
    require(isinstance(manifest_sha256, str) and re.fullmatch('[0-9a-f]{64}', manifest_sha256), 'full_manifest_pin_required')
    snapshot = Path(snapshot).absolute()
    manifest = ordinary(snapshot / 'manifest.json', 64000)
    require(checksum(manifest) == manifest_sha256, 'manifest_pin_mismatch')
    data = json.loads(manifest.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    require(isinstance(data, dict) and data.get('format') == 'ain-recovery-v1', 'snapshot_format_invalid')
    facts = data.get('database')
    require(isinstance(facts, dict) and type(facts.get('schema_version')) is int
            and facts['schema_version'] in (7, 8), 'snapshot_schema_invalid')
    require(isinstance(data.get('snapshot_id'), str), 'snapshot_id_invalid'); UUID(data['snapshot_id'])
    counts = facts.get('row_counts')
    require(isinstance(counts, dict) and bool(counts)
            and all(type(v) is int and v >= 0 for v in counts.values()), 'snapshot_counts_invalid')
    expected_tables = set(SNAPSHOT_TABLES) - ({'security_audit'} if facts['schema_version'] == 7 else set())
    require(set(counts) == expected_tables, 'snapshot_count_inventory_invalid')
    entries = data.get('files')
    require(isinstance(entries, list) and 1 <= len(entries) <= len(FILES), 'snapshot_inventory_invalid')
    inventory = {}
    for entry in entries:
        require(isinstance(entry, dict), 'snapshot_entry_invalid')
        name = entry.get('path')
        require(isinstance(name, str) and name in FILES and name not in inventory, 'snapshot_inventory_invalid')
        require(type(entry.get('size_bytes')) is int and 0 < entry['size_bytes'] <= MAX_BYTES
                and isinstance(entry.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', entry['sha256']), 'snapshot_entry_invalid')
        inventory[name] = entry
    require('ain.sqlite3' in inventory, 'snapshot_database_required')
    require(('models/delay-v2/model.joblib' in inventory) == ('models/delay-v2/report.json' in inventory), 'model_pair_incomplete')
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = Path(str(snapshot / 'ain.sqlite3') + suffix)
        require(not sidecar.exists() and not sidecar.is_symlink(), 'snapshot_sidecar_present')
    for name, entry in inventory.items():
        limit = 64000 if name.endswith('report.json') else 4_000_000 if name == 'knowledge/index.json' else MAX_BYTES
        file = ordinary(snapshot / name, limit)
        require(file.stat().st_size == entry['size_bytes'] and checksum(file) == entry['sha256'], 'snapshot_file_mismatch')
    return data, inventory


def fingerprints(database, *, seconds=300):
    """Stream ordered rows into digests; return no row values or account fields."""
    deadline = time.monotonic() + seconds
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF')
        require(db.execute('PRAGMA integrity_check(1)').fetchone() == ('ok',), 'copy_integrity_failed')
        version = history_version(db, 8)
        result = {'schema_version': version, 'tables': {},
                  'migration_history': db.execute('SELECT version,applied_at FROM schema_migrations ORDER BY version').fetchall()}
        tables = (*BASE_TABLES, 'security_audit') if version == 8 else BASE_TABLES
        for table in tables:
            columns = [r[1] for r in db.execute('PRAGMA table_info("' + table + '")')]
            require(set(COLUMNS[table].split()).issubset(columns), 'copy_schema_incomplete')
            cursor = db.execute('SELECT * FROM "' + table + '" ORDER BY "' + PRIMARY[table] + '"')
            digest = hashlib.sha256(); count = 0
            while rows := cursor.fetchmany(128):
                require(time.monotonic() < deadline, 'fingerprint_budget_exceeded')
                for row in rows:
                    digest.update(json.dumps(row, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode() + b'\n')
                    count += 1
            result['tables'][table] = {'rows': count, 'sha256': digest.hexdigest(), 'columns': columns}
        # Quiescent scope is required for unchanged retained agent rows.
        require(db.execute("SELECT 1 FROM agent_runs WHERE json_type(result_json,'$.state') IS NOT 'text' OR "
                           "json_extract(result_json,'$.state') NOT IN ('awaiting_review','reviewed','needs_changes','failed','cancelled','interrupted') LIMIT 1").fetchone() is None,
                'nonquiescent_agent_snapshot_not_supported')
        return result


def execute_case(case):
    from services.api.paths import STATE
    from services.api.main import initialize
    from infra.recovery import backup, restore
    from infra.verify_restore_evidence import verify_evidence

    case = Path(case).resolve()
    require(case.parent == (ROOT / '.local/full-snapshot-recovery').resolve(), 'private_case_required')
    require(STATE == case / 'state' and os.environ.get('AIN_DB_PATH') == str(STATE / 'ain.sqlite3'), 'isolated_worker_state_required')
    plan = json.loads((case / 'plan.json').read_text(encoding='utf-8'))
    for name, entry in plan['files'].items():
        require(checksum(STATE / name) == entry['sha256'], 'copied_snapshot_changed')
    database = STATE / 'ain.sqlite3'
    before = fingerprints(database)
    require(before['schema_version'] == plan['database']['schema_version'], 'recorded_schema_mismatch')
    expected_counts = plan['database']['row_counts']
    for name, count in expected_counts.items():
        require(name in before['tables'] and before['tables'][name]['rows'] == count, 'recorded_count_mismatch')
    initialize(database)
    # Only the owned copy is checkpointed. The selected input is never migrated.
    with closing(sqlite3.connect(database)) as db:
        require(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0, 'copy_checkpoint_failed')
    upgraded = fingerprints(database)
    require(upgraded['schema_version'] == 8, 'copy_upgrade_failed')
    require(upgraded['migration_history'][:len(before['migration_history'])] == before['migration_history'], 'historical_migration_rows_changed')
    require(all(before['tables'][t] == upgraded['tables'][t] for t in BASE_TABLES), 'upgrade_row_preservation_failed')
    if before['schema_version'] == 7:
        require(upgraded['tables']['security_audit']['rows'] == 0, 'historical_events_invented')
    else:
        require(before['tables']['security_audit'] == upgraded['tables']['security_audit'], 'historical_audit_changed')
    manifest = backup(STATE, case / 'backup')
    receipt = restore(case / 'backup', case / 'restored')
    restored = case / 'restored'
    with closing(sqlite3.connect(restored / 'ain.sqlite3')) as db:
        require(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0, 'restore_checkpoint_failed')
    retained = fingerprints(restored / 'ain.sqlite3')
    require(retained['migration_history'] == upgraded['migration_history'], 'restored_migration_history_changed')
    require(all(upgraded['tables'][t] == retained['tables'][t] for t in BASE_TABLES if t != 'auth_sessions'), 'restore_row_preservation_failed')
    require(retained['tables']['auth_sessions']['rows'] == 0, 'sessions_not_revoked')
    require(retained['tables']['security_audit']['rows'] == upgraded['tables']['security_audit']['rows'] + 1, 'restore_audit_missing')
    artifacts = {name: checksum(STATE / name) for name in plan['files'] if name != 'ain.sqlite3'}
    require({name: checksum(restored / name) for name in artifacts} == artifacts, 'artifact_parity_failed')
    # Quiescent ordinary copies avoid SQLite sidecars in the independent verifier.
    offline = case / 'offline-evidence'; offline.mkdir()
    for label, source in (('backup', case / 'backup'), ('restored', restored)):
        target = offline / label; target.mkdir()
        for entry in manifest['files']:
            name = entry['path']; out = target / name; out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, out)
        name = 'manifest.json' if label == 'backup' else 'recovery-receipt.json'
        shutil.copyfile(source / name, target / name)
    evidence = verify_evidence(offline / 'backup', offline / 'restored', offline_copy=True)
    require(evidence['consistency_verified'], 'offline_evidence_failed')
    require(fingerprints(database) == upgraded, 'upgraded_copy_changed_by_restore')
    return {'passed': True, 'checks': {'manifest_counts_match_copied_database': True,
            'copied_schema_upgrade_preserves_all_base_rows': True, 'all_restored_retained_table_digests_match': True,
            'migration_history_preserved': True,
            'restored_sessions_revoked': True, 'restore_audit_bound_to_receipt': True,
            'artifact_bytes_preserved': True, 'offline_rows_and_receipt_consistent': True,
            'upgraded_copy_unchanged_by_restore': True},
            'input_schema_version': before['schema_version'], 'restored_schema_version': retained['schema_version'],
            'flight_records': retained['tables']['flights']['rows'], 'table_fingerprints_before_upgrade': before['tables'],
            'restored_table_fingerprints': retained['tables'], 'artifact_sha256': artifacts,
            'restoration': receipt, 'offline_consistency': evidence,
            'actual_password_login_tested': False, 'inference_rechecked': False,
            'retrieval_rechecked': False, 'independent_recovery_qualified': False}


def run_check(snapshot, manifest_sha256, *, offline_snapshot=False):
    data, inventory = admit(snapshot, manifest_sha256, offline_snapshot=offline_snapshot)
    needed = 6 * sum(entry['size_bytes'] for entry in inventory.values()) + 1024 ** 3
    require(shutil.disk_usage(ROOT).free >= needed, 'insufficient_private_case_disk_budget')
    case = ROOT / '.local/full-snapshot-recovery' / uuid4().hex
    state = case / 'state'; state.mkdir(parents=True, exist_ok=False)
    report = {'format': 'ain-full-snapshot-recovery-v1', 'passed': False,
              'checked_at': datetime.now(timezone.utc).isoformat(), 'toolkit_identity': source_identity(),
              'verifier_sha256': checksum(Path(__file__)),
              'source_snapshot_id': data['snapshot_id'], 'source_manifest_sha256': manifest_sha256,
              'source_database_sha256': inventory['ain.sqlite3']['sha256'], 'source_snapshot_authenticated': False,
              'source_snapshot_read': True, 'primary_state_accessed': False, 'source_snapshot_migrated': False,
              'production_ready': False}
    try:
        for name, entry in inventory.items():
            target = state / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(snapshot) / name, target)
            require(checksum(target) == entry['sha256'], 'copied_snapshot_mismatch')
        (case / 'plan.json').write_text(json.dumps({'files': inventory, 'database': data['database']}), encoding='utf-8')
        env = {k: v for k, v in os.environ.items() if not k.startswith('AIN_') and k != 'PORT'}
        env.update(AIN_ENV='local', AIN_CONTAINER='0', AIN_AGENT_JOBS='0', AIN_MONITOR_ENABLED='0',
                   AIN_STATE_ROOT=str(state), AIN_DB_PATH=str(state / 'ain.sqlite3'))
        worker = 'import json,sys;from infra.full_snapshot_recovery import execute_case;print(json.dumps(execute_case(sys.argv[1])))'
        result = subprocess.run([sys.executable, '-c', worker, str(case)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=900)
        require(result.returncode == 0, 'isolated_worker_failed')
        outcome = json.loads(result.stdout); require(outcome['passed'] is True, 'snapshot_recovery_failed')
        admit(snapshot, manifest_sha256, offline_snapshot=offline_snapshot)
        report.update(outcome)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        report.update(passed=False, error='full_snapshot_recovery_unverified')
    report['scope'] = 'Manifest-pinned retained snapshot copied, upgraded and restored in private native directories; real retained rows/accounts preserved by streaming digests, restored sessions revoked; no service deployment, actual password login, inference, embedding weights or off-host recovery.'
    target = case / 'report.json'; target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'report': str(target), 'production_ready': False}, indent=2))
    return report, target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--offline-snapshot', action='store_true')
    args = parser.parse_args()
    try:
        report, _ = run_check(args.snapshot, args.manifest_sha256, offline_snapshot=args.offline_snapshot)
        return 0 if report['passed'] else 2
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, sqlite3.Error):
        print(json.dumps({'passed': False, 'error': 'full_snapshot_admission_refused', 'production_ready': False}))
        return 2


if __name__ == '__main__': raise SystemExit(main())
