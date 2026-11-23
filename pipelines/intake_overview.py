"""Export a bounded, deduplicated, unsigned intake snapshot without importing data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid
from pipelines.verify_intake import verify_run
from services.api.intake_overview import validate, digest
from services.api.paths import ROOT


def collect(directory, clock=time.monotonic):
    start = clock(); runs=[]
    directory=Path(directory)
    if directory.is_symlink() or not directory.is_dir(): raise ValueError('Missing intake directory')
    for disposition in ('accepted','quarantined'):
        folder=directory/disposition
        if folder.is_symlink(): raise ValueError('Invalid intake directory')
        if not folder.exists(): continue
        for run in folder.iterdir():
            runs.append(run)
            if len(runs)>1000: raise ValueError('Intake run limit exceeded')
    accepted={}; quarantined=unverifiable=0; reasons={}
    for run in sorted(runs):
        if clock()-start>120: raise ValueError('Intake overview budget exceeded')
        try: result=verify_run(run)
        except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
            unverifiable+=1; continue
        if result['disposition']=='quarantined':
            quarantined+=1; reason=result['reason_code']; reasons[reason]=reasons.get(reason,0)+1; continue
        row={'period':result['declared_period'],'sha256':result['archive_sha256'],'bytes':result['archive_size_bytes'],'declared_rows':result['declared_rows_read'],'runs':1}
        previous=accepted.get(row['sha256'])
        if previous:
            if any(previous[k]!=row[k] for k in ('period','bytes','declared_rows')): raise ValueError('Contradictory receipts for archive')
            previous['runs']+=1
        else: accepted[row['sha256']]=row
    if clock()-start>120: raise ValueError('Intake overview budget exceeded')
    rows=sorted(accepted.values(),key=lambda row:(row['period'],row['sha256']))
    count=sum(row['runs'] for row in rows)
    return validate({'format':'ain-intake-overview-v1','checked_at':datetime.now(timezone.utc).isoformat(),
        'runs_checked':len(runs),'accepted_runs':count,'quarantined_runs':quarantined,'unverifiable_runs':unverifiable,
        'unique_archives':len(rows),'repeated_accepted_runs':count-len(rows),'declared_rows':sum(row['declared_rows'] for row in rows),
        'archives':rows,'quarantine_reasons':reasons,'receipt_authenticated':False,'rows_rescanned':False,
        'import_authorized':False,'import_performed':False,'production_ready':False})


def export(root=ROOT):
    root=Path(root); payload=collect(root/'.local/intake')
    folder=root/'.local/intake-dashboard'
    if folder.is_symlink(): raise ValueError('Invalid snapshot directory')
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/'snapshot.json'
    if target.is_symlink(): raise ValueError('Invalid snapshot file')
    if target.exists():
        if not target.is_file() or target.stat().st_size>256_000: raise ValueError('Invalid previous snapshot')
        with (folder/('previous-'+uuid.uuid4().hex+'.json')).open('xb') as history: history.write(target.read_bytes())
    temporary=folder/('pending-'+uuid.uuid4().hex+'.json')
    with temporary.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump({'payload':payload,'payload_sha256':digest(payload)},stream,indent=2); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,target)
    return payload


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try: payload=export()
    except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
        print(json.dumps({'exported':False,'error':'intake_overview_unavailable','production_ready':False})); raise SystemExit(2)
    print(json.dumps({'exported':True,**payload},indent=2))


if __name__=='__main__': main()
