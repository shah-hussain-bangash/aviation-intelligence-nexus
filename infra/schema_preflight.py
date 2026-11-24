"""Inspect an explicitly offline SQLite snapshot; never migrate or open live state."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import time

# Independent admission contract for the eight migrations in main.initialize.
# This module deliberately does not import the API or resolve its active state.
VERSION = 8
MAX_BYTES = 2 * 1024 ** 3
SECONDS = 30
COLUMNS = {
    'schema_migrations': 'version applied_at',
    'flights': 'id source source_record_id flight_date carrier origin destination departure_delay_minutes arrival_delay_minutes flight_number scheduled_departure cancelled diverted',
    'imports': 'sha256 source_url period rows_read rows_inserted duplicate_rows imported_at',
    'research_runs': 'id request_key input_sha256 scenario_json result_json model_version artifact_sha256 created_at owner_id',
    'auth_users': 'id username password_hash role active',
    'auth_sessions': 'token_hash user_id expires_at',
    'auth_limits': 'key failures window_start',
    'gate_runs': 'id owner_id request_key scenario_hash result_json created_at',
    'knowledge_runs': 'id owner_id result_json created_at',
    'agent_runs': 'id owner_id request_key input_hash result_json updated_at',
    'security_audit': 'sequence event_id occurred_at action outcome actor_id subject_id request_id',
}
INDEXES = {
    'research_runs': [('created_at',), ('owner_id', 'created_at')],
    'gate_runs': [('owner_id', 'created_at')],
    'knowledge_runs': [('owner_id', 'created_at')],
    'agent_runs': [('owner_id', 'updated_at')],
}
UNIQUE = {
    'flights': [('source', 'source_record_id')],
    'research_runs': [('request_key',)], 'auth_users': [('username',)],
    'gate_runs': [('owner_id', 'request_key')],
    'agent_runs': [('owner_id', 'request_key')],
    'security_audit': [('event_id',)],
}
PRIMARY = {'schema_migrations': 'version', 'flights': 'id', 'imports': 'sha256',
           'research_runs': 'id', 'auth_users': 'id', 'auth_sessions': 'token_hash',
           'auth_limits': 'key', 'gate_runs': 'id', 'knowledge_runs': 'id', 'agent_runs': 'id', 'security_audit': 'sequence'}


class Refused(Exception):
    pass


def inspect_snapshot(path, *, offline_snapshot=False):
    report = {'format': 'ain-offline-schema-check-v1', 'status': 'blocked',
              'local_schema_checks_passed': False, 'errors': [], 'expected_version': VERSION,
              'database_opened': False, 'migration_performed': False, 'production_ready': False}
    deadline = time.monotonic() + SECONDS

    def budget():
        if time.monotonic() >= deadline:
            raise Refused('inspection_budget_exceeded')

    def stable_file():
        budget()
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise Refused('ordinary_snapshot_required')
        if info.st_size <= 0 or info.st_size > MAX_BYTES:
            raise Refused('snapshot_size_not_allowed')
        sidecars = [Path(str(path) + suffix) for suffix in ('-wal', '-shm', '-journal')]
        if any(sidecar.exists() or sidecar.is_symlink() for sidecar in sidecars):
            raise Refused('sqlite_sidecar_present')
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def digest():
        result = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                budget()
                result.update(chunk)
        return result.hexdigest()

    try:
        if offline_snapshot is not True:
            raise Refused('offline_snapshot_acknowledgement_required')
        path = Path(path).absolute()
        # Reject remote paths and redirected parent directories too.
        if str(path).startswith(('\\\\', '//')) or any(
            part.is_symlink() or getattr(part, 'is_junction', lambda: False)()
            for part in (path, *path.parents)
        ):
            raise Refused('local_unredirected_snapshot_required')
        path = path.resolve()
        before = stable_file()
        fingerprint = digest()
        if stable_file() != before:
            raise Refused('snapshot_changed')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=0)) as connection:
            report['database_opened'] = True
            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            if connection.execute('PRAGMA integrity_check(1)').fetchone() != ('ok',):
                raise Refused('integrity_check_failed')
            tables = dict(connection.execute("SELECT name,type FROM sqlite_schema WHERE type IN ('table','view')"))
            if tables.get('schema_migrations') != 'table':
                raise Refused('migration_history_missing')
            versions = [r[0] for r in connection.execute('SELECT version FROM schema_migrations ORDER BY version LIMIT 9')]
            if not versions or any(type(v) is not int for v in versions):
                raise Refused('migration_history_invalid')
            if versions != list(range(1, len(versions) + 1)):
                raise Refused('migration_history_gap')
            report['recorded_version'] = versions[-1]
            if versions[-1] > VERSION:
                raise Refused('schema_newer_than_service')
            if versions[-1] < VERSION:
                report['status'] = 'migration_required'
                raise Refused('schema_upgrade_requires_separate_review')
            for table, names in COLUMNS.items():
                budget()
                if tables.get(table) != 'table':
                    raise Refused('required_table_missing')
                columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                if not set(names.split()).issubset({c[1] for c in columns}):
                    raise Refused('required_column_missing')
                if [c[1] for c in columns if c[5]] != [PRIMARY[table]]:
                    raise Refused('primary_key_mismatch')
                indexes = []; unique = []
                for index in connection.execute(f'PRAGMA index_list("{table}")').fetchall():
                    # Index names originate in a potentially untrusted snapshot.
                    escaped = index[1].replace('"', '""')
                    fields = tuple(r[2] for r in connection.execute(f'PRAGMA index_info("{escaped}")'))
                    if not index[4]:
                        indexes.append(fields)
                        if index[2]:
                            unique.append(fields)
                if any(fields not in indexes for fields in INDEXES.get(table, [])):
                    raise Refused('required_index_missing')
                if any(fields not in unique for fields in UNIQUE.get(table, [])):
                    raise Refused('required_uniqueness_missing')
        if stable_file() != before or digest() != fingerprint or stable_file() != before:
            raise Refused('snapshot_changed')
        report.update(status='checked', local_schema_checks_passed=True, snapshot_sha256=fingerprint,
                      snapshot_bytes=before[2], integrity_checked=True, migration_history_contiguous=True)
    except Refused as error:
        report['errors'] = [str(error)]
    except (OSError, ValueError, sqlite3.Error):
        report['errors'] = ['inspection_budget_exceeded' if time.monotonic() >= deadline else 'snapshot_unavailable_or_invalid']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', help='Standalone offline snapshot, never a live database')
    parser.add_argument('--offline-snapshot', action='store_true', help='Acknowledge the snapshot has no writers and is checkpointed')
    args = parser.parse_args()
    report = inspect_snapshot(args.snapshot, offline_snapshot=args.offline_snapshot)
    print(json.dumps(report, indent=2))
    return 0 if report['local_schema_checks_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
