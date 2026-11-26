"""Opt-in local research cases linked to immutable snapshots of owner-saved predictions."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field


class CaseConflict(ValueError): pass
class CaseMissing(ValueError): pass


class OpenCase(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_run_id: UUID
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    title: str = Field(min_length=1, max_length=160)


class ChangeCase(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_version: int = Field(strict=True, ge=1, le=100)
    action: Literal['note', 'close']
    note: str = Field(min_length=1, max_length=2000)


def encoded(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(value): return hashlib.sha256(encoded(value).encode()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()


class ResearchCaseService:
    def __init__(self, source_database, case_database):
        self.source_database = Path(source_database).absolute()
        self.case_database = Path(case_database).absolute()
        if self.case_database.resolve() == self.source_database.resolve() or (self.case_database.exists() and self.source_database.exists()
                and self.case_database.samefile(self.source_database)): raise ValueError('Separate case store required')
        if any(p.is_symlink() or getattr(p, 'is_junction', lambda:False)() for p in (self.case_database, *self.case_database.parents)):
            raise ValueError('Unredirected case store required')
        self.case_database.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1): raise ValueError('Unsupported case schema')
            if version == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                raise ValueError('Existing unversioned store requires review')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cases(
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, source_run_id TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL, source_json TEXT NOT NULL, title TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open','closed')), version INTEGER NOT NULL,
                    outcome TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    request_key TEXT NOT NULL, input_sha256 TEXT NOT NULL, UNIQUE(owner_id,request_key));
                CREATE TABLE IF NOT EXISTS case_events(
                    case_id TEXT NOT NULL REFERENCES cases(id), version INTEGER NOT NULL,
                    action TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(case_id,version));
                CREATE INDEX IF NOT EXISTS cases_owner ON cases(owner_id,updated_at);
                PRAGMA user_version=1;
            ''')

    def connect(self):
        db = sqlite3.connect(self.case_database, timeout=5); db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def allow(user, write=False):
        if not user or user.get('role') not in ('admin','researcher','viewer') or (write and user['role']=='viewer'):
            raise PermissionError('Researcher role required')

    def source(self, user, run_id):
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
            row = db.execute("SELECT result_json FROM research_runs WHERE id=? AND owner_id=? AND model_version='delay-v2'", (str(run_id), user['id'])).fetchone()
        if row is None: raise CaseMissing('Source unavailable')
        if len(row[0]) > 100_000: raise ValueError('Source exceeds bound')
        result = json.loads(row[0])
        if not isinstance(result,dict) or result.get('research_only') is not True or result.get('operational_serving_approved') is not False or result.get('model_version') != 'delay-v2':
            raise ValueError('Research-only delay-v2 source required')
        if result.get('run_id') != str(run_id): raise ValueError('Source identity mismatch')
        return result

    def sources(self, user):
        self.allow(user)
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
            rows = db.execute("SELECT id FROM research_runs WHERE owner_id=? AND model_version='delay-v2' ORDER BY created_at DESC,rowid DESC LIMIT 20", (user['id'],)).fetchall()
        return [{'run_id': row[0], 'source_sha256': digest(self.source(user,row[0]))} for row in rows]

    def projection(self, db, row):
        source = json.loads(row['source_json'])
        if digest(source) != row['source_sha256']: raise ValueError('Stored source snapshot changed')
        events = [dict(e) for e in db.execute('SELECT version,action,note,created_at FROM case_events WHERE case_id=? ORDER BY version', (row['id'],))]
        if [e['version'] for e in events] != list(range(1,row['version']+1)): raise ValueError('Case event history incomplete')
        return {**{k:row[k] for k in ('id','source_run_id','source_sha256','title','status','version','outcome','created_at','updated_at')},
            'source_snapshot': source, 'events': events, 'scope': 'historical_us_research',
            'operational_approval': False, 'production_ready': False}

    def get(self, user, case_id):
        self.allow(user)
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?', (str(case_id),user['id'])).fetchone()
            if row is None: raise CaseMissing('Case unavailable')
            return self.projection(db,row)

    def recent(self, user):
        self.allow(user)
        with closing(self.connect()) as db:
            return [self.projection(db,row) for row in db.execute('SELECT * FROM cases WHERE owner_id=? ORDER BY updated_at DESC,id DESC LIMIT 20', (user['id'],)).fetchall()]

    def open(self, user, request, request_key):
        self.allow(user,write=True)
        request_key = str(UUID(str(request_key)))
        payload = request.model_dump(mode='json'); input_hash = digest(payload)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM cases WHERE owner_id=? AND request_key=?', (user['id'],request_key)).fetchone()
            if row:
                if row['input_sha256'] != input_hash: raise CaseConflict('Request key has different inputs')
                return {**self.projection(db,row), 'replayed':True}
            source = self.source(user,request.source_run_id)
            if digest(source) != request.source_sha256: raise CaseConflict('Source version changed')
            case_id, timestamp = str(uuid4()), now()
            db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?,1,NULL,?,?,?,?)',
                (case_id,user['id'],str(request.source_run_id),request.source_sha256,encoded(source),request.title,'open',timestamp,timestamp,request_key,input_hash))
            db.execute('INSERT INTO case_events VALUES(?,1,?,?,?)', (case_id,'opened','Research case created from saved prediction',timestamp))
            row = db.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
            return {**self.projection(db,row), 'replayed':False}

    def change(self, user, case_id, request):
        self.allow(user,write=True)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?', (str(case_id),user['id'])).fetchone()
            if row is None: raise CaseMissing('Case unavailable')
            self.projection(db,row)
            if row['status'] != 'open' or row['version'] != request.expected_version or row['version']>=100:
                raise CaseConflict('Case closed or version changed')
            version, timestamp = row['version']+1, now()
            db.execute('UPDATE cases SET version=?,status=?,outcome=?,updated_at=? WHERE id=?',
                (version,'closed' if request.action=='close' else 'open',request.note if request.action=='close' else None,timestamp,str(case_id)))
            db.execute('INSERT INTO case_events VALUES(?,?,?,?,?)', (str(case_id),version,request.action,request.note,timestamp))
            return self.projection(db,db.execute('SELECT * FROM cases WHERE id=?',(str(case_id),)).fetchone())
