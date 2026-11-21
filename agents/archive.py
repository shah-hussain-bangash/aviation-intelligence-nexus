"""Read-only, owner-scoped keyset pages of investigation metadata."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

STATES=('queued','running','awaiting_review','reviewed','needs_changes','failed','interrupted','cancelled','withdrawn')


class ArchiveQuery(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    q: str=Field(default='',max_length=120)
    state: Literal['all','queued','running','awaiting_review','reviewed','needs_changes','failed','interrupted','cancelled','withdrawn']='all'
    before: str | None=Field(default=None,pattern=r'^(0|[1-9][0-9]{0,18})$')
    through: str | None=Field(default=None,pattern=r'^(0|[1-9][0-9]{0,18})$')

    @model_validator(mode='after')
    def cursor_scope(self):
        if any(value is not None and int(value)>2**63-1 for value in (self.before,self.through)):
            raise ValueError('Cursor outside SQLite range')
        if self.before is not None and (self.through is None or int(self.before)>int(self.through)):
            raise ValueError('Previous boundary needs its insertion ceiling')
        return self


def page(database,user,query):
    if user['role'] not in ('admin','researcher','viewer'):raise ValueError('Unsupported role')
    deadline=time.monotonic()+3
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=.25)) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
        owner='' if user['role']=='admin' else ' AND owner_id=?'
        args=[] if not owner else [user['id']]
        ceiling=int(query.through) if query.through is not None else db.execute('SELECT coalesce(max(rowid),0) FROM agent_runs WHERE 1=1'+owner,args).fetchone()[0]
        where='rowid<=?'+owner;values=[ceiling,*args]
        if query.before is not None:where+=' AND rowid<?';values.append(int(query.before))
        if query.state!='all':where+=" AND json_extract(result_json,'$.state')=?";values.append(query.state)
        if query.q:
            where+=" AND instr(lower(json_extract(result_json,'$.request.objective')),lower(?))>0";values.append(query.q)
        rows=db.execute("SELECT rowid AS position,id,json_extract(result_json,'$.actor') AS actor,json_extract(result_json,'$.request.objective') AS objective,json_extract(result_json,'$.state') AS state,json_extract(result_json,'$.created_at') AS created_at,updated_at FROM agent_runs WHERE "+where+' ORDER BY rowid DESC LIMIT 11',values).fetchall()
        results=[{key:row[key] for key in ['actor','objective','state','created_at','updated_at']}|{'run_id':row['id']} for row in rows[:10]]
        if any(row['state'] not in STATES or any(not isinstance(row[key],str) for key in row) for row in results):
            raise ValueError('Invalid archived metadata')
        if time.monotonic()>=deadline:raise TimeoutError('Archive query exceeded budget')
        return {'runs':results,'through':str(ceiling),'next_before':str(rows[9]['position']) if len(rows)>10 else None,
            'page_size':10,'order':'newest_created_first','search_scope':'objective_literal_ascii_case_insensitive',
            'research_only':True,'operational_approval':False}
