"""Consistent SQLite snapshots and verified restoration to a NEW private directory."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
from uuid import uuid4
from services.api.paths import ROOT,STATE,SCHEMA_VERSION
from agents.store import AgentStore

FILES=('ain.sqlite3','models/delay-v2/model.joblib','models/delay-v2/report.json','knowledge/index.json')
TABLES=('flights','imports','auth_users','auth_sessions','research_runs','gate_runs','knowledge_runs','agent_runs')


def timestamp():return datetime.now(timezone.utc).isoformat()


def checksum(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def safe_file(root,relative):
    if relative not in FILES:raise ValueError('Backup contains an unapproved file path')
    root=Path(root).resolve();file=root/relative
    if file.is_symlink() or not file.resolve().is_relative_to(root):raise ValueError('Backup file escapes its state directory')
    if not file.is_file():raise ValueError('Required backup file is missing')
    return file


def database_facts(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed')
        schema=db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        if schema!=SCHEMA_VERSION:raise ValueError('Backup schema is incompatible with this release')
        counts={table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in TABLES}
    return {'schema_version':schema,'row_counts':counts}


def verify(backup):
    backup=Path(backup).resolve()
    if (backup/'manifest.json').stat().st_size>64000:raise ValueError('Oversized backup manifest')
    manifest=json.loads((backup/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format')!='ain-recovery-v1' or not isinstance(manifest.get('files'),list):raise ValueError('Unsupported backup manifest')
    names=[entry['path'] for entry in manifest['files']]
    if len(names)!=len(set(names)) or 'ain.sqlite3' not in names:raise ValueError('Invalid backup inventory')
    for entry in manifest['files']:
        file=safe_file(backup,entry['path'])
        if file.stat().st_size!=entry['size_bytes'] or checksum(file)!=entry['sha256']:raise ValueError('Backup checksum mismatch')
    facts=database_facts(backup/'ain.sqlite3')
    if facts!=manifest['database']:raise ValueError('Database contents do not match the snapshot receipt')
    model='models/delay-v2/model.joblib' in names;report='models/delay-v2/report.json' in names
    if model!=report:raise ValueError('Incomplete active model pair')
    if model:
        metadata=json.loads((backup/'models/delay-v2/report.json').read_text(encoding='utf-8'))
        if metadata['artifact_sha256']!=checksum(backup/'models/delay-v2/model.joblib'):raise ValueError('Model artifact does not match its report')
    if 'knowledge/index.json' in names:
        envelope=json.loads((backup/'knowledge/index.json').read_text(encoding='utf-8'))
        if envelope['sha256']!=hashlib.sha256(json.dumps(envelope['payload'],sort_keys=True).encode()).hexdigest():raise ValueError('Knowledge index integrity failed')
    return manifest


def backup(state,destination):
    state=Path(state).resolve();destination=Path(destination).resolve()
    source=safe_file(state,'ain.sqlite3');destination.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    def progress(status,remaining,total):
        if time.monotonic()-started>120:raise TimeoutError('Snapshot exceeded its local time budget')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=5)) as src,closing(sqlite3.connect(destination/'ain.sqlite3')) as dst:
        src.backup(dst,pages=256,progress=progress,sleep=.01)
    inventory=[]
    for relative in FILES:
        if relative!='ain.sqlite3':
            if not (state/relative).exists():continue
            origin=safe_file(state,relative);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
        target=destination/relative
        inventory.append({'path':relative,'sha256':checksum(target),'size_bytes':target.stat().st_size})
    manifest={'format':'ain-recovery-v1','snapshot_id':str(uuid4()),'created_at':timestamp(),'database':database_facts(destination/'ain.sqlite3'),
        'files':inventory,'scope':'SQLite state, active delay-v2 model and knowledge index; excludes raw archives, retired models and Ollama weights',
        'elapsed_ms':round((time.monotonic()-started)*1000,2),'encrypted':False}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    verify(destination)
    return manifest


def restore(backup_directory,destination):
    started=time.monotonic();manifest=verify(backup_directory)
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
    for entry in manifest['files']:
        origin=safe_file(backup_directory,entry['path']);target=destination/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
        if checksum(target)!=entry['sha256']:raise ValueError('Restored file failed checksum verification')
    original=database_facts(destination/'ain.sqlite3')
    with closing(sqlite3.connect(destination/'ain.sqlite3')) as db,db:
        db.execute('DELETE FROM auth_sessions')
    AgentStore(destination/'ain.sqlite3').recover()
    restored=database_facts(destination/'ain.sqlite3')
    expected={**original['row_counts'],'auth_sessions':0}
    if restored['row_counts']!=expected:raise ValueError('Restored row counts differ from the snapshot')
    receipt={'format':'ain-restore-receipt-v1','snapshot_id':manifest['snapshot_id'],'restored_at':timestamp(),'schema_version':SCHEMA_VERSION,
        'checksums_verified':True,'database_integrity_verified':True,'row_counts_preserved':True,'sessions_revoked':True,
        'flight_records':restored['row_counts']['flights'],'active_model_restored':any(e['path']=='models/delay-v2/model.joblib' for e in manifest['files']),
        'knowledge_index_restored':any(e['path']=='knowledge/index.json' for e in manifest['files']),
        'elapsed_ms':round((time.monotonic()-started)*1000,2),'production_qualified':False}
    (destination/'recovery-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return receipt


def private_target(value):
    target=Path(value).resolve()
    if not target.is_relative_to((ROOT/'.local').resolve()) or target==(ROOT/'.local').resolve():raise ValueError('Recovery writes must use a new directory under .local')
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['backup','verify','restore']);parser.add_argument('--source');parser.add_argument('--destination')
    args=parser.parse_args()
    if args.action=='backup':result=backup(args.source or STATE,private_target(args.destination or ROOT/'.local/recovery/backups'/str(uuid4())))
    elif args.action=='verify':result=verify(args.source)
    else:result=restore(args.source,private_target(args.destination or ROOT/'.local/recovery/restores'/str(uuid4())))
    # Never print credentials, database contents or absolute personal paths.
    print(json.dumps(result if args.action=='restore' else {'format':result['format'],'snapshot_id':result['snapshot_id'],'verified':True,'files':len(result['files'])},indent=2))


if __name__=='__main__':main()
