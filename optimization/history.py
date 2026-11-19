"""Owner-scoped persistence for synthetic optimizer proposals."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from uuid import uuid4


class GateRunStore:
    def __init__(self, database):
        self.database = database

    def connection(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def existing(self, db, owner, key, payload):
        row = db.execute("SELECT scenario_hash,result_json FROM gate_runs WHERE owner_id=? AND request_key=?", (owner,key)).fetchone()
        if row:
            if row["scenario_hash"] != hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest():
                raise ValueError("Request key conflicts with its saved scenario")
            return {**json.loads(row["result_json"]), "replayed": True}
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
            saved = {**result, "run_id": str(uuid4()), "saved_at":datetime.now(timezone.utc).isoformat(),
                     "actor":user["username"],"replayed":False}
            db.execute("INSERT INTO gate_runs(id,owner_id,request_key,scenario_hash,result_json,created_at) VALUES(?,?,?,?,?,?)",
                (saved["run_id"],user["id"],key,result["scenario_sha256"],json.dumps(saved),saved["saved_at"]))
            return saved

    def recent(self, user):
        with closing(self.connection()) as db:
            query = "SELECT result_json FROM gate_runs"
            params = ()
            if user["role"] != "admin":
                query += " WHERE owner_id=?"; params = (user["id"],)
            query += " ORDER BY created_at DESC,rowid DESC LIMIT 10"
            return [json.loads(row["result_json"]) for row in db.execute(query,params)]
