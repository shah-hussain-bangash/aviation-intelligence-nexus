"""Read-only migration-history admission on the caller's SQLite connection."""
import sqlite3


class MigrationHistoryError(RuntimeError):
    """Fixed diagnostic code; never includes database paths or row values."""


def history_version(connection, expected, *, allow_empty=False):
    try:
        entry = connection.execute(
            "SELECT type FROM sqlite_schema WHERE name='schema_migrations'"
        ).fetchone()
        if entry is None:
            versions = []
        else:
            if entry[0] != 'table':
                raise MigrationHistoryError('migration_history_invalid')
            columns = connection.execute('PRAGMA table_info(schema_migrations)').fetchall()
            if ([c[1] for c in columns if c[5]] != ['version']
                or not any(c[1] == 'version' and c[2].upper() == 'INTEGER' for c in columns)
                or 'applied_at' not in {c[1] for c in columns}):
                raise MigrationHistoryError('migration_history_invalid')
            versions = [row[0] for row in connection.execute(
                'SELECT version FROM schema_migrations ORDER BY version LIMIT ?', (expected + 2,)
            )]
        if not versions:
            # Only a genuinely empty database can bootstrap. Never adopt unversioned state.
            other = connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' "
                "AND name!='schema_migrations' LIMIT 1"
            ).fetchone()
            if allow_empty and other is None:
                return 0
            raise MigrationHistoryError('migration_history_missing')
        if any(type(version) is not int or version < 1 for version in versions):
            raise MigrationHistoryError('migration_history_invalid')
        if versions[-1] > expected:
            raise MigrationHistoryError('migration_history_newer_than_service')
        if versions != list(range(1, versions[-1] + 1)):
            raise MigrationHistoryError('migration_history_gap')
        return versions[-1]
    except sqlite3.Error:
        raise MigrationHistoryError('migration_history_unavailable') from None


def require_current(connection, expected):
    if history_version(connection, expected) != expected:
        raise MigrationHistoryError('migration_history_upgrade_required')
