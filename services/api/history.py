"""Append-only API history; local filesystem owners can still modify the database."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


class IdempotencyConflict(ValueError):
    pass


class ResearchHistory:
    def __init__(self, database: Path):
        self.database = database

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def input_hash(payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def existing(self, connection, key, digest):
        row = connection.execute("SELECT input_sha256, result_json FROM research_runs WHERE request_key = ?", (key,)).fetchone()
        if row:
            if row["input_sha256"] != digest:
                raise IdempotencyConflict("Request key already belongs to different inputs")
            return {**json.loads(row["result_json"]), "replayed": True}
        return None

    def lookup(self, key, payload):
        with closing(self.connect()) as connection:
            return self.existing(connection, key, self.input_hash(payload))

    def save(self, key, payload, result):
        digest = self.input_hash(payload)
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self.existing(connection, key, digest)
            if existing:
                return existing
            identifier = str(uuid4())
            saved_at = datetime.now(timezone.utc).isoformat()
            stored = {**result, "run_id": identifier, "saved_at": saved_at,
                      "actor": "anonymous_local", "replayed": False}
            connection.execute("INSERT INTO research_runs (id, request_key, input_sha256, scenario_json, "
                "result_json, model_version, artifact_sha256, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (identifier, key, digest, json.dumps(payload), json.dumps(stored),
                 result["model_version"], result["artifact_sha256"], saved_at))
            return stored

    def recent(self):
        with closing(self.connect()) as connection:
            return [json.loads(row["result_json"]) for row in connection.execute(
                "SELECT result_json FROM research_runs ORDER BY created_at DESC, rowid DESC LIMIT 10")]
