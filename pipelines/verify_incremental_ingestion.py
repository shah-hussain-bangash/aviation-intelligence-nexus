"""Crash/restart/replay demonstration in a new generated synthetic ingestion case."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

from pipelines.synthetic_ingestion import create_case, enqueue, jobs, work_one
from pipelines.verify_import_safety import BASE, identity
from services.api.paths import ROOT

SOURCES = ('pipelines/synthetic_ingestion.py','pipelines/verify_incremental_ingestion.py')
CRASH_WORKER = '''import os,sys
from pathlib import Path
from unittest.mock import patch
import pipelines.synthetic_ingestion as worker
original=worker.import_archive
def interrupted(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(73)
with patch.object(worker,'import_archive',interrupted):
    worker.work_one(Path(sys.argv[1]))
'''


def state(directory):
    with closing(sqlite3.connect(directory/'flights.sqlite3')) as db:
        return {'flights':db.execute('SELECT COUNT(*) FROM flights').fetchone()[0],
                'imports':db.execute('SELECT COUNT(*) FROM imports').fetchone()[0],
                'observed_bts':db.execute("SELECT COUNT(*) FROM flights WHERE source='BTS_REPORTING_CARRIER'").fetchone()[0]}


def verify(directory):
    context = identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory = create_case(directory)
    report = {'format':'ain-incremental-ingestion-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
              'case_id':directory.name, **context,'passed':False,'checks':{},'synthetic_only':True,
              'primary_database_accessed':False,'external_data_imported':False,'training_performed':False,
              'deployment_performed':False,'production_ready':False}
    stage = 'enqueue'
    try:
        first = enqueue(directory, BASE, year=2025, month=1)
        february = [*BASE[0]]; february[0] = '2025-02-01'
        second = enqueue(directory, [february], year=2025, month=2)
        new = [*BASE[0]]; new[2] = '9'
        conflict = [*BASE[0]]; conflict[7] = '99'
        third = enqueue(directory, [new, conflict], year=2025, month=1)
        stage = 'abrupt_worker_exit'
        crashed = subprocess.run([sys.executable,'-c',CRASH_WORKER,str(directory)],cwd=ROOT,capture_output=True,timeout=60)
        before = state(directory)
        interrupted = jobs(directory)
        stage = 'resume'
        resumed = work_one(directory)
        after_replay = state(directory)
        following = work_one(directory)
        rejected = work_one(directory)
        idle = work_one(directory)
        final = state(directory)
        recorded = jobs(directory)
        receipt = json.loads(recorded[0]['result_json'])
        archives = {row['job_id']:row['archive_sha256'] for row in recorded}
        report['checks'] = {
            'real_process_exited_after_data_commit': crashed.returncode == 73 and before == {'flights':3,'imports':1,'observed_bts':0},
            'interrupted_job_persisted': interrupted[0]['state'] == 'running' and interrupted[0]['attempts'] == 1,
            'restart_reclaimed_released_lock': resumed['job_id'] == first and resumed['state'] == 'succeeded' and resumed['attempts'] == 2,
            'committed_batch_replayed_once': resumed['import_status'] == 'already_imported' and after_replay == before,
            'next_month_imported': following['job_id'] == second and following['import_status'] == 'imported',
            'conflicting_batch_quarantined': rejected['job_id'] == third and rejected['state'] == 'quarantined',
            'partial_conflicting_rows_rolled_back': final == {'flights':4,'imports':2,'observed_bts':0},
            'queue_drained': idle is None and [row['state'] for row in recorded] == ['succeeded','succeeded','quarantined'],
            'receipt_bound_to_expected_archive': receipt['sha256'] == archives[first] and receipt['source_url'] == 'urn:ain:synthetic-bts-schema:2025-01',
            'retained_archives_match': all(hashlib.sha256((directory/'archives'/(key+'.zip')).read_bytes()).hexdigest() == digest for key,digest in archives.items()),
            'source_unchanged': all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() == digest for p,digest in context['source_sha256'].items())}
        report.update(crash_exit_code=crashed.returncode, counts=final, jobs=recorded)
        report['passed'] = all(report['checks'].values())
    except Exception:
        report.update(error='synthetic_incremental_check_failed',failed_stage=stage)
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = verify(ROOT/'.local/incremental-ingestion'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
