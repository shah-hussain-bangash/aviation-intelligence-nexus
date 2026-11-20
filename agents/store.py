"""Transactional checkpoints and owner-scoped, report-bound review."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class Conflict(ValueError):
    pass


class AgentStore:
    def __init__(self,database): self.database=database

    def connection(self):
        db=sqlite3.connect(self.database,timeout=5); db.row_factory=sqlite3.Row
        return db

    def lookup(self,user,key,payload):
        with closing(self.connection()) as db:
            row=db.execute('SELECT input_hash,result_json FROM agent_runs WHERE owner_id=? AND request_key=?',(user['id'],key)).fetchone()
        if row:
            if row['input_hash']!=sha(payload): raise Conflict('Request key conflicts with its original investigation')
            result=json.loads(row['result_json'])
            if result['state']=='running': raise Conflict('Investigation is still running; refresh history')
            return {**result,'replayed':True}

    def begin(self,user,key,payload):
        result={'run_id':str(uuid4()),'actor':user['username'],'request':payload,'state':'running','steps':[],
            'claims':[],'reviews':[],'created_at':now(),'updated_at':now(),'research_only':True,'operational_approval':False,
            'runtime':'bounded-ollama-tools-v1','replayed':False}
        with closing(self.connection()) as db,db:
            db.execute('INSERT INTO agent_runs(id,owner_id,request_key,input_hash,result_json,updated_at) VALUES(?,?,?,?,?,?)',
                (result['run_id'],user['id'],key,sha(payload),json.dumps(result),result['updated_at']))
        return result

    def checkpoint(self,result):
        result['updated_at']=now()
        with closing(self.connection()) as db,db:
            db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',
                (json.dumps(result),result['updated_at'],result['run_id']))

    def recent(self,user):
        with closing(self.connection()) as db:
            query='SELECT result_json FROM agent_runs'; params=()
            if user['role']!='admin': query+=' WHERE owner_id=?'; params=(user['id'],)
            return [json.loads(row[0]) for row in db.execute(query+' ORDER BY updated_at DESC,rowid DESC LIMIT 10',params)]

    def recover(self):
        with closing(self.connection()) as db,db:
            for row in db.execute('SELECT id,result_json FROM agent_runs').fetchall():
                result=json.loads(row['result_json'])
                if result['state']=='running':
                    for step in result['steps']:
                        if step['state']=='running': step.update(state='interrupted',error='Service restarted during this tool.')
                    result.update(state='interrupted',updated_at=now(),error='Service restarted before completion; no tools are automatically replayed.')
                    db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),result['updated_at'],row['id']))

    def review(self,user,run_id,report_hash,decision,note):
        with closing(self.connection()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT owner_id,result_json FROM agent_runs WHERE id=?',(run_id,)).fetchone()
            if not row or (row['owner_id']!=user['id'] and user['role']!='admin'): raise KeyError('Investigation unavailable')
            result=json.loads(row['result_json'])
            actual_hash=sha({'request':result['request'],'steps':result['steps'],'claims':result['claims']})
            if result['state']!='awaiting_review' or result.get('report_sha256')!=report_hash or actual_hash!=report_hash: raise Conflict('Report is changed or already reviewed')
            result['reviews'].append({'actor':user['username'],'decision':decision,'note':note,'report_sha256':report_hash,'at':now()})
            result.update(state='reviewed' if decision=='reviewed' else 'needs_changes',updated_at=now())
            db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),result['updated_at'],run_id))
            return result
