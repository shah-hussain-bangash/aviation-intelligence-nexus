"""Read-only checks of this project's local containers and unauthenticated health."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen
from services.api.paths import ROOT


def compose(project,*arguments):
    if not re.fullmatch(r'ain-[a-z0-9-]{1,40}',project):raise ValueError('Use an explicitly named AIN project')
    return subprocess.check_output(['docker','compose','-p',project,*arguments],cwd=ROOT,text=True)


def verify(project='ain-local-release',port=8090):
    if not 1<=port<=65535:raise ValueError('Invalid loopback port')
    checks={};images={}
    for service in ('api','web'):
        identifier=compose(project,'ps','-q',service).strip()
        if not identifier:raise RuntimeError('Required local service is not running')
        container=json.loads(subprocess.check_output(['docker','inspect',identifier],text=True))[0]
        config,host=container['Config'],container['HostConfig']
        checks[service+'_healthy']=container['State'].get('Health',{}).get('Status')=='healthy'
        checks[service+'_non_root']=bool(config.get('User')) and config['User'].split(':')[0] not in ('0','root')
        checks[service+'_read_only_root']=host.get('ReadonlyRootfs') is True
        checks[service+'_capabilities_dropped']='ALL' in host.get('CapDrop',[])
        checks[service+'_not_privileged']=host.get('Privileged') is False
        checks[service+'_no_privilege_escalation']='no-new-privileges:true' in host.get('SecurityOpt',[])
        bindings=host.get('PortBindings') or {}
        checks[service+'_port_scope']=not bindings if service=='api' else bool(bindings) and all(binding.get('HostIp')=='127.0.0.1' for values in bindings.values() for binding in values)
        images[service]={'image_id':container['Image'],'source_revision':config.get('Labels',{}).get('org.opencontainers.image.revision','unrecorded')}
    base=f'http://127.0.0.1:{port}'
    with urlopen(base+'/__ain/ready',timeout=5) as response:readiness=json.load(response)
    checks['database_backed_readiness']=readiness.get('backend_ready') is True and readiness.get('production_ready') is False
    with urlopen(base+'/api/v1/auth/session',timeout=5) as response:session=json.load(response)
    checks['unauthenticated_access_not_granted']=session.get('authenticated') is False and session.get('user') is None
    return {'scope':'Local container smoke and isolation checks, not production qualification','project':project,'checks':checks,
        'passed':all(checks.values()),'images':images,'production_ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',default='ain-local-release');parser.add_argument('--port',type=int,default=8090);parser.add_argument('--output')
    args=parser.parse_args();result=verify(args.project,args.port)
    if args.output:
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
