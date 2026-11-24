"""Export one verified January receipt identity to an explicitly selected private research state."""
import argparse
import hashlib
import json
from pathlib import Path
from infra.recovery import private_target
from pipelines.verify_intake import verify_run
from services.api.batch_lineage import project
from services.api.data_quality import REPORT_SHA256


def export(run, state):
    run=private_target(run); state=private_target(state)
    checked=verify_run(run)
    text=(run/'receipt.json').read_bytes().decode('utf-8')
    envelope={'format':'ain-batch-lineage-v1','receipt_text':text,
        'receipt_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'dataset_report_sha256':REPORT_SHA256}
    result=project(envelope,'admin')
    require_keys=('run_id','archive_sha256','declared_period','rows_read')
    r=result['admin_receipt']
    expected={'run_id':checked['run_id'],'archive_sha256':checked['archive_sha256'],
        'declared_period':checked['declared_period'],'rows_read':checked['declared_rows_read']}
    if any(r[k]!=expected[k] for k in require_keys): raise ValueError('Receipt changed during verification')
    folder=state/'intake-dashboard'
    if folder.is_symlink(): raise ValueError('Invalid evidence folder')
    folder.mkdir(parents=True,exist_ok=True)
    # Never replace a prior lineage record. Select a new research state for another run.
    with (folder/'batch-lineage.json').open('x',encoding='utf-8',newline='\n') as stream: json.dump(envelope,stream,indent=2)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path);parser.add_argument('--state',type=Path,required=True)
    args=parser.parse_args()
    try: result=export(args.run,args.state)
    except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError):
        print(json.dumps({'exported':False,'error':'batch_lineage_unavailable'}));raise SystemExit(2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
