"""Owner-scoped persistence for synthetic optimizer proposals."""

from contextlib import closing
import hashlib
import json
import sqlite3
from uuid import uuid4
from optimization.reviews import GateReview,ReviewConflict,digest,seal,status,view,now


class GateRunStore:
    def __init__(self, database, clock=now):
        self.database = database
        self.clock = clock

    def connection(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def existing(self, db, owner, key, payload):
        row = db.execute("SELECT scenario_hash,result_json FROM gate_runs WHERE owner_id=? AND request_key=?", (owner,key)).fetchone()
        if row:
            if row["scenario_hash"] != hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest():
                raise ValueError("Request key conflicts with its saved scenario")
            return view({**json.loads(row["result_json"]), "replayed": True},self.clock())
        return None

    def lookup(self, user, key, payload):
        with closing(self.connection()) as db:
            return self.existing(db,user["id"],key,payload)

    def save(self, user, key, result):
        with closing(self.connection()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = self.existing(db,user["id"],key,result["scenario"])
            if prior:
                return prior
            saved = {**result, "run_id": str(uuid4()), "saved_at":self.clock().isoformat(),
                     "actor":user["username"],"replayed":False}
            saved=seal(saved)
            db.execute("INSERT INTO gate_runs(id,owner_id,request_key,scenario_hash,result_json,created_at) VALUES(?,?,?,?,?,?)",
                (saved["run_id"],user["id"],key,result["scenario_sha256"],json.dumps(saved),saved["saved_at"]))
            return view(saved,self.clock())

    def recent(self, user):
        with closing(self.connection()) as db:
            query = "SELECT result_json FROM gate_runs"
            params = ()
            if user["role"] != "admin":
                query += " WHERE owner_id=?"; params = (user["id"],)
            query += " ORDER BY created_at DESC,rowid DESC LIMIT 10"
            return [view(json.loads(row["result_json"]),self.clock()) for row in db.execute(query,params)]

    def review(self,user,request):
        request=GateReview.model_validate(request)
        if user['role'] not in ('admin','researcher'):raise PermissionError('Researcher access required')
        with closing(self.connection()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT owner_id,scenario_hash,created_at,result_json FROM gate_runs WHERE id=?',(str(request.run_id),)).fetchone()
            if not row or row['owner_id']!=user['id'] and user['role']!='admin':raise KeyError('Proposal unavailable')
            run=json.loads(row['result_json']);current=self.clock();checked=status(run,current)
            if checked['state'] in ('invalid','legacy') or run['scenario_sha256']!=row['scenario_hash'] or run['saved_at']!=row['created_at'] or run.get('run_id')!=str(request.run_id) or request.proposal_sha256!=run.get('proposal_sha256'):
                raise ReviewConflict('Proposal integrity changed or review is unavailable. Compute a new proposal.')
            receipt=run.get('review')
            if receipt:
                if all(receipt[k]==v for k,v in {'review_key':str(request.review_key),'reviewer':user['username'],'proposal_sha256':request.proposal_sha256,'decision':request.decision,'note':request.note}.items()):
                    return {**view(run,current),'review_replayed':True}
                raise ReviewConflict('This proposal already has a different research decision.')
            if not checked['eligible']:raise ReviewConflict('The research review window expired. Compute a new proposal.')
            receipt={'review_key':str(request.review_key),'reviewer':user['username'],'proposal_sha256':request.proposal_sha256,
                'decision':request.decision,'note':request.note,'reviewed_at':current.isoformat(),'acknowledged':True}
            receipt['decision_sha256']=digest(receipt);run['review']=receipt
            db.execute('UPDATE gate_runs SET result_json=? WHERE id=?',(json.dumps(run),str(request.run_id)))
            return {**view(run,current),'review_replayed':False}
