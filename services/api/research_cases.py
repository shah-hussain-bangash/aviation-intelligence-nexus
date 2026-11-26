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
from services.api.case_agents import checked_agent, agent_summary
from services.api.case_gates import checked_gate, gate_summary


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


class AttachEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(strict=True, ge=1, le=99)
    evidence_run_id: UUID
    evidence_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


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
        with closing(self.connect(create=True)) as db, db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1,2,3,4): raise ValueError('Unsupported case schema')
            if version == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                raise ValueError('Existing unversioned store requires review')
            db.executescript('''
                BEGIN IMMEDIATE;
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
                CREATE TABLE IF NOT EXISTS case_evidence(
                    case_id TEXT NOT NULL REFERENCES cases(id), attached_version INTEGER NOT NULL,
                    evidence_run_id TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                    PRIMARY KEY(case_id,evidence_run_id),
                    FOREIGN KEY(case_id,attached_version) REFERENCES case_events(case_id,version));
                CREATE TABLE IF NOT EXISTS case_agents(
                    case_id TEXT NOT NULL REFERENCES cases(id), attached_version INTEGER NOT NULL,
                    agent_run_id TEXT NOT NULL, agent_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                    PRIMARY KEY(case_id,agent_run_id),
                    FOREIGN KEY(case_id,attached_version) REFERENCES case_events(case_id,version));
                CREATE TABLE IF NOT EXISTS case_gates(
                    case_id TEXT NOT NULL REFERENCES cases(id), attached_version INTEGER NOT NULL,
                    gate_run_id TEXT NOT NULL, gate_sha256 TEXT NOT NULL, snapshot_json TEXT NOT NULL,
                    PRIMARY KEY(case_id,gate_run_id),
                    FOREIGN KEY(case_id,attached_version) REFERENCES case_events(case_id,version));
                PRAGMA user_version=4;
                COMMIT;
            ''')

    def connect(self,create=False):
        mode='rwc' if create else 'rw'
        db = sqlite3.connect(self.case_database.as_uri()+'?mode='+mode,uri=True,timeout=5); db.row_factory = sqlite3.Row
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
        attachments=[]
        for item in db.execute('SELECT * FROM case_evidence WHERE case_id=? ORDER BY attached_version',(row['id'],)):
            snapshot=self.checked_evidence(item['snapshot_json'],item['evidence_run_id'])
            if digest(snapshot)!=item['evidence_sha256'] or not 1<item['attached_version']<=row['version']:
                raise ValueError('Evidence snapshot changed')
            event=events[item['attached_version']-1]
            if event['action']!='evidence' or event['note']!='Attached saved research evidence '+item['evidence_run_id']:
                raise ValueError('Evidence event binding changed')
            attachments.append({'run_id':item['evidence_run_id'],'sha256':item['evidence_sha256'],
                'attached_version':item['attached_version'],'question':snapshot['question'],'mode':snapshot['mode'],
                'evidence_count':len(snapshot['evidence'])})
        if len(attachments)>10 or {a['attached_version'] for a in attachments}!={e['version'] for e in events if e['action']=='evidence'}:
            raise ValueError('Evidence event inventory changed')
        agent_links=[]
        for item in db.execute('SELECT * FROM case_agents WHERE case_id=? ORDER BY attached_version',(row['id'],)):
            snapshot=checked_agent(item['snapshot_json'],item['agent_run_id'],row['owner_id'])
            context=snapshot['request'].get('case_context')
            if context and (context['case_id']!=row['id'] or context['source_sha256']!=row['source_sha256'] or context['case_version']>=item['attached_version']):
                raise ValueError('Captured agent case binding changed')
            version=item['attached_version']
            if digest(snapshot)!=item['agent_sha256'] or not 1<version<=row['version'] or events[version-1]['action']!='agent' or events[version-1]['note']!='Attached saved agent report '+item['agent_run_id']:
                raise ValueError('Agent snapshot or event changed')
            agent_links.append({'run_id':item['agent_run_id'],'sha256':item['agent_sha256'],'attached_version':version,**agent_summary(snapshot)})
        if len(agent_links)>5 or {a['attached_version'] for a in agent_links}!={e['version'] for e in events if e['action']=='agent'}:
            raise ValueError('Agent event inventory changed')
        gate_links=[]
        for item in db.execute('SELECT * FROM case_gates WHERE case_id=? ORDER BY attached_version',(row['id'],)):
            snapshot=checked_gate(item['snapshot_json'],item['gate_run_id']);version=item['attached_version']
            if digest(snapshot)!=item['gate_sha256'] or not 1<version<=row['version'] or events[version-1]['action']!='gate' or events[version-1]['note']!='Attached synthetic gate proposal '+item['gate_run_id']:
                raise ValueError('Gate snapshot or event changed')
            gate_links.append({'run_id':item['gate_run_id'],'sha256':item['gate_sha256'],'attached_version':version,**gate_summary(snapshot)})
        if len(gate_links)>5 or {a['attached_version'] for a in gate_links}!={e['version'] for e in events if e['action']=='gate'}:
            raise ValueError('Gate event inventory changed')
        return {**{k:row[k] for k in ('id','source_run_id','source_sha256','title','status','version','outcome','created_at','updated_at')},
            'source_snapshot': source, 'events': events, 'attachments':attachments,'agent_links':agent_links,'gate_links':gate_links,'scope': 'historical_us_research',
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

    @staticmethod
    def checked_evidence(raw, run_id):
        if len(raw.encode('utf-8'))>64_000: raise ValueError('Evidence exceeds bound')
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get('run_id')!=str(run_id) or result.get('research_only') is not True or result.get('operational_approval') is not False:
            raise ValueError('Research evidence identity required')
        if result.get('mode') not in ('generated','evidence_only','abstained') or not isinstance(result.get('question'),str) or not 1<=len(result['question'])<=600:
            raise ValueError('Research evidence summary required')
        if not isinstance(result.get('evidence'),list) or len(result['evidence'])>8 or not isinstance(result.get('claims'),list) or len(result['claims'])>3:
            raise ValueError('Bounded evidence records required')
        # Preserve the saved response, including abstentions and rejected generation.
        # This is an integrity/ownership check, not an answer-quality assessment.
        digest(result)
        return result

    def evidence_source(self, user, run_id):
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            row=db.execute('SELECT result_json FROM knowledge_runs WHERE id=? AND owner_id=?',(str(run_id),user['id'])).fetchone()
        if row is None: raise CaseMissing('Evidence unavailable')
        return self.checked_evidence(row[0],run_id)

    def evidence_sources(self,user):
        self.allow(user)
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            rows=db.execute('SELECT id FROM knowledge_runs WHERE owner_id=? ORDER BY created_at DESC,rowid DESC LIMIT 20',(user['id'],)).fetchall()
        result=[]
        for row in rows:
            snapshot=self.evidence_source(user,row[0])
            result.append({'run_id':row[0],'sha256':digest(snapshot),'question':snapshot['question'],'mode':snapshot['mode'],'evidence_count':len(snapshot['evidence'])})
        return result

    def attach_evidence(self,user,case_id,request):
        self.allow(user,write=True)
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None: raise CaseMissing('Case unavailable')
            current=self.projection(db,row)
            prior=next((a for a in current['attachments'] if a['run_id']==str(request.evidence_run_id)),None)
            if prior:
                if prior['sha256']!=request.evidence_sha256 or prior['attached_version']!=request.expected_version+1:
                    raise CaseConflict('Evidence already attached with different inputs')
                return {**current,'replayed':True}
            if row['status']!='open' or row['version']!=request.expected_version or row['version']>=100 or len(current['attachments'])>=10:
                raise CaseConflict('Case closed, changed or attachment limit reached')
            snapshot=self.evidence_source(user,request.evidence_run_id)
            if digest(snapshot)!=request.evidence_sha256: raise CaseConflict('Evidence version changed')
            version,timestamp=row['version']+1,now()
            db.execute('UPDATE cases SET version=?,updated_at=? WHERE id=?',(version,timestamp,str(case_id)))
            db.execute('INSERT INTO case_events VALUES(?,?,?,?,?)',(str(case_id),version,'evidence','Attached saved research evidence '+str(request.evidence_run_id),timestamp))
            db.execute('INSERT INTO case_evidence VALUES(?,?,?,?,?)',(str(case_id),version,str(request.evidence_run_id),request.evidence_sha256,encoded(snapshot)))
            return {**self.projection(db,db.execute('SELECT * FROM cases WHERE id=?',(str(case_id),)).fetchone()),'replayed':False}

    def attached_evidence(self,user,case_id,run_id):
        self.allow(user)
        with closing(self.connect()) as db:
            row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None: raise CaseMissing('Case unavailable')
            case=self.projection(db,row)
            item=next((a for a in case['attachments'] if a['run_id']==str(run_id)),None)
            if item is None: raise CaseMissing('Attachment unavailable')
            raw=db.execute('SELECT snapshot_json FROM case_evidence WHERE case_id=? AND evidence_run_id=?',(str(case_id),str(run_id))).fetchone()[0]
            return {'case_id':str(case_id),'case_version':case['version'],**item,'snapshot':self.checked_evidence(raw,run_id),
                'research_only':True,'operational_approval':False,'production_ready':False}

    def agent_source(self,user,run_id):
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            row=db.execute('SELECT result_json FROM agent_runs WHERE id=? AND owner_id=?',(str(run_id),user['id'])).fetchone()
        if row is None:raise CaseMissing('Owned agent report unavailable')
        return checked_agent(row[0],run_id,user['id'])

    def agent_sources(self,user):
        self.allow(user)
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            rows=db.execute("SELECT id FROM agent_runs WHERE owner_id=? AND json_extract(result_json,'$.state') IN ('reviewed','needs_changes') ORDER BY updated_at DESC,rowid DESC LIMIT 20",(user['id'],)).fetchall()
        result=[]
        for row in rows:
            snapshot=self.agent_source(user,row[0])
            result.append({'run_id':row[0],'sha256':digest(snapshot),**agent_summary(snapshot)})
        return result

    def attach_agent(self,user,case_id,request):
        self.allow(user,write=True)
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None:raise CaseMissing('Case unavailable')
            current=self.projection(db,row)
            prior=next((a for a in current['agent_links'] if a['run_id']==str(request.agent_run_id)),None)
            if prior:
                if prior['sha256']!=request.agent_sha256 or prior['attached_version']!=request.expected_version+1:raise CaseConflict('Agent attachment inputs changed')
                return {**current,'replayed':True}
            if row['status']!='open' or row['version']!=request.expected_version or row['version']>=100 or len(current['agent_links'])>=5:
                raise CaseConflict('Case closed, changed or report limit reached')
            snapshot=self.agent_source(user,request.agent_run_id)
            if digest(snapshot)!=request.agent_sha256:raise CaseConflict('Agent snapshot changed')
            context=snapshot['request'].get('case_context')
            if context and (context['case_id']!=str(case_id) or context['source_sha256']!=row['source_sha256'] or context['case_version']>row['version']):
                raise CaseConflict('Report belongs to a different case context')
            version,timestamp=row['version']+1,now()
            db.execute('UPDATE cases SET version=?,updated_at=? WHERE id=?',(version,timestamp,str(case_id)))
            db.execute('INSERT INTO case_events VALUES(?,?,?,?,?)',(str(case_id),version,'agent','Attached saved agent report '+str(request.agent_run_id),timestamp))
            db.execute('INSERT INTO case_agents VALUES(?,?,?,?,?)',(str(case_id),version,str(request.agent_run_id),request.agent_sha256,encoded(snapshot)))
            return {**self.projection(db,db.execute('SELECT * FROM cases WHERE id=?',(str(case_id),)).fetchone()),'replayed':False}

    def attached_agent(self,user,case_id,run_id):
        self.allow(user)
        with closing(self.connect()) as db:
            row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None:raise CaseMissing('Case unavailable')
            case=self.projection(db,row)
            item=next((a for a in case['agent_links'] if a['run_id']==str(run_id)),None)
            if item is None:raise CaseMissing('Agent attachment unavailable')
            raw=db.execute('SELECT snapshot_json FROM case_agents WHERE case_id=? AND agent_run_id=?',(str(case_id),str(run_id))).fetchone()[0]
            return {'case_id':str(case_id),'case_version':case['version'],**item,'snapshot':checked_agent(raw,run_id,user['id']),
                'research_only':True,'operational_approval':False,'production_ready':False}

    def gate_source(self,user,run_id):
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            row=db.execute('SELECT result_json,scenario_hash,created_at FROM gate_runs WHERE id=? AND owner_id=?',(str(run_id),user['id'])).fetchone()
        if row is None:raise CaseMissing('Owned gate proposal unavailable')
        snapshot=checked_gate(row[0],run_id)
        if snapshot['scenario_sha256']!=row[1] or snapshot['saved_at']!=row[2]:raise ValueError('Gate source metadata changed')
        return snapshot

    def gate_sources(self,user):
        self.allow(user)
        with closing(sqlite3.connect(self.source_database.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            rows=db.execute("SELECT id FROM gate_runs WHERE owner_id=? AND json_type(result_json,'$.review')='object' ORDER BY created_at DESC,rowid DESC LIMIT 20",(user['id'],)).fetchall()
        result=[]
        for row in rows:
            snapshot=self.gate_source(user,row[0]);result.append({'run_id':row[0],'sha256':digest(snapshot),**gate_summary(snapshot)})
        return result

    def attach_gate(self,user,case_id,request):
        self.allow(user,write=True)
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None:raise CaseMissing('Case unavailable')
            current=self.projection(db,row);prior=next((a for a in current['gate_links'] if a['run_id']==str(request.gate_run_id)),None)
            if prior:
                if prior['sha256']!=request.gate_sha256 or prior['attached_version']!=request.expected_version+1:raise CaseConflict('Gate attachment inputs changed')
                return {**current,'replayed':True}
            if row['status']!='open' or row['version']!=request.expected_version or row['version']>=100 or len(current['gate_links'])>=5:
                raise CaseConflict('Case closed, changed or proposal limit reached')
            snapshot=self.gate_source(user,request.gate_run_id)
            if digest(snapshot)!=request.gate_sha256:raise CaseConflict('Gate snapshot changed')
            version,timestamp=row['version']+1,now()
            db.execute('UPDATE cases SET version=?,updated_at=? WHERE id=?',(version,timestamp,str(case_id)))
            db.execute('INSERT INTO case_events VALUES(?,?,?,?,?)',(str(case_id),version,'gate','Attached synthetic gate proposal '+str(request.gate_run_id),timestamp))
            db.execute('INSERT INTO case_gates VALUES(?,?,?,?,?)',(str(case_id),version,str(request.gate_run_id),request.gate_sha256,encoded(snapshot)))
            return {**self.projection(db,db.execute('SELECT * FROM cases WHERE id=?',(str(case_id),)).fetchone()),'replayed':False}

    def attached_gate(self,user,case_id,run_id):
        self.allow(user)
        with closing(self.connect()) as db:
            row=db.execute('SELECT * FROM cases WHERE id=? AND owner_id=?',(str(case_id),user['id'])).fetchone()
            if row is None:raise CaseMissing('Case unavailable')
            case=self.projection(db,row);item=next((a for a in case['gate_links'] if a['run_id']==str(run_id)),None)
            if item is None:raise CaseMissing('Gate attachment unavailable')
            raw=db.execute('SELECT snapshot_json FROM case_gates WHERE case_id=? AND gate_run_id=?',(str(case_id),str(run_id))).fetchone()[0]
            return {'case_id':str(case_id),'case_version':case['version'],**item,'snapshot':checked_gate(raw,run_id),
                'research_only':True,'operational_approval':False,'production_ready':False}
