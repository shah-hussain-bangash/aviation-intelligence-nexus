"""Stage pinned June archive bytes and ZIP metadata; never open a member or parse flight rows."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import time
import zipfile

from infra.research_model_recovery import ordinary, unique_object
from ml.register_evaluation import PLAN_SHA256, require
from pipelines.import_bts import owned_snapshot, bounded_zip_metadata, source_url, MAX_ARCHIVE, MAX_CSV, SECONDS, budget
from pipelines.synthetic_ingestion import host, local
from pipelines.verify_import_safety import identity
from services.api.paths import ROOT

CSV_NAME = 'On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2025_6.csv'


def pin(value):
    require(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value), 'full_sha256_required')


def read_pinned(path, expected, maximum=1_000_000):
    pin(expected)
    raw=ordinary(path,maximum).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected, 'pinned_file_changed')
    return raw


def registration_record(path, expected):
    path=local(path)
    require('..' not in Path(path).parts and path.is_relative_to(ROOT/'.local') and path.name=='registration.json',
            'private_registration_required')
    r=json.loads(read_pinned(path,expected),object_pairs_hook=unique_object)
    require(isinstance(r,dict) and r.get('format')=='ain-external-month-registration-v1'
            and r.get('state')=='plan_prepared' and r.get('candidate_period')=='2025-06'
            and r.get('production_ready') is False and r.get('candidate_rows_read') is False,
            'prepared_june_registration_required')
    plan_bytes=read_pinned(path.parent/'plan.json',PLAN_SHA256,64000)
    require(r.get('plan_sha256')==PLAN_SHA256 and r.get('plan')==json.loads(plan_bytes,object_pairs_hook=unique_object),
            'frozen_plan_binding_changed')
    require(r.get('declared_source_url')==source_url(2025,6), 'declared_source_changed')
    m=r['model']
    read_pinned(path.parent/'model/model.joblib',m['artifact_sha256'],32_000_000)
    report=json.loads(read_pinned(path.parent/'model/report.json',m['report_sha256']),object_pairs_hook=unique_object)
    public=json.loads(read_pinned(ROOT/'docs/reports/Delay_v2.json',m['public_report_sha256']),object_pairs_hook=unique_object)
    require(report==public and report.get('artifact_sha256')==m['artifact_sha256']
            and report.get('threshold')==r.get('frozen_threshold')
            and report.get('training_delay_prevalence')==r.get('constant_training_prior'), 'frozen_model_binding_changed')
    return path,r


def archive_metadata(snapshot):
    bounded_zip_metadata(snapshot)
    with zipfile.ZipFile(snapshot) as archive:
        entries=archive.infolist()
        require(1<=len(entries)<=16,'bounded_zip_member_count_required')
        for e in entries:
            name=e.filename.replace('\\','/')
            require(e.filename==e.orig_filename and not name.startswith('/') and ':' not in name
                    and '..' not in PurePosixPath(name).parts and not stat.S_ISLNK(e.external_attr>>16),
                    'unsafe_zip_member')
            require(not e.flag_bits&1 and e.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),
                    'unsupported_zip_member_encoding')
        csvs=[e for e in entries if e.filename.lower().endswith('.csv')]
        require(len(csvs)==1 and csvs[0].filename==CSV_NAME,'declared_june_csv_member_required')
        e=csvs[0]
        require(0<e.file_size<=MAX_CSV and e.compress_size>0,'bounded_csv_metadata_required')
        # Deliberately no ZipFile.open/read/testzip: even the header is deferred.
        return {'csv_member':e.filename,'csv_uncompressed_size_declared':e.file_size,
                'csv_compressed_size_declared':e.compress_size,'csv_crc32_declared':f'{e.CRC:08x}',
                'member_count':len(entries)}


def stage(registration, registration_sha256, archive, archive_sha256, directory):
    host();pin(registration_sha256);pin(archive_sha256)
    require('..' not in Path(directory).parts and '..' not in Path(archive).parts
            and '..' not in Path(registration).parts,'unredirected_private_paths_required')
    target=local(directory);archive=local(archive)
    require(target.is_relative_to(ROOT/'.local') and not target.exists(),'fresh_private_admission_directory_required')
    require(archive.is_relative_to(ROOT/'.local'),'private_archive_required')
    registration,r=registration_record(registration,registration_sha256)
    deadline=time.monotonic()+SECONDS
    with owned_snapshot(archive,deadline) as (snapshot,digest):
        require(digest==archive_sha256,'candidate_archive_pin_mismatch')
        metadata=archive_metadata(snapshot);budget(deadline)
        snapshot.seek(0)
        target.mkdir(parents=True,exist_ok=False)
        with (target/'archive.zip').open('xb') as output:
            while chunk:=snapshot.read(1024*1024):
                budget(deadline);output.write(chunk)
        size=(target/'archive.zip').stat().st_size
        require(0<size<=MAX_ARCHIVE,'retained_archive_size_invalid')
        with (target/'archive.zip').open('rb') as retained:
            require(hashlib.file_digest(retained,'sha256').hexdigest()==digest,'retained_archive_changed')
    # Recheck the frozen registration after capture, without reading any member.
    registration_record(registration,registration_sha256)
    provenance=identity()
    provenance['source_sha256'].update({'ml/admit_evaluation_archive.py':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest()})
    result={'format':'ain-june-archive-admission-v1','state':'archive_metadata_staged',
        'checked_at':datetime.now(timezone.utc).isoformat(),**provenance,
        'registration_file':registration.relative_to(ROOT).as_posix(),'registration_sha256':registration_sha256,
        'plan_sha256':PLAN_SHA256,'model_sha256':r['model']['artifact_sha256'],
        'declared_period':'2025-06','declared_source_url':source_url(2025,6),
        'archive_sha256':digest,'archive_size_bytes':size,**metadata,
        'compressed_archive_hash_verified':True,'member_data_opened':False,
        'candidate_rows_parsed':False,'candidate_labels_inspected':False,'row_count':None,
        'csv_schema_verified':False,'csv_crc_verified':False,'row_period_verified':False,
        'data_quality_verified':False,'source_origin_verified':False,'source_rights_verified':False,
        'globally_untouched_holdout_established':False,'global_single_use_enforced':False,
        'evaluation_authorized':False,'model_deserialized':False,'inference_executed':False,
        'primary_database_accessed':False,'import_performed':False,'production_ready':False,
        'next_dependency':'Create and enforce an exclusive evaluation attempt before opening the CSV member; validate rows and quality within that attempt.'}
    with (target/'admission.json').open('x',encoding='utf-8') as output:
        json.dump(result,output,indent=2,allow_nan=False);output.write('\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',type=Path,required=True)
    parser.add_argument('--registration-sha256',required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--archive-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:r=stage(args.registration,args.registration_sha256,args.archive,args.archive_sha256,args.output)
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):
        parser.exit(2,'Archive metadata admission was not confirmed. Preserve any partial private output; no row-quality or evaluation approval is implied.\n')
    print(json.dumps(r,indent=2))


if __name__=='__main__':main()
