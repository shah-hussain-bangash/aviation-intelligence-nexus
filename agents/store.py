"""Transactional checkpoints and owner-scoped, report-bound review."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4
from agents.quality import assess_report
from agents.cancellation import finish_cancelled
from agents.review_access import can_read,peer_pending,view as review_view


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
            compatible=[payload]
            if payload.get('document_scope') is None:
                compatible.append({key:value for key,value in payload.items() if key!='document_scope'})
            if not payload.get('required_tools'):
                compatible.extend([{key:value for key,value in candidate.items() if key!='required_tools'} for candidate in list(compatible)])
            if row['input_hash'] not in {sha(candidate) for candidate in compatible}: raise Conflict('Request key conflicts with its original investigation')
            result=json.loads(row['result_json'])
            if result['state']=='running': raise Conflict('Investigation is still running; refresh history')
            return {**result,**({'quality':assess_report(result)} if result.get('report_sha256') else {}),'replayed':True}

    def begin(self,user,key,payload):
        result={'run_id':str(uuid4()),'actor':user['username'],'request':payload,'state':'running','steps':[],
            'claims':[],'reviews':[],'created_at':now(),'updated_at':now(),'research_only':True,'operational_approval':False,
            'runtime':'bounded-ollama-tools-v2','replayed':False}
        with closing(self.connection()) as db,db:
            db.execute('INSERT INTO agent_runs(id,owner_id,request_key,input_hash,result_json,updated_at) VALUES(?,?,?,?,?,?)',
                (result['run_id'],user['id'],key,sha(payload),json.dumps(result),result['updated_at']))
        return result

    def stop_requested(self,run_id):
        with closing(self.connection()) as db:
            row=db.execute("SELECT json_extract(result_json,'$.cancel_requested_at'),json_type(result_json,'$.request.case_context'),owner_id,json_extract(result_json,'$.execution') FROM agent_runs WHERE id=?",(run_id,)).fetchone()
            if row and (row[1] is not None or row[3]=='local-background-queue-v1'):
                account=db.execute('SELECT role,active FROM auth_users WHERE id=?',(row[2],)).fetchone()
                if not account or not account['active'] or account['role'] not in ('admin','researcher'):return True
        if not row:raise KeyError('Investigation unavailable')
        return bool(row[0])

    def checkpoint(self,result):
        result['updated_at']=now()
        with closing(self.connection()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            saved=db.execute('SELECT result_json,owner_id FROM agent_runs WHERE id=?',(result['run_id'],)).fetchone()
            if saved:
                metadata=json.loads(saved['result_json'])
                if 'case_context' in metadata.get('request',{}) and result.get('request')!=metadata['request']:
                    raise Conflict('Captured case request cannot change between checkpoints')
                if 'submission_keys' in metadata:
                    result['submission_keys']=metadata['submission_keys']
                for key in ['cancel_requested_at','cancel_requested_by']:
                    if key in metadata:result[key]=metadata[key]
                if metadata.get('cancel_requested_at') and result['state'] in ('awaiting_review','failed','queued'):
                    finish_cancelled(result,now())
                # Recheck under this write lock: revocation may commit after the
                # runtime's last cooperative stop check, before its final save.
                protected='case_context' in metadata.get('request',{}) or metadata.get('execution')=='local-background-queue-v1'
                if protected and metadata.get('state')=='running' and result['state'] in ('awaiting_review','failed','queued'):
                    account=db.execute('SELECT role,active FROM auth_users WHERE id=?',(saved['owner_id'],)).fetchone()
                    if not account or not account['active'] or account['role'] not in ('admin','researcher'):
                        finish_cancelled(result,now())
            db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',
                (json.dumps(result),result['updated_at'],result['run_id']))

    def recent(self,user):
        with closing(self.connection()) as db:
            query='SELECT owner_id,result_json FROM agent_runs'; params=()
            query+=" WHERE (owner_id=? OR json_type(result_json,'$.request.case_context') IS NULL)" if user['role']=='admin' else ' WHERE owner_id=?'
            params=(user['id'],)
            rows=db.execute(query+' ORDER BY updated_at DESC,rowid DESC LIMIT 10',params).fetchall()
            results=[]
            for row in rows:
                result=json.loads(row['result_json'])
                results.append(review_view({**result,**({'quality':assess_report(result)} if result.get('report_sha256') else {})},user,row['owner_id']))
            return results

    def recover(self,restoring=False):
        with closing(self.connection()) as db,db:
            for row in db.execute('SELECT id,result_json FROM agent_runs').fetchall():
                result=json.loads(row['result_json'])
                if restoring and result['state']=='queued':
                    result.update(state='cancelled',updated_at=now(),error='Restored queued work is not automatically replayed. Start a new investigation after checking restored state.')
                    db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),result['updated_at'],row['id']))
                if result['state']=='running':
                    for step in result['steps']:
                        if step['state']=='running': step.update(state='interrupted',error='Service restarted during this tool.')
                    result.update(state='interrupted',updated_at=now(),error='Service restarted before completion; no tools are automatically replayed.')
                    db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),result['updated_at'],row['id']))

    def review(self,user,run_id,report_hash,decision,note,session_token=None):
        if user['role'] not in ('researcher','admin'):raise PermissionError('Researcher access required')
        with closing(self.connection()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT owner_id,result_json FROM agent_runs WHERE id=?',(run_id,)).fetchone()
            if not row:raise KeyError('Investigation unavailable')
            result=json.loads(row['result_json'])
            if not can_read(user,row['owner_id'],result):raise KeyError('Investigation unavailable')
            independent=result['request'].get('require_peer_review') is True
            if independent and row['owner_id']==user['id']:raise Conflict('A different researcher or administrator account must review this report')
            account=None;current_user=user
            if independent or session_token is not None:
                account=db.execute('SELECT username,role,active FROM auth_users WHERE id=?',(user['id'],)).fetchone()
                if not account or not account['active'] or account['role'] not in ('researcher','admin'):raise PermissionError('Current account cannot record this review')
                current_user={**user,'username':account['username'],'role':account['role']}
                if not can_read(current_user,row['owner_id'],result):raise PermissionError('Current account cannot review this report')
                if session_token is not None and not db.execute('SELECT 1 FROM auth_sessions WHERE user_id=? AND token_hash=? AND expires_at>?',(user['id'],hashlib.sha256(session_token.encode()).hexdigest(),datetime.now(timezone.utc).timestamp())).fetchone():raise PermissionError('Current session no longer permits review')
            actual_hash=sha({'request':result['request'],'steps':result['steps'],'claims':result['claims']})
            if result['state']!='awaiting_review' or result.get('report_sha256')!=report_hash or actual_hash!=report_hash: raise Conflict('Report is changed or already reviewed')
            quality=assess_report(result)
            if decision=='reviewed' and not quality['passed']: raise Conflict('Incomplete report cannot be accepted; request changes or start a revised investigation')
            result['quality']=quality
            receipt={'actor':account['username'] if account is not None else user['username'],'decision':decision,'note':note,'report_sha256':report_hash,'at':now()}
            if independent:receipt.update(second_account_review=True,reviewer_id=user['id'])
            result['reviews'].append(receipt)
            result.update(state='reviewed' if decision=='reviewed' else 'needs_changes',updated_at=now())
            db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),result['updated_at'],run_id))
            return review_view(result,current_user,row['owner_id'])

    def withdraw_sharing(self,user,request,session_token=None):
        with closing(self.connection()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT owner_id,result_json FROM agent_runs WHERE id=?',(str(request.run_id),)).fetchone()
            if not row or row['owner_id']!=user['id'] and user['role']!='admin':raise KeyError('Investigation unavailable')
            if 'case_context' in json.loads(row['result_json'])['request'] and row['owner_id']!=user['id']:raise KeyError('Investigation unavailable')
            result=json.loads(row['result_json'])
            account=db.execute('SELECT username,role,active FROM auth_users WHERE id=?',(user['id'],)).fetchone()
            if not account or not account['active'] or row['owner_id']!=user['id'] and account['role']!='admin':raise PermissionError('Current account cannot withdraw this sharing')
            if session_token is not None and not db.execute('SELECT 1 FROM auth_sessions WHERE user_id=? AND token_hash=? AND expires_at>?',(user['id'],hashlib.sha256(session_token.encode()).hexdigest(),datetime.now(timezone.utc).timestamp())).fetchone():raise PermissionError('Current session no longer permits withdrawal')
            actual_hash=sha({k:result[k] for k in ['request','steps','claims']})
            if result['request'].get('require_peer_review') is not True or result.get('report_sha256')!=request.report_sha256 or actual_hash!=request.report_sha256 or result['research_only'] is not True or result['operational_approval'] is not False:raise Conflict('Shared report integrity changed or withdrawal is unavailable')
            if result['state']=='withdrawn':
                prior=result.get('sharing_withdrawal',{})
                if all(prior.get(k)==v for k,v in {'withdrawal_key':str(request.withdrawal_key),'actor_id':user['id'],'note':request.note,'report_sha256':request.report_sha256}.items()):return review_view({**result,'withdrawal_replayed':True},user,row['owner_id'])
                raise Conflict('This report already has a different withdrawal record')
            if not peer_pending(result):raise Conflict('Only a pending shared report can be withdrawn; recorded decisions remain unchanged')
            at=now();result.update(state='withdrawn',updated_at=at,sharing_withdrawal={'withdrawal_key':str(request.withdrawal_key),'actor_id':user['id'],'actor':account['username'],'note':request.note,'report_sha256':request.report_sha256,'at':at,'acknowledged':True})
            db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),at,result['run_id']))
            return review_view({**result,'withdrawal_replayed':False},user,row['owner_id'])
