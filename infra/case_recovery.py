"""Opt-in local paired case-workspace backup; restore only to a new private directory."""
import argparse
from contextlib import ExitStack,closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time
from uuid import UUID,uuid4
from infra import recovery
from infra.recovery_state import RESTORE_MARKER,require_complete_restore
from services.api.research_cases import ResearchCaseService,encoded

MANIFEST='case-workspace-backup.json'
CASE_FILE='research-cases.sqlite3'
TABLES=('cases','case_events','case_evidence','case_agents','case_gates')
MAX_CASES=2000


class CaseRecoveryError(ValueError):pass


def require(ok,code):
    if not ok:raise CaseRecoveryError(code)


def local_path(value):
    raw=str(value);require(not raw.startswith(('\\\\','//')) and '://' not in raw,'local_path_required')
    path=Path(value).absolute()
    require(not any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path,*path.parents)),'unredirected_path_required')
    return path.resolve()


def file_at(root,name):
    root=local_path(root);file=local_path(root/name)
    require(file.is_relative_to(root) and file.is_file(),'required_file_missing')
    return file


def target_path(source,destination):
    source=local_path(source);destination=local_path(destination)
    require(not destination.exists(),'new_destination_required')
    require(not destination.is_relative_to(source) and not source.is_relative_to(destination),'separate_destination_required')
    return destination


def write_new(path,value):
    with path.open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')


def case_facts(database,cases):
    database=local_path(database);cases=local_path(cases)
    require(cases.stat().st_size<=256*1024*1024,'case_store_exceeds_local_bound')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=5)) as auth,closing(sqlite3.connect(cases.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.row_factory=sqlite3.Row
        require(db.execute('PRAGMA user_version').fetchone()[0]==4,'case_schema_4_required')
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not db.execute('PRAGMA foreign_key_check').fetchall(),'case_integrity_failed')
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        require(names==set(TABLES),'case_table_inventory_changed')
        counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in TABLES}
        require(counts['cases']<=MAX_CASES and counts['case_events']<=MAX_CASES*100,'case_inventory_exceeds_local_bound')
        users={r[0] for r in auth.execute('SELECT id FROM auth_users')};owners=set();seen={name:0 for name in TABLES}
        service=object.__new__(ResearchCaseService) # Projection only: never initialize/migrate the store being verified.
        for row in db.execute('SELECT * FROM cases ORDER BY id'):
            require(row['owner_id'] in users,'case_owner_missing');owners.add(row['owner_id'])
            UUID(row['id']);UUID(row['source_run_id']);require(isinstance(row['version'],int) and 1<=row['version']<=100,'invalid_case_version')
            require(isinstance(row['title'],str) and 1<=len(row['title'])<=160,'invalid_case_title')
            result=service.projection(db,row);events=result['events'];source=result['source_snapshot']
            for value in (row['created_at'],row['updated_at'],*(e['created_at'] for e in events)):
                require(datetime.fromisoformat(value).tzinfo is not None,'case_timestamp_changed')
            require(source.get('run_id')==row['source_run_id'] and source.get('model_version')=='delay-v2' and source.get('research_only') is True and source.get('operational_serving_approved') is False,'case_source_scope_changed')
            require(row['status'] in ('open','closed') and (row['outcome'] is None if row['status']=='open' else isinstance(row['outcome'],str) and 1<=len(row['outcome'])<=2000),'case_outcome_changed')
            for index,event in enumerate(events):
                expected=('opened',) if index==0 else ('close',) if row['status']=='closed' and index==len(events)-1 else ('note','evidence','agent','gate')
                require(event['action'] in expected and isinstance(event['note'],str) and len(event['note'])<=2000,'case_event_changed')
            if row['status']=='closed':require(events[-1]['note']==row['outcome'],'case_closure_changed')
            require(row['status']!='closed' or row['version']>1,'invalid_closed_case_version')
            seen['cases']+=1;seen['case_events']+=len(events)
            for table,key in [('case_evidence','attachments'),('case_agents','agent_links'),('case_gates','gate_links')]:seen[table]+=len(result[key])
        require(counts==seen,'unbound_case_rows')
        content=hashlib.sha256()
        for table in TABLES:
            content.update((table+'\n').encode())
            for row in db.execute('SELECT * FROM '+table+' ORDER BY '+('id' if table=='cases' else 'case_id,version' if table=='case_events' else 'case_id,attached_version')):
                content.update((encoded(dict(row))+'\n').encode())
    return {'schema_version':4,'row_counts':counts,'content_sha256':content.hexdigest(),
        'owner_bindings_sha256':hashlib.sha256(encoded(sorted(owners)).encode()).hexdigest()}


def _verify_contents(directory):
    directory=local_path(directory);manifest_file=file_at(directory,MANIFEST)
    for entry in directory.rglob('*'):local_path(entry)
    require(manifest_file.stat().st_size<=64000,'manifest_exceeds_bound')
    manifest=json.loads(manifest_file.read_text(encoding='utf-8'))
    require(manifest.get('format')=='ain-case-workspace-backup-v1' and manifest.get('encrypted') is False,'unsupported_case_backup')
    require(manifest.get('database_writers_excluded_during_capture') is True and manifest.get('offline_acknowledged') is True and manifest.get('service_shutdown_verified') is False and manifest.get('production_ready') is False,'unsupported_case_backup_claims')
    UUID(manifest['snapshot_id']);require(datetime.fromisoformat(manifest['created_at']).tzinfo is not None,'invalid_backup_timestamp')
    primary=file_at(directory,'application/manifest.json')
    require(recovery.checksum(primary)==manifest['application_manifest_sha256'],'application_manifest_changed')
    application=recovery.verify(directory/'application')
    case_file=file_at(directory,CASE_FILE)
    require(case_file.stat().st_size==manifest['case_file']['size_bytes'] and recovery.checksum(case_file)==manifest['case_file']['sha256'],'case_file_changed')
    facts=case_facts(directory/'application/ain.sqlite3',case_file)
    require(facts==manifest['cases'],'case_receipt_changed')
    expected={MANIFEST,CASE_FILE,'application/manifest.json',*('application/'+r['path'] for r in application['files'])}
    actual=set()
    for entry in directory.rglob('*'):
        local_path(entry)
        if entry.is_file():actual.add(entry.relative_to(directory).as_posix())
    require(actual-{RESTORE_MARKER}==expected,'backup_file_inventory_changed')
    return manifest


def verify(directory,manifest_sha256):
    directory=local_path(directory);require_complete_restore(directory/'ain.sqlite3')
    require(isinstance(manifest_sha256,str) and re.fullmatch('[0-9a-f]{64}',manifest_sha256),'manifest_pin_required')
    require(recovery.checksum(file_at(directory,MANIFEST))==manifest_sha256,'manifest_pin_changed')
    return _verify_contents(directory)


def _sqlite_copy(source,target):
    started=time.monotonic()
    def progress(status,remaining,total):require(time.monotonic()-started<120,'sqlite_copy_timeout')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=5)) as src,closing(sqlite3.connect(target)) as dst:
        src.backup(dst,pages=256,progress=progress,sleep=.01)


def _standalone_copy(database):
    # Only newly created private copies: eliminate any dependency on WAL/SHM sidecars.
    with closing(sqlite3.connect(database)) as db:
        require(db.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete','standalone_snapshot_required')


def _seal_application(directory):
    manifest=recovery.verify(directory)
    _standalone_copy(directory/'ain.sqlite3')
    for entry in manifest['files']:
        if entry['path']=='ain.sqlite3':
            entry['sha256']=recovery.checksum(directory/'ain.sqlite3')
            entry['size_bytes']=(directory/'ain.sqlite3').stat().st_size
    # This manifest belongs to the fresh, still-marked incomplete paired bundle.
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    recovery.verify(directory)


def backup(source,destination,*,offline_acknowledged=False):
    require(offline_acknowledged is True,'offline_acknowledgment_required')
    source=local_path(source);destination=target_path(source,destination)
    require_complete_restore(source/'ain.sqlite3')
    application=file_at(source,'ain.sqlite3');cases=file_at(source,CASE_FILE)
    for name in recovery.FILES:local_path(source/name)
    require(not application.samefile(cases),'separate_databases_required')
    with ExitStack() as stack:
        # Separate guard connections exclude writers; read-only SQLite backup connections can still read committed pages.
        for file in (application,cases):
            guard=stack.enter_context(closing(sqlite3.connect(file.as_uri()+'?mode=rw',uri=True,timeout=5)))
            guard.execute('BEGIN IMMEDIATE');stack.callback(guard.rollback)
        recovery.database_facts(application)
        with closing(sqlite3.connect(application.as_uri()+'?mode=ro',uri=True)) as db:
            require(db.execute("SELECT COUNT(*) FROM agent_runs WHERE json_extract(result_json,'$.state') IN ('queued','running')").fetchone()[0]==0,'active_agent_work_must_stop')
        original=case_facts(application,cases)
        destination.mkdir(parents=True,exist_ok=False);write_new(destination/RESTORE_MARKER,{'format':'ain-case-backup-incomplete-v1'})
        recovery.backup(source,destination/'application');_seal_application(destination/'application')
        _sqlite_copy(cases,destination/CASE_FILE);_standalone_copy(destination/CASE_FILE)
        copied=case_facts(destination/'application/ain.sqlite3',destination/CASE_FILE)
        require(copied==original,'paired_case_copy_changed')
        manifest={'format':'ain-case-workspace-backup-v1','snapshot_id':str(uuid4()),'created_at':datetime.now(timezone.utc).isoformat(),
            'application_manifest_sha256':recovery.checksum(destination/'application/manifest.json'),
            'case_file':{'sha256':recovery.checksum(destination/CASE_FILE),'size_bytes':(destination/CASE_FILE).stat().st_size},'cases':copied,
            'database_writers_excluded_during_capture':True,'offline_acknowledged':True,'service_shutdown_verified':False,
            'encrypted':False,'scope':'Paired auth/application and schema-4 cases with existing active-model/index inventory; no raw archives or Ollama weights',
            'production_ready':False}
        write_new(destination/MANIFEST,manifest);_verify_contents(destination)
        (destination/RESTORE_MARKER).unlink()
    pin=recovery.checksum(destination/MANIFEST);verify(destination,pin)
    return {'format':manifest['format'],'snapshot_id':manifest['snapshot_id'],'manifest_sha256':pin,'cases':copied,'encrypted':False,'production_ready':False}


def restore(source,destination,manifest_sha256,*,offline_acknowledged=False):
    require(offline_acknowledged is True,'offline_acknowledgment_required')
    source=local_path(source);destination=target_path(source,destination);manifest=verify(source,manifest_sha256)
    destination.mkdir(parents=True,exist_ok=False);write_new(destination/RESTORE_MARKER,{'format':'ain-case-restore-incomplete-v1','snapshot_id':manifest['snapshot_id']})
    # Legacy restore runs in a private child so its marker removal cannot expose a half-restored paired workspace.
    stage=destination/'application-stage';primary_receipt=recovery.restore(source/'application',stage)
    application=recovery.verify(source/'application')
    for entry in application['files']:
        origin=file_at(stage,entry['path']);target=destination/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
        require(recovery.checksum(origin)==recovery.checksum(target),'restored_application_copy_changed')
    shutil.copyfile(stage/'recovery-receipt.json',destination/'recovery-receipt.json')
    shutil.copyfile(file_at(source,CASE_FILE),destination/CASE_FILE)
    require(recovery.checksum(destination/CASE_FILE)==manifest['case_file']['sha256'],'restored_cases_changed')
    facts=case_facts(destination/'ain.sqlite3',destination/CASE_FILE);require(facts==manifest['cases'],'restored_case_inventory_changed')
    require(recovery.database_facts(destination/'ain.sqlite3')==recovery.database_facts(stage/'ain.sqlite3'),'restored_application_facts_changed')
    verify(source,manifest_sha256)
    receipt={'format':'ain-case-workspace-restore-v1','snapshot_id':manifest['snapshot_id'],'manifest_sha256':manifest_sha256,
        'restored_at':datetime.now(timezone.utc).isoformat(),'cases':facts,'case_contents_preserved':True,'owner_bindings_verified':True,
        'restored_sessions_revoked':primary_receipt['sessions_revoked'],'session_revocation_audited':primary_receipt['session_revocation_audited'],
        'primary_stage_retained':True,'encrypted':False,'original_state_replaced':False,'production_ready':False}
    write_new(destination/'case-workspace-restore.json',receipt);(destination/RESTORE_MARKER).unlink()
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('backup','verify','restore'))
    parser.add_argument('--source',required=True);parser.add_argument('--destination');parser.add_argument('--manifest-sha256');parser.add_argument('--offline-acknowledged',action='store_true');args=parser.parse_args()
    try:
        if args.action=='verify':verify(args.source,args.manifest_sha256);result={'verified':True,'production_ready':False}
        else:
            require(args.destination is not None,'new_destination_required');destination=recovery.private_target(args.destination)
            result=backup(args.source,destination,offline_acknowledged=args.offline_acknowledged) if args.action=='backup' else restore(args.source,destination,args.manifest_sha256,offline_acknowledged=args.offline_acknowledged)
        print(json.dumps(result,indent=2))
    except Exception as error:
        print(json.dumps({'passed':False,'error':str(error) if isinstance(error,CaseRecoveryError) else 'case_workspace_recovery_unverified','production_ready':False}));raise SystemExit(2) from None


if __name__=='__main__':main()
