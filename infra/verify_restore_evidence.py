"""Read-only consistency checks for a fresh, quiescent, explicitly offline schema-8 restore."""
import argparse
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat
import time

from services.api.paths import SCHEMA_VERSION
from services.api.migrations import require_current
from services.api.security_audit import identifier, require_audit_contract
from infra.recovery_state import require_complete_restore
from infra.schema_preflight import COLUMNS, PRIMARY

FILES = ('ain.sqlite3', 'models/delay-v2/model.joblib', 'models/delay-v2/report.json', 'knowledge/index.json')
COUNTED_TABLES = ('flights', 'imports', 'auth_users', 'auth_sessions', 'research_runs', 'gate_runs', 'knowledge_runs', 'agent_runs', 'security_audit')
MAX_BYTES = 2 * 1024 ** 3
SECONDS = 120


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def verify_evidence(backup, restored, *, offline_copy=False):
    report = {'format': 'ain-restore-evidence-check-v1', 'consistency_verified': False,
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'fresh_quiescent_offline_schema8_restore', 'checks': {}, 'errors': [],
              'receipt_authenticated': False, 'backup_origin_authenticated': False,
              'historical_audit_authenticated': False, 'data_modified': False, 'production_ready': False}
    deadline = time.monotonic() + SECONDS
    tracked = {}

    def budget():
        require(time.monotonic() < deadline, 'verification_budget_exceeded')

    def local(path):
        path = Path(path).absolute()
        require(not str(path).startswith(('\\\\', '//')), 'local_paths_required')
        require(not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)), 'unredirected_paths_required')
        return path.resolve()

    def present(path):
        budget()
        try:path.lstat()
        except FileNotFoundError:return False
        return True

    def facts(path, limit):
        budget(); info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and not path.is_symlink(), 'ordinary_files_required')
        require(0 < info.st_size <= limit, 'file_size_not_allowed')
        if path.name == 'ain.sqlite3':
            require(not any(present(Path(str(path) + suffix))
                            for suffix in ('-wal', '-shm', '-journal')), 'sqlite_sidecar_present')
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def digest(path):
        value = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                budget(); value.update(chunk)
        return value.hexdigest()

    def track(path, limit=MAX_BYTES):
        path = local(path); before = facts(path, limit); fingerprint = digest(path)
        require(facts(path, limit) == before, 'file_changed')
        if path in tracked:
            require(tracked[path][:2] == (before, fingerprint), 'file_changed')
        tracked[path] = (before, fingerprint, limit)
        return fingerprint

    def read_json(path, limit):
        fingerprint = track(path, limit)
        def reject_constant(value): raise Refused('nonfinite_json')
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)
        require(isinstance(data, dict), 'json_object_required')
        return data, fingerprint

    def database(stack, path):
        connection = stack.enter_context(closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=0)))
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        connection.execute('PRAGMA query_only=ON'); connection.execute('PRAGMA trusted_schema=OFF')
        require(connection.execute('PRAGMA integrity_check(1)').fetchone() == ('ok',), 'database_integrity_failed')
        require_current(connection, 8); require_audit_contract(connection)
        tables = dict(connection.execute("SELECT name,type FROM sqlite_schema WHERE type IN ('table','view')"))
        for table, columns in COLUMNS.items():
            require(tables.get(table) == 'table', 'required_table_missing')
            actual = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            require(set(columns.split()).issubset({c[1] for c in actual}), 'required_columns_missing')
            require([c[1] for c in actual if c[5]] == [PRIMARY[table]], 'primary_key_mismatch')
        return connection

    def compare_rows(source, target, table):
        left = source.execute(f'SELECT * FROM "{table}" ORDER BY "{PRIMARY[table]}"')
        right = target.execute(f'SELECT * FROM "{table}" ORDER BY "{PRIMARY[table]}"')
        while True:
            budget(); a = left.fetchmany(256); b = right.fetchmany(256)
            require(a == b, 'retained_rows_mismatch')
            if not a: break

    try:
        require(offline_copy is True, 'offline_copy_acknowledgement_required')
        require(SCHEMA_VERSION == 8, 'schema8_only')
        backup = local(backup); restored = local(restored)
        require(backup != restored, 'distinct_directories_required')
        require_complete_restore(backup / 'ain.sqlite3'); require_complete_restore(restored / 'ain.sqlite3')
        manifest, manifest_hash = read_json(backup / 'manifest.json', 64000)
        receipt, receipt_hash = read_json(restored / 'recovery-receipt.json', 16000)
        require(manifest.get('format') == 'ain-recovery-v1', 'backup_manifest_format_invalid')
        require(receipt.get('format') == 'ain-restore-receipt-v1', 'restore_receipt_format_invalid')
        snapshot_id = identifier(manifest.get('snapshot_id'))
        event_id = identifier(receipt.get('session_revocation_event_id'))
        require(snapshot_id is not None and receipt.get('snapshot_id') == snapshot_id, 'snapshot_binding_invalid')
        require(event_id is not None, 'audited_restore_receipt_required')
        require(type(receipt.get('schema_version')) is int and receipt['schema_version'] == 8, 'receipt_schema_invalid')
        flags = ('checksums_verified', 'database_integrity_verified', 'row_counts_preserved', 'sessions_revoked', 'session_revocation_audited')
        require(all(receipt.get(k) is True for k in flags) and receipt.get('production_qualified') is False, 'receipt_flags_invalid')
        require(receipt.get('session_revocation_scope') == 'all_restored_sessions', 'revocation_scope_invalid')
        require(type(receipt.get('revoked_session_rows')) is int and receipt['revoked_session_rows'] >= 0, 'revocation_count_invalid')
        changes = receipt.get('expected_row_changes')
        require(isinstance(changes, dict) and all(type(v) is int for v in changes.values())
                and changes == {'auth_sessions': -receipt['revoked_session_rows'], 'security_audit': 1}, 'row_changes_invalid')
        entries = manifest.get('files')
        require(isinstance(entries, list) and 1 <= len(entries) <= len(FILES), 'backup_inventory_invalid')
        names = []; hashes = {}
        for entry in entries:
            require(isinstance(entry, dict), 'backup_inventory_invalid')
            name = entry.get('path')
            require(isinstance(name, str) and name in FILES and name not in names, 'backup_inventory_invalid')
            require(type(entry.get('size_bytes')) is int and 0 < entry['size_bytes'] <= MAX_BYTES, 'backup_inventory_invalid')
            require(isinstance(entry.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', entry['sha256']), 'backup_inventory_invalid')
            limit = 64000 if name.endswith('report.json') else 4000000 if name == 'knowledge/index.json' else MAX_BYTES
            fingerprint = track(backup / name, limit)
            require(fingerprint == entry['sha256'] and (backup / name).stat().st_size == entry['size_bytes'], 'backup_file_mismatch')
            names.append(name); hashes[name] = fingerprint
        require('ain.sqlite3' in names, 'backup_database_missing')
        require(('models/delay-v2/model.joblib' in names) == ('models/delay-v2/report.json' in names), 'model_pair_incomplete')
        for name in names:
            fingerprint = track(restored / name, 64000 if name.endswith('report.json') else 4000000 if name == 'knowledge/index.json' else MAX_BYTES)
            if name != 'ain.sqlite3': require(fingerprint == hashes[name], 'restored_artifact_mismatch')
        require(not (tracked[backup / 'ain.sqlite3'][0][:2] == tracked[restored / 'ain.sqlite3'][0][:2]
                     and tracked[backup / 'ain.sqlite3'][0][1] != 0), 'distinct_database_files_required')
        for name in FILES:
            require(present(backup / name) == (name in names), 'backup_inventory_mismatch')
            require(present(restored / name) == (name in names), 'restored_inventory_mismatch')
        if 'models/delay-v2/report.json' in names:
            metadata, _ = read_json(backup / 'models/delay-v2/report.json', 64000)
            require(metadata.get('artifact_sha256') == hashes['models/delay-v2/model.joblib'], 'model_report_binding_invalid')
        if 'knowledge/index.json' in names:
            envelope, _ = read_json(backup / 'knowledge/index.json', 4000000)
            require('payload' in envelope and envelope.get('sha256') == hashlib.sha256(json.dumps(envelope['payload'], sort_keys=True).encode()).hexdigest(), 'index_envelope_invalid')
        require(type(receipt.get('active_model_restored')) is bool and receipt['active_model_restored'] == ('models/delay-v2/model.joblib' in names), 'receipt_artifact_flags_invalid')
        require(type(receipt.get('knowledge_index_restored')) is bool and receipt['knowledge_index_restored'] == ('knowledge/index.json' in names), 'receipt_artifact_flags_invalid')
        with ExitStack() as stack:
            source = database(stack, backup / 'ain.sqlite3'); target = database(stack, restored / 'ain.sqlite3')
            source_counts = {table: source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in COUNTED_TABLES}
            recorded = manifest.get('database')
            require(isinstance(recorded, dict) and type(recorded.get('schema_version')) is int and recorded['schema_version'] == 8, 'backup_schema_invalid')
            counts = recorded.get('row_counts')
            require(isinstance(counts, dict) and all(type(v) is int and v >= 0 for v in counts.values()) and counts == source_counts, 'backup_counts_mismatch')
            require(source.execute("SELECT 1 FROM agent_runs WHERE json_type(result_json,'$.state') IS NOT 'text' OR "
                                   "json_extract(result_json,'$.state') NOT IN ('awaiting_review','reviewed','needs_changes','failed','cancelled','interrupted') LIMIT 1").fetchone() is None, 'nonquiescent_agent_scope_not_supported')
            require(target.execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0] == 0, 'restored_sessions_not_empty')
            require(receipt['revoked_session_rows'] == source_counts['auth_sessions'], 'revocation_count_mismatch')
            require(type(receipt.get('flight_records')) is int and receipt['flight_records'] == source_counts['flights'], 'receipt_flight_count_mismatch')
            for table in COLUMNS:
                if table not in ('auth_sessions', 'security_audit'): compare_rows(source, target, table)
            left = source.execute('SELECT * FROM security_audit ORDER BY sequence')
            right = target.execute('SELECT * FROM security_audit ORDER BY sequence')
            while True:
                budget(); rows = left.fetchmany(256)
                if not rows: break
                require(right.fetchmany(len(rows)) == rows, 'historical_audit_mismatch')
            event = right.fetchone()
            require(event is not None and right.fetchone() is None, 'restore_event_count_invalid')
            require(event[1] == event_id and event[3:] == ('sign_out', 'success', None, None, None), 'restore_event_binding_invalid')
        for path, (before, fingerprint, limit) in tracked.items():
            require(facts(path, limit) == before and digest(path) == fingerprint and facts(path, limit) == before, 'file_changed')
        require_complete_restore(backup / 'ain.sqlite3'); require_complete_restore(restored / 'ain.sqlite3')
        report.update(consistency_verified=True, snapshot_id=snapshot_id, session_revocation_event_id=event_id,
                      manifest_sha256=manifest_hash, receipt_sha256=receipt_hash,
                      backup_database_sha256=hashes['ain.sqlite3'], restored_database_sha256=tracked[restored / 'ain.sqlite3'][1],
                      flight_records=source_counts['flights'], revoked_session_rows=receipt['revoked_session_rows'],
                      checks={'backup_bytes_match_manifest': True, 'snapshot_receipt_event_link': True,
                              'retained_rows_match': True, 'historical_events_match': True, 'one_restore_event_matches': True,
                              'restored_sessions_empty': True, 'artifact_bytes_match': True, 'observed_files_unchanged': True})
    except Refused as error:
        report['errors'] = [str(error)]
    except (OSError, ValueError, RuntimeError, sqlite3.Error, TypeError, KeyError, IndexError):
        report['errors'] = ['verification_budget_exceeded' if time.monotonic() >= deadline else 'evidence_unavailable_or_invalid']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True); parser.add_argument('--restored', required=True)
    parser.add_argument('--offline-copy', action='store_true', help='Acknowledge both inputs are stopped, checkpointed and will have no writers')
    args = parser.parse_args(); report = verify_evidence(args.backup, args.restored, offline_copy=args.offline_copy)
    print(json.dumps(report, indent=2)); return 0 if report['consistency_verified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
