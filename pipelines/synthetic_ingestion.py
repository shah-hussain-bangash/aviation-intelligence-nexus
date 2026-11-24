"""Serialized resumable research batch queue; generated synthetic inputs only."""
from contextlib import closing, contextmanager
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
import zipfile

from pipelines.import_bts import import_archive
from pipelines.verify_import_safety import fixture
from services.api.configuration import validate_environment

MAX_JOBS = 100
MAX_ATTEMPTS = 3
MAX_ROWS = 10_000


def host():
    config = validate_environment(os.environ)
    if config.container or any(os.environ.get(k) == '1' for k in ('AIN_AGENT_JOBS', 'AIN_MONITOR_ENABLED', 'AIN_OBSERVER_MOUNTED', 'AIN_INTAKE_OVERVIEW_MOUNTED')):
        raise ValueError('host_research_environment_required')


def local(path):
    path = Path(path).absolute()
    if str(path).startswith(('\\\\', '//')) or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)):
        raise ValueError('unredirected_local_case_required')
    return path


def create_case(directory):
    host(); directory = local(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory/'archives').mkdir()
    (directory/'case.json').write_text('{"format":"ain-synthetic-queue-v1","source_scope":"synthetic"}\n', encoding='utf-8')
    (directory/'worker.lock').write_bytes(b'0')
    with closing(sqlite3.connect(directory/'queue.sqlite3')) as db, db:
        db.execute("CREATE TABLE jobs(sequence INTEGER PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,period TEXT NOT NULL,archive_sha256 TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('queued','running','succeeded','quarantined','blocked')),attempts INTEGER NOT NULL DEFAULT 0,reason TEXT,result_json TEXT)")
    return directory


def case_path(directory):
    host(); directory = local(directory)
    marker = local(directory/'case.json')
    if not marker.is_file() or marker.stat().st_size > 1024:
        raise ValueError('synthetic_case_marker_required')
    if json.loads(marker.read_text(encoding='utf-8')) != {'format':'ain-synthetic-queue-v1','source_scope':'synthetic'}:
        raise ValueError('synthetic_case_marker_required')
    for name in ('queue.sqlite3', 'worker.lock', 'archives'):
        path = local(directory/name)
        if not path.exists():raise ValueError('synthetic_case_incomplete')
    for name in ('flights.sqlite3','queue.sqlite3'):
        local(directory/name)
        for suffix in ('-wal','-shm','-journal'):local(directory/(name+suffix))
    return directory


@contextmanager
def exclusive(directory):
    directory = case_path(directory)
    with (directory/'worker.lock').open('r+b') as lock:
        acquired = False
        try:
            if os.name == 'nt':
                import msvcrt
                try:msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:raise ValueError('synthetic_worker_busy') from None
            else:
                import fcntl
                try:fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:raise ValueError('synthetic_worker_busy') from None
            acquired = True
            yield directory
        finally:
            if acquired:
                if os.name == 'nt':
                    lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def enqueue(directory, rows, *, year, month):
    date(year, month, 1)
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError('bounded_synthetic_rows_required')
    with exclusive(directory) as directory, closing(sqlite3.connect(directory/'queue.sqlite3')) as db, db:
        if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= MAX_JOBS:
            raise ValueError('synthetic_job_limit')
        job_id = uuid4().hex
        archive = directory/'archives'/(job_id+'.zip')
        fixture(archive, rows)
        fingerprint = hashlib.sha256(archive.read_bytes()).hexdigest()
        db.execute('INSERT INTO jobs(job_id,period,archive_sha256,state) VALUES(?,?,?,?)',
                   (job_id, f'{year:04d}-{month:02d}', fingerprint, 'queued'))
        return job_id


def jobs(directory):
    directory = case_path(directory)
    with closing(sqlite3.connect((directory/'queue.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY sequence LIMIT 101')]


def work_one(directory):
    with exclusive(directory) as directory:
        with closing(sqlite3.connect(directory/'queue.sqlite3')) as db, db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            # Holding the OS lock proves no participating live worker owns this case.
            db.execute("UPDATE jobs SET state=CASE WHEN attempts>=? THEN 'quarantined' ELSE 'queued' END,reason=CASE WHEN attempts>=? THEN 'attempt_limit' ELSE 'interrupted_worker' END WHERE state='running'", (MAX_ATTEMPTS, MAX_ATTEMPTS))
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY sequence LIMIT 1").fetchone()
            if row is None:return None
            row = dict(row)
            if not re.fullmatch('[0-9a-f]{32}', row['job_id']) or not re.fullmatch('[0-9a-f]{64}', row['archive_sha256']):
                raise ValueError('synthetic_job_identity_invalid')
            if row['attempts'] >= MAX_ATTEMPTS:
                db.execute("UPDATE jobs SET state='quarantined',reason='attempt_limit' WHERE job_id=?", (row['job_id'],))
                return {'job_id':row['job_id'],'state':'quarantined','reason':'attempt_limit'}
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,reason=NULL WHERE job_id=?", (row['job_id'],))
        state, reason, result = 'succeeded', None, None
        try:
            archive = local(directory/'archives'/(row['job_id']+'.zip'))
            year, month = map(int, row['period'].split('-'))
            result = import_archive(archive, directory/'flights.sqlite3', year, month,
                                    synthetic=True, expected_sha256=row['archive_sha256'])
        except (ValueError, OSError, zipfile.BadZipFile):
            state, reason = 'quarantined', 'batch_or_artifact_rejected'
        except sqlite3.OperationalError as error:
            code = getattr(error,'sqlite_errorcode',None)
            if type(code) is int and (code & 0xff) in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):
                state = 'queued' if row['attempts']+1 < MAX_ATTEMPTS else 'quarantined'
                reason = 'database_busy' if state == 'queued' else 'attempt_limit'
            else:state, reason = 'blocked', 'database_unavailable'
        with closing(sqlite3.connect(directory/'queue.sqlite3')) as db, db:
            db.execute('UPDATE jobs SET state=?,reason=?,result_json=? WHERE job_id=? AND state=\'running\'',
                       (state, reason, json.dumps(result, sort_keys=True) if result else None, row['job_id']))
        return {'job_id':row['job_id'], 'state':state, 'reason':reason,
                'attempts':row['attempts']+1, 'import_status':result['status'] if result else None}
