"""Bounded SQLite-backed investigation queue for one local API process."""
import asyncio
from contextlib import closing,ExitStack
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4
from agents.store import Conflict, now, sha
from agents.runtime import Investigation
from agents.quality import assess_report
from agents.review_access import can_read,view as review_view


class QueueFull(Conflict):
    pass


class JobQueue:
    def __init__(self, store, case_jobs=None):
        self.store = store
        self.case_jobs = case_jobs

    def enqueue(self, user, key, request, context=None, session_token=None):
        payload = request.model_dump()
        with ExitStack() as locks, closing(self.store.connection()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if session_token is not None:
                account=db.execute('SELECT username,role,active FROM auth_users WHERE id=?',(user['id'],)).fetchone()
                if not account or not account['active'] or account['role'] not in ('admin','researcher'):
                    raise PermissionError('Current account cannot submit this investigation')
                if not db.execute('SELECT 1 FROM auth_sessions WHERE user_id=? AND token_hash=? AND expires_at>?',
                        (user['id'],hashlib.sha256(session_token.encode()).hexdigest(),datetime.now(timezone.utc).timestamp())).fetchone():
                    raise PermissionError('Current session no longer permits submission')
                user={**user,'username':account['username'],'role':account['role']}
            prior = db.execute("SELECT input_hash,result_json FROM agent_runs WHERE owner_id=? AND (request_key=? OR EXISTS (SELECT 1 FROM json_each(agent_runs.result_json,'$.submission_keys') AS aliases WHERE aliases.value=?))", (user['id'], key, key)).fetchone()
            if context is not None:payload['case_context']=locks.enter_context(context(db,json.loads(prior['result_json']) if prior else None))
            fingerprint = sha(payload)
            if prior:
                if prior['input_hash'] != fingerprint:
                    raise Conflict('Request key belongs to different inputs')
                return {**json.loads(prior['result_json']), 'replayed': True}
            duplicate = db.execute("SELECT result_json FROM agent_runs WHERE owner_id=? AND input_hash=? AND json_extract(result_json,'$.state') IN ('queued','running') LIMIT 1", (user['id'], fingerprint)).fetchone()
            if duplicate:
                result = json.loads(duplicate['result_json'])
                aliases = result.setdefault('submission_keys', [])
                if len(aliases) >= 32:
                    raise Conflict('Active investigation retry-key limit reached; inspect saved history')
                aliases.append(key)
                db.execute('UPDATE agent_runs SET result_json=? WHERE id=?', (json.dumps(result), result['run_id']))
                return {**result, 'replayed': True}
            waiting = db.execute("SELECT owner_id FROM agent_runs WHERE json_extract(result_json,'$.state')='queued'").fetchall()
            if len(waiting) >= 5 or sum(row['owner_id'] == user['id'] for row in waiting) >= 2:
                raise QueueFull('Local waiting queue is full')
            result = {'run_id': str(uuid4()), 'actor': user['username'], 'request': payload, 'state': 'queued',
                'steps': [], 'claims': [], 'reviews': [], 'created_at': now(), 'updated_at': now(),
                'research_only': True, 'operational_approval': False, 'runtime': 'bounded-ollama-tools-v2',
                'execution': 'local-background-queue-v1', 'submission_keys': [], 'replayed': False}
            db.execute('INSERT INTO agent_runs(id,owner_id,request_key,input_hash,result_json,updated_at) VALUES(?,?,?,?,?,?)',
                (result['run_id'], user['id'], key, fingerprint, json.dumps(result), result['updated_at']))
            return result

    def get(self, user, run_id):
        with closing(self.store.connection()) as db:
            row = db.execute('SELECT owner_id,result_json FROM agent_runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                raise KeyError('Investigation unavailable')
            result = json.loads(row['result_json'])
            if not can_read(user,row['owner_id'],result):raise KeyError('Investigation unavailable')
            return review_view({**result, **({'quality': assess_report(result)} if result.get('report_sha256') else {})},user,row['owner_id'])

    def cancel(self, user, run_id, session_token=None):
        if user['role'] not in ('admin','researcher'):raise PermissionError('Researcher access required')
        with closing(self.store.connection()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT owner_id,result_json FROM agent_runs WHERE id=?', (run_id,)).fetchone()
            if not row or row['owner_id'] != user['id'] and user['role'] != 'admin':
                raise KeyError('Investigation unavailable')
            result = json.loads(row['result_json'])
            if 'case_context' in result['request'] and row['owner_id']!=user['id']:raise KeyError('Investigation unavailable')
            account = db.execute('SELECT username,role,active FROM auth_users WHERE id=?', (user['id'],)).fetchone()
            if not account or not account['active'] or account['role'] not in ('admin','researcher') or row['owner_id']!=user['id'] and account['role']!='admin':
                raise PermissionError('Current account cannot stop this investigation')
            if session_token is not None and not db.execute('SELECT 1 FROM auth_sessions WHERE user_id=? AND token_hash=? AND expires_at>?',
                    (user['id'],hashlib.sha256(session_token.encode()).hexdigest(),datetime.now(timezone.utc).timestamp())).fetchone():
                raise PermissionError('Current session no longer permits cancellation')
            if result['state'] == 'cancelled':
                return result
            if result['state']=='running':
                if result.get('cancel_requested_at'):return result
                result.update(cancel_requested_at=now(),cancel_requested_by=account['username'],updated_at=now())
            elif result['state']=='queued':
                result.update(state='cancelled',updated_at=now(),cancelled_at=now(),error='Cancelled before background execution.')
            else:
                raise Conflict('Only queued or running investigations can be stopped; completed reports are unchanged')
            db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?', (json.dumps(result), result['updated_at'], run_id))
            return result

    def claim(self):
        with ExitStack() as locks, closing(self.store.connection()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM agent_runs WHERE json_extract(result_json,'$.state')='running' LIMIT 1").fetchone():
                return None
            rows = db.execute("SELECT * FROM agent_runs WHERE json_extract(result_json,'$.state')='queued' ORDER BY rowid").fetchall()
            for row in rows:
                result = json.loads(row['result_json'])
                account = db.execute('SELECT id,username,role,active FROM auth_users WHERE id=?', (row['owner_id'],)).fetchone()
                if not account or not account['active'] or account['role'] not in ('admin', 'researcher'):
                    result.update(state='cancelled', updated_at=now(), error='Account no longer has permission to start this investigation.')
                    db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?', (json.dumps(result), result['updated_at'], row['id']))
                    continue
                if 'case_context' in result['request']:
                    try:
                        if self.case_jobs is None:raise ValueError('Case workspace is unavailable')
                        if result['request'].get('require_peer_review'):raise ValueError('Case sharing is unavailable')
                        locks.enter_context(self.case_jobs.claim_context(db,dict(account),result['request']['case_context']))
                    except (ValueError,KeyError,PermissionError):
                        result.update(state='cancelled',updated_at=now(),error='Captured case is unavailable, closed or changed; inspect the case before submitting a new investigation.')
                        db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?',(json.dumps(result),result['updated_at'],row['id']))
                        continue
                result.update(state='running', started_at=now(), updated_at=now())
                db.execute('UPDATE agent_runs SET result_json=?,updated_at=? WHERE id=?', (json.dumps(result), result['updated_at'], row['id']))
                return dict(account), row['request_key'], result


class JobWorker:
    def __init__(self, queue, investigator, enabled=False):
        self.queue, self.investigator, self.enabled = queue, investigator, enabled
        self.stopping = asyncio.Event()
        self.task = None
        self.last_poll = None
        self.last_error = None

    def tick(self):
        self.last_poll = now()
        item = self.queue.claim()
        if not item:
            return False
        user, key, result = item
        try:
            request = Investigation.model_validate({k:v for k,v in result['request'].items() if k!='case_context'})
            self.investigator.run(user, key, request, queued_result=result)
        except Conflict:
            # RUN_LOCK was occupied before any tool could start. Return this claim to the queue.
            result.update(state='queued')
            self.queue.store.checkpoint(result)
        except Exception:
            result.update(state='failed', error='Background execution stopped; inspect saved checkpoints before starting a new investigation.')
            self.queue.store.checkpoint(result)
        return True

    async def run(self):
        while not self.stopping.is_set():
            try:
                await asyncio.to_thread(self.tick)
                self.last_error = None
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, sqlite3.Error):
                self.last_error = 'Background queue could not be checked.'
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=1)
            except TimeoutError:
                pass

    def start(self):
        if self.enabled:
            self.task = asyncio.create_task(self.run())

    async def stop(self):
        self.stopping.set()
        if self.task:
            await self.task

    def status(self):
        return {'enabled': self.enabled, 'alive': bool(self.task and not self.task.done()),
                'last_poll': self.last_poll, 'error': self.last_error,
                'global_waiting_limit': 5, 'owner_waiting_limit': 2, 'running_limit': 1,
                'scope': 'One local API process; cooperative stops between bounded calls; no external worker failover or forced interruption'}
