"""Offline synthetic batch/archive/ledger/row consistency, never live readiness or source authentication."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time

from pipelines.synthetic_ingestion import case_path, local
from pipelines.import_bts import import_archive
from services.api.migrations import require_current

MAX_BYTES = 2*1024**3
SECONDS = 120
FLIGHT_COLUMNS = 'source,source_record_id,flight_date,carrier,origin,destination,departure_delay_minutes,arrival_delay_minutes,flight_number,scheduled_departure,cancelled,diverted'


def require(condition, code):
    if not condition:raise ValueError(code)


def reconcile(directory, *, offline_copy=False):
    report={'format':'ain-synthetic-case-reconciliation-v1','consistent':False,'errors':[],
            'source_case_modified':False,'source_authenticated':False,'current_health_verified':False,
            'scratch_reconstruction':False,'synthetic_only':True,'production_ready':False}
    deadline=time.monotonic()+SECONDS
    tracked={};total=[0]
    def budget():require(time.monotonic()<deadline,'reconciliation_budget_exceeded')
    def facts(path):
        info=path.stat()
        require(stat.S_ISREG(info.st_mode),'ordinary_file_required')
        return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns
    def digest(path):
        value=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk:=stream.read(1024*1024):budget();value.update(chunk)
        return value.hexdigest()
    def track(path):
        path=local(path);before=facts(path)
        require(0<before[2]<=MAX_BYTES,'file_size_limit')
        total[0]+=before[2];require(total[0]<=MAX_BYTES,'aggregate_input_limit')
        fingerprint=digest(path);require(facts(path)==before,'input_changed')
        tracked[path]=(before,fingerprint)
        return fingerprint
    def database(path):
        for suffix in ('-wal','-shm','-journal'):
            require(not local(Path(str(path)+suffix)).exists(),'sqlite_sidecar_present')
        track(path)
        db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=0)
        try:
            db.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
        except Exception:
            db.close();raise
        return db
    try:
        require(offline_copy is True,'explicit_offline_copy_required')
        directory=case_path(directory)
        inventory=(sorted(p.name for p in directory.iterdir()),sorted(p.name for p in (directory/'archives').iterdir()))
        track(directory/'case.json')
        with closing(database(directory/'queue.sqlite3')) as queue, closing(database(directory/'flights.sqlite3')) as source:
            require(source.execute('PRAGMA integrity_check(1)').fetchone()==('ok',),'database_integrity_failed')
            require_current(source,8)
            queue.row_factory=sqlite3.Row
            rows=[dict(row) for row in queue.execute('SELECT * FROM jobs ORDER BY sequence LIMIT 101')]
            require(0<len(rows)<=100,'bounded_recorded_jobs_required')
            require(not any(row['state'] in ('queued','running') for row in rows),'unfinished_jobs_require_review')
            require(all(row['state'] in ('succeeded','quarantined','blocked') for row in rows),'unsupported_job_state')
            successful=[row for row in rows if row['state']=='succeeded']
            require(successful,'successful_batches_required')
            with tempfile.TemporaryDirectory(prefix='ain-case-reconstruction-') as scratch:
                reconstructed=Path(scratch)/'flights.sqlite3'
                expected={}
                for row in rows:
                    budget()
                    require(isinstance(row['job_id'],str) and re.fullmatch('[0-9a-f]{32}',row['job_id']),'invalid_job_identity')
                    fingerprint=track(directory/'archives'/(row['job_id']+'.zip'))
                    require(fingerprint==row['archive_sha256'],'archive_identity_mismatch')
                    if row['state']!='succeeded':continue
                    require(isinstance(row['result_json'],str) and len(row['result_json'])<=4096,'bounded_result_required')
                    receipt=json.loads(row['result_json'])
                    year,month=map(int,row['period'].split('-'))
                    result=import_archive(directory/'archives'/(row['job_id']+'.zip'),reconstructed,year,month,
                                          synthetic=True,expected_sha256=fingerprint)
                    require(receipt['sha256']==fingerprint and receipt['period']==row['period'] and receipt['source_url']==result['source_url'],'queue_result_binding_mismatch')
                    require(receipt['status'] in ('imported','already_imported'),'queue_result_status_invalid')
                    expected[fingerprint]=(result['source_url'],row['period'],result['rows_read'])
                report['scratch_reconstruction']=True
                ledger={}
                for entry in source.execute('SELECT sha256,source_url,period,rows_read,rows_inserted,duplicate_rows FROM imports LIMIT 101'):
                    fingerprint,url,period,read,inserted,duplicates=entry
                    require(fingerprint not in ledger,'duplicate_ledger_identity')
                    require(all(type(v) is int and v>=0 for v in (read,inserted,duplicates)) and read==inserted+duplicates,'ledger_accounting_invalid')
                    ledger[fingerprint]=(url,period,read,inserted,duplicates)
                require(set(ledger)==set(expected),'ledger_batch_set_mismatch')
                for fingerprint,values in expected.items():require(ledger[fingerprint][:3]==values,'ledger_metadata_mismatch')
                for row in successful:
                    receipt=json.loads(row['result_json'])
                    counters=tuple(receipt[k] for k in ('rows_read','rows_inserted','duplicate_rows'))
                    require(all(type(v) is int and v>=0 for v in counters) and counters==ledger[row['archive_sha256']][2:],'queue_result_accounting_mismatch')
                with closing(sqlite3.connect(reconstructed)) as rebuilt:
                    left=source.execute('SELECT '+FLIGHT_COLUMNS+' FROM flights ORDER BY source,source_record_id')
                    right=rebuilt.execute('SELECT '+FLIGHT_COLUMNS+' FROM flights ORDER BY source,source_record_id')
                    count=0
                    while True:
                        budget();a=left.fetchmany(256);b=right.fetchmany(256)
                        require(a==b,'stored_rows_do_not_match_archives')
                        if not a:break
                        count+=len(a)
                require(sum(row[3] for row in ledger.values())==count,'total_inserted_rows_mismatch')
                report.update(flight_records=count,successful_jobs=len(successful),retained_jobs=len(rows),
                              import_ledgers=len(ledger),archive_sha256=sorted(expected))
        for path,(before,fingerprint) in tracked.items():
            require(facts(path)==before and digest(path)==fingerprint,'input_changed')
        require(inventory==(sorted(p.name for p in directory.iterdir()),sorted(p.name for p in (directory/'archives').iterdir())),'case_entries_changed')
        for name in ('queue.sqlite3','flights.sqlite3'):
            require(not any((directory/(name+suffix)).exists() for suffix in ('-wal','-shm','-journal')),'sqlite_sidecar_present')
        report.update(consistent=True,input_sha256={path.name:fingerprint for path,(_,fingerprint) in tracked.items()},
                      terminal_review_jobs=sum(row['state']!='succeeded' for row in rows))
    except ValueError as error:
        codes={'reconciliation_budget_exceeded','ordinary_file_required','file_size_limit','aggregate_input_limit','input_changed','sqlite_sidecar_present','explicit_offline_copy_required','database_integrity_failed','bounded_recorded_jobs_required','unfinished_jobs_require_review','unsupported_job_state','successful_batches_required','invalid_job_identity','archive_identity_mismatch','bounded_result_required','queue_result_binding_mismatch','queue_result_status_invalid','queue_result_accounting_mismatch','duplicate_ledger_identity','ledger_accounting_invalid','ledger_batch_set_mismatch','ledger_metadata_mismatch','stored_rows_do_not_match_archives','total_inserted_rows_mismatch','case_entries_changed'}
        report['errors']=[str(error) if str(error) in codes else 'reconciliation_unavailable']
    except Exception:report['errors']=['reconciliation_unavailable']
    report['elapsed_seconds']=round(SECONDS-(deadline-time.monotonic()),6)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('case')
    parser.add_argument('--offline-copy',action='store_true')
    args=parser.parse_args();result=reconcile(args.case,offline_copy=args.offline_copy)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['consistent'] else 2)
