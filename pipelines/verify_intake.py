"""Read-only unsigned intake-receipt consistency and archive-byte verification."""
import argparse
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
from pipelines.intake_bts import MAX_ARCHIVE, MAX_CSV, MAX_ROWS, SECONDS
from pipelines.import_bts import REQUIRED, source_url
from infra.recovery import private_target

FIELDS = {'format','policy_version','run_id','checked_at','disposition','declared_period','declared_source_url',
          'origin_verified','archive_sha256','archive_size_bytes','rows_read','unique_identities',
          'identical_duplicates','csv_columns','scan_complete','csv_crc_verified','scratch_database_used',
          'reason_code','primary_database_accessed','import_performed','training_performed','raw_snapshot_retained',
          'limits','elapsed_seconds','production_ready','scope'}
REASONS = {'invalid_zip','unsupported_zip_metadata','csv_line_limit','csv_member_count','unsafe_zip_member',
           'encrypted_zip','unsupported_compression','unsupported_zip_member','csv_size_limit','schema_invalid',
           'time_budget','row_limit','record_shape','invalid_record','conflicting_identity','empty_csv',
           'corrupt_zip','invalid_csv_encoding_or_syntax'}
SCOPE = 'Selected-field local structural preflight; not source authorization, business accuracy or operational acceptance.'


def require(condition):
    if not condition:raise ValueError('Invalid intake artifact consistency')


def validate(receipt):
    require(isinstance(receipt,dict) and set(receipt)==FIELDS)
    require(receipt['format']=='ain-bts-intake-v1' and receipt['policy_version']=='bts-intake-v1')
    require(isinstance(receipt['run_id'],str) and re.fullmatch('[0-9a-f]{32}',receipt['run_id']))
    require(isinstance(receipt['checked_at'],str) and datetime.fromisoformat(receipt['checked_at']).utcoffset() is not None)
    require(isinstance(receipt['declared_period'],str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}',receipt['declared_period']))
    year,month=map(int,receipt['declared_period'].split('-'));date(year,month,1)
    require(receipt['declared_source_url']==source_url(year,month))
    for flag in ('origin_verified','primary_database_accessed','import_performed','training_performed','production_ready'):
        require(receipt[flag] is False)
    require(receipt['raw_snapshot_retained'] is True and receipt['scope']==SCOPE)
    for flag in ('scan_complete','csv_crc_verified','scratch_database_used'):require(type(receipt[flag]) is bool)
    for count in ('archive_size_bytes','rows_read','unique_identities','identical_duplicates'):
        require(type(receipt[count]) is int and receipt[count]>=0)
    require(receipt['archive_size_bytes']<=MAX_ARCHIVE and receipt['rows_read']<=MAX_ROWS+1)
    require(isinstance(receipt['archive_sha256'],str) and re.fullmatch('[0-9a-f]{64}',receipt['archive_sha256']))
    require(type(receipt['elapsed_seconds']) in (int,float) and math.isfinite(receipt['elapsed_seconds']) and receipt['elapsed_seconds']>=0)
    limits=receipt['limits'];expected={'archive_bytes':MAX_ARCHIVE,'csv_bytes':MAX_CSV,'rows':MAX_ROWS,'seconds':SECONDS}
    require(isinstance(limits,dict) and limits==expected and all(type(v) is int for v in limits.values()))
    columns=receipt['csv_columns'];require(columns is None or type(columns) is int and len(REQUIRED)<=columns<=200)
    valid_prefix=receipt['unique_identities']+receipt['identical_duplicates']
    require(valid_prefix<=receipt['rows_read'])
    require(not receipt['rows_read'] or receipt['scratch_database_used'])
    require(not receipt['rows_read'] or columns is not None)
    require(not receipt['identical_duplicates'] or receipt['unique_identities']>0)
    if receipt['disposition']=='accepted':
        require(receipt['reason_code'] is None and receipt['scan_complete'] is True and receipt['csv_crc_verified'] is True)
        require(receipt['scratch_database_used'] is True and columns is not None)
        require(0<receipt['rows_read']<=MAX_ROWS and valid_prefix==receipt['rows_read'])
    else:
        require(receipt['disposition']=='quarantined' and isinstance(receipt['reason_code'],str) and receipt['reason_code'] in REASONS)
        require(receipt['scan_complete'] is False and receipt['csv_crc_verified'] is False)
    return receipt


def verify_run(directory):
    directory=Path(directory)
    require(not directory.is_symlink() and directory.is_dir())
    receipt_file,archive=directory/'receipt.json',directory/'archive.zip'
    require(not receipt_file.is_symlink() and not archive.is_symlink())
    require(receipt_file.is_file() and receipt_file.stat().st_size<=64000 and archive.is_file())
    receipt=validate(json.loads(receipt_file.read_text(encoding='utf-8')))
    require(directory.name==receipt['run_id'] and directory.parent.name==receipt['disposition'])
    with archive.open('rb') as stream:
        import os
        before=os.fstat(stream.fileno())
        require(before.st_size==receipt['archive_size_bytes'])
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
        after=os.fstat(stream.fileno())
    current=archive.stat()
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    require(identity(before)==identity(after)==identity(current))
    require(actual==receipt['archive_sha256'])
    return {'format':'ain-bts-intake-verification-v1','verified':True,'check':'unsigned_content_consistency',
        'run_id':receipt['run_id'],'disposition':receipt['disposition'],'declared_period':receipt['declared_period'],
        'archive_sha256':actual,'archive_size_bytes':before.st_size,'declared_rows_read':receipt['rows_read'],
        'reason_code':receipt['reason_code'],'archive_hash_matches_receipt':True,
        'receipt_authenticated':False,'rows_rescanned':False,'source_rights_verified':False,
        'import_authorized':False,'import_performed':False,'production_ready':False,
        'scope':'Archive bytes match an unsigned structurally consistent receipt; not row revalidation, source authentication or import approval.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run_directory',type=Path)
    args=parser.parse_args()
    try:result=verify_run(private_target(args.run_directory))
    except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
        print(json.dumps({'verified':False,'error':'intake_artifact_unverifiable','import_authorized':False,'production_ready':False}))
        raise SystemExit(2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
