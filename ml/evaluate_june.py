"""One checkout-local June attempt: row validation, trusted frozen inference and planned metrics."""
import argparse
from contextlib import closing
import csv
from datetime import date,datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
import zipfile

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from infra.research_model_recovery import unique_object,ordinary
from ml.admit_evaluation_archive import read_pinned, registration_record, archive_metadata, pin, CSV_NAME
from ml.june_metrics import summarize
from ml.prepare_dataset import FEATURES
from pipelines.import_bts import owned_snapshot, normalize, BoundedLines, REQUIRED, MAX_ROWS,MAX_ARCHIVE
from pipelines.synthetic_ingestion import host,local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

SECONDS=300
MAX_ELIGIBLE=1_000_000


class EvaluationFailure(ValueError):
    """Controlled reason code, without row values or private model exceptions."""


def require(ok,code):
    if not ok:raise EvaluationFailure(code)


def write_new(path,value,started=None):
    raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        if started:started()
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def scan(snapshot,output,deadline,counts):
    features=[];targets=[];dates=[]
    with closing(sqlite3.connect(output/'identities.sqlite3')) as db,db,zipfile.ZipFile(snapshot) as archive:
        db.execute('CREATE TABLE identities(k TEXT PRIMARY KEY,value TEXT NOT NULL)')
        with archive.open(CSV_NAME) as raw,io.TextIOWrapper(raw,encoding='utf-8-sig',newline='') as text:
            reader=csv.DictReader(BoundedLines(text,deadline))
            require(REQUIRED.issubset(reader.fieldnames or []) and len(reader.fieldnames)==len(set(reader.fieldnames)),
                    'csv_schema_invalid')
            for row in reader:
                require(time.monotonic()<deadline,'evaluation_time_budget')
                counts['rows_read']+=1;require(counts['rows_read']<=MAX_ROWS,'row_limit_exceeded')
                require(None not in row and all(value is not None for value in row.values()),'csv_row_shape_invalid')
                try:values=normalize(row,'2025-06')
                except (ValueError,TypeError,AttributeError):raise EvaluationFailure('candidate_record_invalid') from None
                record=json.dumps(values,allow_nan=False)
                inserted=db.execute('INSERT OR IGNORE INTO identities VALUES(?,?)',(values[1],record)).rowcount
                if not inserted:
                    require(db.execute('SELECT value FROM identities WHERE k=?',(values[1],)).fetchone()[0]==record,
                            'conflicting_natural_identity')
                    counts['identical_duplicates']+=1;continue
                counts['unique_identities']+=1
                if values[10]:counts['excluded_cancelled']+=1;continue
                if values[11]:counts['excluded_diverted']+=1;continue
                if values[7] is None:counts['excluded_missing_target']+=1;continue
                counts['eligible_records']+=1
                require(counts['eligible_records']<=MAX_ELIGIBLE,'eligible_memory_bound_exceeded')
                day=date.fromisoformat(values[2]);scheduled=values[9]
                features.append([values[3],values[4],values[5],values[8],str(day.month),str(day.day),
                                 str(day.isoweekday()),str(int(scheduled[:2])),str(int(scheduled[2:]))])
                targets.append(int(values[7]>=15));dates.append(values[2])
    require(counts['rows_read']>0 and counts['eligible_records']>0,'empty_evaluation_cohort')
    require(counts['rows_read']==counts['unique_identities']+counts['identical_duplicates'],'identity_counts_inconsistent')
    require(counts['unique_identities']==sum(counts[k] for k in ('eligible_records','excluded_cancelled',
            'excluded_diverted','excluded_missing_target')),'cohort_counts_inconsistent')
    return pd.DataFrame(features,columns=FEATURES,dtype=str),np.asarray(targets,dtype=int),dates


def evaluate(admission,admission_sha256,directory,*,trusted_registered_model=False):
    result={'format':'ain-frozen-june-evaluation-v1','state':'refused','attempt_consumed':False,
        'candidate_member_open_started':False,'rows_validated':False,'model_deserialization_started':False,
        'model_deserialized':False,'model_refitted':False,'inference_started':False,'inference_executed':False,
        'metrics_computed':False,'bootstrap_executed':False,'checkout_single_attempt_enforced':False,
        'global_single_use_enforced':False,'globally_untouched_holdout_established':False,
        'primary_database_accessed':False,'import_performed':False,'deployment_performed':False,'production_ready':False}
    output=None;owned_output=False
    try:
        host();require(trusted_registered_model is True,'explicit_trusted_registered_model_required');pin(admission_sha256)
        require('..' not in Path(admission).parts and '..' not in Path(directory).parts,'private_paths_required')
        admission=local(admission);output=local(directory)
        require(admission.is_relative_to(ROOT/'.local') and admission.name=='admission.json'
                and output.is_relative_to(ROOT/'.local') and not output.exists(),'fresh_private_evaluation_required')
        admitted=json.loads(read_pinned(admission,admission_sha256),object_pairs_hook=unique_object)
        require(admitted['format']=='ain-june-archive-admission-v1' and admitted['state']=='archive_metadata_staged'
                and admitted['declared_period']=='2025-06' and admitted['evaluation_authorized'] is False,
                'metadata_admission_required')
        registration=local(ROOT/admitted['registration_file'])
        registration,r=registration_record(registration,admitted['registration_sha256'])
        require(admitted['model_sha256']==r['model']['artifact_sha256'] and admitted['plan_sha256']==r['plan_sha256'],
                'admission_registration_binding_changed')
        model_bytes=read_pinned(registration.parent/'model/model.joblib',r['model']['artifact_sha256'],32_000_000)
        provenance=identity();provenance['source_sha256'].update({name:hashlib.sha256((Path(__file__).parent/filename).read_text(encoding='utf-8').encode()).hexdigest()
            for name,filename in [('ml/evaluate_june.py','evaluate_june.py'),('ml/june_metrics.py','june_metrics.py')]})
        deadline=time.monotonic()+SECONDS
        with owned_snapshot(local(admission.parent/'archive.zip'),deadline) as (snapshot,digest):
            require(digest==admitted['archive_sha256'],'candidate_archive_changed')
            metadata=archive_metadata(snapshot)
            require(all(admitted.get(k)==v for k,v in metadata.items()),'archive_metadata_changed')
            ledger=local(ROOT/'.local/evaluation-attempts/2025-06.json');ledger.parent.mkdir(parents=True,exist_ok=True)
            claim={'format':'ain-june-attempt-v1','attempt_id':uuid4().hex,'candidate_period':'2025-06',
                'claimed_at':datetime.now(timezone.utc).isoformat(),'admission_sha256':admission_sha256,
                'registration_sha256':admitted['registration_sha256'],'archive_sha256':digest,
                'model_sha256':r['model']['artifact_sha256'],'plan_sha256':r['plan_sha256'],
                'output':output.relative_to(ROOT).as_posix(),'policy':'One retained attempt per candidate month in this checkout; no reset or retry',**provenance}
            # Fixed checkout-level path and exclusive creation precede any CSV open.
            def claimed():
                result.update(state='failed',attempt_consumed=True,attempt_id=claim['attempt_id'],
                    attempt_receipt=ledger.relative_to(ROOT).as_posix(),checkout_single_attempt_enforced=True,
                    admission_sha256=admission_sha256,archive_sha256=digest,
                    registration_sha256=admitted['registration_sha256'],model_sha256=r['model']['artifact_sha256'],
                    plan_sha256=r['plan_sha256'],claimed_at=claim['claimed_at'],**provenance)
            claim_sha=write_new(ledger,claim,started=claimed);result['attempt_sha256']=claim_sha
            output.mkdir(parents=True,exist_ok=False)
            owned_output=True
            counts={key:0 for key in ('rows_read','unique_identities','identical_duplicates','eligible_records',
                    'excluded_cancelled','excluded_diverted','excluded_missing_target')};result['data_counts']=counts
            result['candidate_member_open_started']=True
            frame,y,dates=scan(snapshot,output,deadline,counts)
            result.update(rows_validated=True,csv_crc_verified=True,row_period_verified=True)
            require(set(np.unique(y))=={0,1},'two_target_classes_required')
            require(len(set(dates))>=2,'at_least_two_date_clusters_required')
            require(time.monotonic()<deadline,'evaluation_time_budget')
            result['model_deserialization_started']=True
            model=joblib.load(io.BytesIO(model_bytes));result['model_deserialized']=True
            require(list(model.classes_)==[0,1],'binary_model_class_order_required')
            result['inference_started']=True
            with threadpool_limits(limits=4):probabilities=np.asarray(model.predict_proba(frame[FEATURES]),dtype=float)
            require(probabilities.shape==(len(y),2) and np.isfinite(probabilities).all()
                    and ((probabilities>=0)&(probabilities<=1)).all()
                    and np.allclose(probabilities.sum(axis=1),1,rtol=0,atol=1e-6),'invalid_model_probabilities')
            result['inference_executed']=True
            require(time.monotonic()<deadline,'evaluation_time_budget')
            result['evaluation']=summarize(frame,y,probabilities[:,1],dates,r)
            result.update(metrics_computed=True,bootstrap_executed=True)
            read_pinned(admission,admission_sha256);registration_record(registration,admitted['registration_sha256'])
            with ordinary(admission.parent/'archive.zip',MAX_ARCHIVE).open('rb') as source:
                require(hashlib.file_digest(source,'sha256').hexdigest()==digest,'retained_archive_changed')
            require(time.monotonic()<deadline,'evaluation_time_budget')
            result.update(state='evaluated',completed_at=datetime.now(timezone.utc).isoformat(),
                limits={'seconds':SECONDS,'max_rows':MAX_ROWS,'max_eligible_rows':MAX_ELIGIBLE},
                limitations=['Historical June US records; no UAE transfer or actual-flight confirmation.',
                    'Conditional on completed non-diverted flights with observed target; reported schedules are not point-in-time snapshots.',
                    'One local unsigned checkout ledger; OS-owner edits or another checkout cannot be prevented.',
                    'No globally untouched holdout, statistical independence or production qualification is established.',
                    'No model, preprocessing, calibration or threshold refit; no deployment or operational action.'])
    except Exception as error:
        result.update(error='evaluation_failed_after_claim' if result['attempt_consumed'] else 'evaluation_admission_refused',
                      failure_type=type(error).__name__)
        if isinstance(error,EvaluationFailure):result['failure_code']=str(error)
    if result['attempt_consumed'] and owned_output:
        try:write_new(output/'report.json',result)
        except (OSError,ValueError):result.update(state='failed',error='evaluation_report_not_saved',report_persisted=False)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission',type=Path,required=True);parser.add_argument('--admission-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--trusted-registered-model',action='store_true')
    args=parser.parse_args();result=evaluate(args.admission,args.admission_sha256,args.output,trusted_registered_model=args.trusted_registered_model)
    print(json.dumps(result,indent=2,allow_nan=False));return 0 if result['state']=='evaluated' else 2


if __name__=='__main__':raise SystemExit(main())
