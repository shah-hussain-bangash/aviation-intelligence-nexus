"""Read-only January archive identity link, not a claim about the original import event."""
import hashlib
import json
import os
from pathlib import Path
from services.api.data_quality import load_quality, REPORT_SHA256
from services.api.intake_overview import require


def project(envelope, role):
    require(role in ('admin','researcher','viewer'))
    # Lazy import avoids the legacy importer/main module cycle. No importer is executed.
    from pipelines.verify_intake import validate
    require(isinstance(envelope,dict) and set(envelope)=={'format','receipt_text','receipt_sha256','dataset_report_sha256'})
    require(envelope['format']=='ain-batch-lineage-v1' and envelope['dataset_report_sha256']==REPORT_SHA256)
    text=envelope['receipt_text']; require(isinstance(text,str) and len(text.encode('utf-8'))<=64000)
    require(hashlib.sha256(text.encode('utf-8')).hexdigest()==envelope['receipt_sha256'])
    receipt=validate(json.loads(text))
    require(receipt['disposition']=='accepted' and receipt['declared_period']=='2025-01')
    audit=load_quality(); month=audit['months'][0]
    matches=[r for r in month['manifests'] if r['sha256']==receipt['archive_sha256']]
    require(len(matches)==1 and matches[0]['rows_read']==receipt['rows_read'])
    result={'format':'ain-batch-lineage-view-v1','relation':'archive_identity_recheck',
        'dataset':{'period':month['period'],'recorded_rows':month['records'],'archive_sha256':receipt['archive_sha256'],
            'audit_report_sha256':REPORT_SHA256},
        'intake':{'run_id':receipt['run_id'],'record':'accepted/'+receipt['run_id'],'receipt_sha256':envelope['receipt_sha256'],
            'checked_at':receipt['checked_at'],'declared_source_url':receipt['declared_source_url'],'disposition':'accepted'},
        'receipt_authenticated':False,'original_import_receipt':False,'live_database_checked':False,
        'import_performed':False,'production_ready':False}
    if role=='admin': result['admin_receipt']=receipt
    return result


def load_lineage(state,role):
    require(role in ('admin','researcher','viewer'))
    folder=Path('/intake-status') if os.environ.get('AIN_INTAKE_OVERVIEW_MOUNTED')=='1' else Path(state)/'intake-dashboard'
    path=folder/'batch-lineage.json'
    require(not path.is_symlink() and path.is_file() and path.stat().st_size<=100000)
    with path.open('rb') as stream: raw=stream.read(100001)
    require(len(raw)<=100000)
    return project(json.loads(raw),role)
