"""Bounded read-only metadata inbox for explicitly shared pending reports."""
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
import time
import json
from agents.review_access import peer_pending


def inbox(database,user):
    if user['role'] not in ('researcher','admin'):raise PermissionError('Researcher access required')
    deadline=time.monotonic()+3
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=.25)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        rows=db.execute("SELECT id,json_extract(result_json,'$.actor') AS author,json_extract(result_json,'$.request.objective') AS objective,updated_at,result_json FROM agent_runs WHERE owner_id<>? AND json_type(result_json,'$.request.require_peer_review')='true' AND json_extract(result_json,'$.state')='awaiting_review' AND length(json_extract(result_json,'$.report_sha256'))=64 ORDER BY updated_at DESC,rowid DESC LIMIT 21",(user['id'],)).fetchall()
        if any(not peer_pending(json.loads(row['result_json'])) for row in rows):raise ValueError('Shared report integrity unavailable')
        if time.monotonic()>deadline:raise TimeoutError('Review inbox budget exceeded')
        results=[{'run_id':row['id'],'author':row['author'],'objective':row['objective'],'updated_at':row['updated_at']} for row in rows[:20]]
        if any(any(not isinstance(value,str) for value in row.values()) for row in results):raise ValueError('Invalid review metadata')
        return {'runs':results,'limit':20,'has_more':len(rows)>20,'checked_at':datetime.now(timezone.utc).isoformat(),
            'scope':'explicit_pending_second_account_reports','research_only':True,'operational_approval':False}
