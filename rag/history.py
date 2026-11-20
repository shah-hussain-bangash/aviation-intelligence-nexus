"""Owner-scoped local evidence query history; not protected auditing."""
from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4


class EvidenceHistory:
    def __init__(self, database):
        self.database = database

    def save(self, user, result):
        saved = {**result, 'run_id': str(uuid4()), 'saved_at': datetime.now(timezone.utc).isoformat(), 'actor': user['username']}
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
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
