"""Owner-scoped local evidence query history; not protected auditing."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import time
from uuid import uuid4


class EvidenceHistory:
    def __init__(self, database):
        self.database = database

    def save(self, user, result, *, session_token=None):
        """HTTP callers supply their session token; omitted only for trusted local fixtures.

        Serialize authorization with the insert so revocation cannot commit between
        the access check and the history write. This cannot recall delivered answers.
        """
        saved = {**result, 'run_id': str(uuid4()), 'saved_at': datetime.now(timezone.utc).isoformat(), 'actor': user['username']}
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if session_token is not None:
                if not isinstance(session_token, str) or not 1 <= len(session_token) <= 128:
                    raise PermissionError('Knowledge query access changed')
                current = db.execute(
                    'SELECT u.id,u.username,u.role FROM auth_users u JOIN auth_sessions s ON u.id=s.user_id '
                    'WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',
                    (hashlib.sha256(session_token.encode()).hexdigest(), time.time())).fetchone()
                if not current or current[0] != user['id'] or current[2] not in ('admin', 'researcher'):
                    raise PermissionError('Knowledge query access changed')
                saved['actor'] = current[1]
            db.execute('INSERT INTO knowledge_runs(id,owner_id,result_json,created_at) VALUES(?,?,?,?)',
                (saved['run_id'], user['id'], json.dumps(saved), saved['saved_at']))
        return saved

    def recent(self, user):
        with closing(sqlite3.connect(self.database, timeout=5)) as db:
            query = 'SELECT result_json FROM knowledge_runs'
            params = ()
            if user['role'] != 'admin':
                query += ' WHERE owner_id=?'; params = (user['id'],)
            return [json.loads(row[0]) for row in db.execute(query + ' ORDER BY created_at DESC,rowid DESC LIMIT 10', params)]
