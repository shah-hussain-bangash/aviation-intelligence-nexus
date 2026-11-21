"""Current-account session controls; no session identifiers are exposed."""
from contextlib import closing
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import sqlite3
import time


class SessionInvalid(ValueError):
    pass


def observe(db,token_hash,current):
    row=db.execute('SELECT s.user_id,s.expires_at FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',(token_hash,current)).fetchone()
    if not row:raise SessionInvalid('Current session is no longer active')
    count=db.execute('SELECT count(*) FROM auth_sessions WHERE user_id=? AND expires_at>?',(row['user_id'],current)).fetchone()[0]
    return row,{'active_sessions':count,'other_active_sessions':count-1,
        'current_expires_at':datetime.fromtimestamp(row['expires_at'],timezone.utc).isoformat(),
        'checked_at':datetime.fromtimestamp(current,timezone.utc).isoformat(),
        'scope':'current_account_local_sessions','production_ready':False}


def account_sessions(database,token,revoke_others=False):
    if not isinstance(token,str) or not token or len(token)>128:raise SessionInvalid('Invalid current session')
    token_hash=hashlib.sha256(token.encode()).hexdigest();deadline=time.monotonic()+3
    uri=Path(database).resolve().as_uri()+('?mode=rw' if revoke_others else '?mode=ro')
    with closing(sqlite3.connect(uri,uri=True,timeout=.25)) as db,db:
        db.row_factory=sqlite3.Row;db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        if not revoke_others:db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN IMMEDIATE' if revoke_others else 'BEGIN')
        current=time.time();row,result=observe(db,token_hash,current)
        if revoke_others:
            removed=db.execute('DELETE FROM auth_sessions WHERE user_id=? AND token_hash<>? AND expires_at>?',(row['user_id'],token_hash,current)).rowcount
            result.update(active_sessions=1,other_active_sessions=0,revoked_other_sessions=removed,current_session_preserved=True)
        if time.monotonic()>=deadline:raise TimeoutError('Session query exceeded budget')
        return result
