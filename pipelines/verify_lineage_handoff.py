"""One-command, isolated research verification. No socket server, import or deployment."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from uuid import uuid4
from infra.recovery import private_target
from pipelines.intake_bts import intake
from pipelines.verify_intake import verify_run
from pipelines.batch_lineage import export
from services.api.paths import ROOT


def require(condition):
    if not condition: raise ValueError('Lineage handoff verification failed')


def provenance():
    paths=('pipelines/verify_lineage_handoff.py','pipelines/intake_bts.py','pipelines/verify_intake.py',
           'pipelines/batch_lineage.py','services/api/batch_lineage.py','services/api/main.py')
    result={'source_sha256':{p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in paths}}
    env=dict(os.environ)
    def quote(value): return "'"+value.replace("'","'\\''")+"'"
    n=int(env.get('GIT_CONFIG_COUNT','0'))
    pairs=[quote(env.pop(f'GIT_CONFIG_KEY_{i}')+'='+env.pop(f'GIT_CONFIG_VALUE_{i}')) for i in range(n)]
    if n:
        env['GIT_CONFIG_PARAMETERS']=(env.get('GIT_CONFIG_PARAMETERS','')+' '+' '.join(pairs)).strip()
        env['GIT_CONFIG_COUNT']='0'
    try:
        command=['git','-c','safe.directory='+ROOT.as_posix()]
        result['source_revision']=subprocess.check_output([*command,'rev-parse','HEAD'],cwd=ROOT,env=env,stderr=subprocess.DEVNULL,text=True,timeout=10).strip()
        result['working_tree_changes']=bool(subprocess.check_output([*command,'status','--porcelain'],cwd=ROOT,env=env,stderr=subprocess.DEVNULL,text=True,timeout=10).strip())
    except (OSError,subprocess.SubprocessError):
        result.update(source_revision=None,working_tree_changes=None)
    return result


def verify(archive, directory):
    # This host-only command must not start runtime workers or consume container mounts.
    require(all(os.environ.get(k)!='1' for k in ('AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_INTAKE_OVERVIEW_MOUNTED','AIN_CONTAINER')))
    directory=private_target(directory);directory.mkdir(parents=True,exist_ok=False)
    stage='preflight'
    with (directory/'started.json').open('x',encoding='utf-8') as stream:
        json.dump({'format':'ain-lineage-handoff-started-v1','research_only':True,'checked_at':datetime.now(timezone.utc).isoformat()},stream)
    try:
        receipt=intake(Path(archive),directory/'intake',2025,1)
        require(receipt['disposition']=='accepted')
        run=directory/'intake/accepted'/receipt['run_id']
        stage='receipt_verification';verification=verify_run(run)
        stage='export';expected=export(run,directory/'state')
        stage='api_role_checks'
        from fastapi.testclient import TestClient
        from services.api.main import create_app
        state=directory/'state'
        app=create_app(state/'ain.sqlite3',model_directory=state/'unconfigured-baseline',
            research_model_directory=state/'unconfigured-model',knowledge_index=state/'unconfigured-index.json')
        route='/api/v1/research/batch-lineage';checks={}
        headers={'Origin':'http://127.0.0.1:'+os.environ.get('PORT','8080')}
        password=secrets.token_urlsafe(32)
        with TestClient(app) as client:
            checks['anonymous_denied']=client.get(route).status_code==401
            for role in ('admin','researcher','viewer'):
                username='lineage-fixture-'+role
                app.state.auth_store.create_user(username,password,role)
                require(client.post('/api/v1/auth/login',json={'username':username,'password':password},headers=headers).status_code==200)
                response=client.get(route);require(response.status_code==200)
                data=response.json()
                require(data['dataset']==expected['dataset'] and data['intake']==expected['intake'])
                checks[role+'_projection']=('admin_receipt' in data)==(role=='admin')
                checks[role+'_query_denied']=client.get(route+'?path=private').status_code==422
                if role!='admin':checks[role+'_intake_overview_denied']=client.get('/api/v1/research/intake-overview').status_code==403
            checks['write_denied']=client.post(route,json={},headers=headers).status_code in (403,405)
            path=state/'intake-dashboard/batch-lineage.json';retained=path.with_name('batch-lineage.retained.json')
            path.rename(retained)
            try:checks['missing_metadata_unavailable']=client.get(route).status_code==503
            finally:retained.rename(path)
            require(all(checks.values()))
        report={'format':'ain-lineage-handoff-v1','passed':True,'checked_at':datetime.now(timezone.utc).isoformat(),
            'verification_id':directory.name if re.fullmatch('[0-9a-f]{32}',directory.name) else None,
            **provenance(),'sample_scope':'historical US research archive identity; disposable synthetic accounts',
            'dataset':expected['dataset'],'intake':expected['intake'],'verification':verification,'checks':checks,
            'original_import_receipt':False,'primary_database_accessed':False,'import_performed':False,
            'deployment_performed':False,'production_ready':False}
        with (directory/'result.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
        return report
    except Exception as error:
        with (directory/'failure.json').open('x',encoding='utf-8') as stream:
            json.dump({'passed':False,'stage':stage,'error':'lineage_handoff_failed','production_ready':False},stream)
        raise ValueError('Lineage handoff verification failed') from error


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path)
    parser.add_argument('--directory',type=Path,default=ROOT/'.local/lineage-handoff'/uuid4().hex)
    args=parser.parse_args()
    try:result=verify(args.archive,args.directory)
    except (OSError,ValueError,TypeError,KeyError,OverflowError,RecursionError,ImportError):
        print(json.dumps({'passed':False,'error':'lineage_handoff_failed','production_ready':False}));raise SystemExit(2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
