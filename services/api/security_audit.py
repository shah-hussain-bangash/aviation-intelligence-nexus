"""Transactional local security events; not an independent or tamper-proof log."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4

EVENTS = {('account_created', 'success'), ('sign_in', 'success'), ('sign_in', 'denied'),
          ('sign_in', 'limited'), ('sign_out', 'success'), ('access_changed', 'success'),
          ('other_sessions_revoked', 'success')}


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
    db.execute('INSERT INTO security_audit(event_id,occurred_at,action,outcome,actor_id,subject_id,request_id) VALUES(?,?,?,?,?,?,?)',
               (str(uuid4()), datetime.now(timezone.utc).isoformat(), action, outcome,
                identifier(actor_id), identifier(subject_id), identifier(request_id)))


def latest_events(database):
    deadline = time.monotonic() + 3
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=.25)) as db:
        db.row_factory = sqlite3.Row
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        db.execute('PRAGMA query_only=ON')
        rows = db.execute('SELECT sequence,event_id,occurred_at,action,outcome,actor_id,subject_id,request_id FROM security_audit ORDER BY sequence DESC LIMIT 101').fetchall()
    return {'scope': 'local_security_events', 'events': [dict(row) for row in rows[:100]],
            'has_older_events': len(rows) > 100, 'limit': 100, 'protected_external_storage': False,
            'production_ready': False}
