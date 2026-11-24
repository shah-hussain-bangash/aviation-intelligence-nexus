"""Generate an offline synthetic case and reject changed copies without altering its data."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import shutil
import sqlite3
from uuid import uuid4

from pipelines.synthetic_ingestion import create_case,enqueue,work_one,jobs,host,local
from pipelines.reconcile_synthetic_case import reconcile
from pipelines.verify_import_safety import BASE,identity
from services.api.paths import ROOT

SOURCES=('pipelines/reconcile_synthetic_case.py','pipelines/verify_case_reconciliation.py','pipelines/synthetic_ingestion.py')


def fingerprints(case):
    return {p.relative_to(case).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in case.rglob('*') if p.is_file()}


def verify(directory):
    host();directory=local(directory);context=identity()
    context['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in SOURCES})
    directory.mkdir(parents=True,exist_ok=False)
    report={'format':'ain-case-reconciliation-drill-v1','checked_at':datetime.now(timezone.utc).isoformat(),
            'case_id':directory.name,**context,'passed':False,'checks':{},'synthetic_only':True,
            'primary_database_accessed':False,'deployment_performed':False,'production_ready':False}
    try:
        case=create_case(directory/'original')
        enqueue(case,BASE,year=2025,month=1)
        february=[*BASE[0]];february[0]='2025-02-01'
        enqueue(case,[february],year=2025,month=2)
        new=[*BASE[0]];new[2]='9';conflict=[*BASE[0]];conflict[7]='99'
        enqueue(case,[new,conflict],year=2025,month=1)
        for _ in range(3):work_one(case)
        before=fingerprints(case)
        positive=reconcile(case,offline_copy=True)
        preserved=before==fingerprints(case)
        altered=directory/'altered';shutil.copytree(case,altered)
        with closing(sqlite3.connect(altered/'flights.sqlite3')) as db,db:
            db.execute('UPDATE flights SET arrival_delay_minutes=88 WHERE cancelled=0 AND diverted=0')
        altered_before=fingerprints(altered)
        changed=reconcile(altered,offline_copy=True)
        negative_preserved=altered_before==fingerprints(altered)
        metadata=directory/'metadata';shutil.copytree(case,metadata)
        with closing(sqlite3.connect(metadata/'queue.sqlite3')) as db,db:
            db.execute("UPDATE jobs SET result_json=? WHERE sequence=1",(json.dumps({'status':'imported','sha256':'0'*64,'period':'2025-01','source_url':'PRIVATE_SOURCE'}),))
        bad_metadata=reconcile(metadata,offline_copy=True)
        report['checks']={
            'retained_batch_reconstruction_matches':positive['consistent'],
            'all_selected_rows_reconciled':positive.get('flight_records')==4,
            'two_successful_batches_two_ledgers':positive.get('successful_jobs')==positive.get('import_ledgers')==2,
            'quarantine_retained_for_review':positive.get('terminal_review_jobs')==1 and jobs(case)[2]['state']=='quarantined',
            'source_case_bytes_entries_preserved':preserved,
            'altered_rows_rejected':not changed['consistent'] and changed['errors']==['stored_rows_do_not_match_archives'],
            'altered_copy_not_repaired':negative_preserved,
            'changed_queue_binding_rejected':not bad_metadata['consistent'] and bad_metadata['errors']==['queue_result_binding_mismatch'],
            'explicit_offline_admission_required':reconcile(case)['errors']==['explicit_offline_copy_required'],
            'source_unchanged':all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in context['source_sha256'].items())}
        report.update(reconciliation=positive,changed_rows_check=changed,changed_binding_check=bad_metadata,
                      original_case_sha256=before)
        report['passed']=all(report['checks'].values())
    except Exception:report['error']='synthetic_reconciliation_check_failed'
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    result=verify(ROOT/'.local/case-reconciliation'/uuid4().hex)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 2)
