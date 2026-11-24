"""Transactional local security events; not an independent or tamper-proof log."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import re
import time
from uuid import UUID, uuid4

EVENTS = {('account_created', 'success'), ('sign_in', 'success'), ('sign_in', 'denied'),
          ('sign_in', 'limited'), ('sign_out', 'success'), ('access_changed', 'success'),
          ('other_sessions_revoked', 'success')}

AUDIT_TABLE_SQL = """CREATE TABLE security_audit (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE, occurred_at TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('account_created','sign_in','sign_out','access_changed','other_sessions_revoked')),
    outcome TEXT NOT NULL CHECK(outcome IN ('success','denied','limited')),
    actor_id TEXT, subject_id TEXT, request_id TEXT
)"""
AUDIT_TRIGGER_SQL = {
    'security_audit_no_update': "CREATE TRIGGER security_audit_no_update BEFORE UPDATE ON security_audit BEGIN SELECT RAISE(ABORT,'security_audit_append_only'); END",
    'security_audit_no_delete': "CREATE TRIGGER security_audit_no_delete BEFORE DELETE ON security_audit BEGIN SELECT RAISE(ABORT,'security_audit_append_only'); END",
}


class AuditContractError(sqlite3.DatabaseError):
    pass


def normalized_sql(value):
    # Only tolerate whitespace differences in the application-owned migration DDL.
    return re.sub(r'\s+', ' ', value).strip() if isinstance(value, str) else None


def require_audit_contract(db):
    """Read-only structural/configuration check, not log-content authentication."""
    expected = {'security_audit': ('table', AUDIT_TABLE_SQL),
                **{name: ('trigger', sql) for name, sql in AUDIT_TRIGGER_SQL.items()}}
    try:
        rows = db.execute("SELECT name,type,tbl_name,sql FROM sqlite_schema WHERE name IN (?,?,?) "
                          "OR (tbl_name='security_audit' AND type='trigger')", tuple(expected)).fetchall()
        if len(rows) != len(expected):
            raise AuditContractError('audit_schema_contract_invalid')
        for name, kind, table, sql in rows:
            if name not in expected or table != 'security_audit' or kind != expected[name][0] or normalized_sql(sql) != normalized_sql(expected[name][1]):
                raise AuditContractError('audit_schema_contract_invalid')
        if (db.execute('PRAGMA ignore_check_constraints').fetchone()[0] != 0
                or db.execute('PRAGMA writable_schema').fetchone()[0] != 0
                or not db.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER)):
            raise AuditContractError('audit_connection_safeguards_disabled')
    except AuditContractError:
        raise
    except (sqlite3.Error, AttributeError):
        raise AuditContractError('audit_contract_unavailable') from None


def identifier(value):
    try:
        parsed = UUID(value)
        return str(parsed) if parsed.version == 4 and str(parsed) == value else None
    except (ValueError, TypeError, AttributeError):
        return None


def append_event(db, action, outcome, *, actor_id=None, subject_id=None, request_id=None):
    if (action, outcome) not in EVENTS:
        raise ValueError('unsupported_security_event')
    if not db.in_transaction:
        raise RuntimeError('security_event_requires_transaction')
    require_audit_contract(db)
    db.execute('INSERT INTO security_audit(event_id,occurred_at,action,outcome,actor_id,subject_id,request_id) VALUES(?,?,?,?,?,?,?)',
               (str(uuid4()), datetime.now(timezone.utc).isoformat(), action, outcome,
                identifier(actor_id), identifier(subject_id), identifier(request_id)))


def latest_events(database):
    deadline = time.monotonic() + 3
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=.25)) as db:
        db.row_factory = sqlite3.Row
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        db.execute('PRAGMA query_only=ON')
        require_audit_contract(db)
        rows = db.execute('SELECT sequence,event_id,occurred_at,action,outcome,actor_id,subject_id,request_id FROM security_audit ORDER BY sequence DESC LIMIT 101').fetchall()
    return {'scope': 'local_security_events', 'events': [dict(row) for row in rows[:100]],
            'has_older_events': len(rows) > 100, 'limit': 100, 'protected_external_storage': False,
            'production_ready': False}
