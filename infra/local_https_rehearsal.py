"""Isolated HTTPS gateway/API authentication with synthetic accounts and explicit client trust."""
import argparse
from contextlib import ExitStack
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time
from urllib.request import build_opener, HTTPSHandler, HTTPCookieProcessor, ProxyHandler, Request
from uuid import uuid4

from agents.verify_june_http import Client, reserve
from infra.local_tls import CERT, KEY, create
from pipelines.synthetic_ingestion import host, local
from pipelines.verify_import_safety import identity
from rag.ollama import NoRedirect
from services.api.auth import AuthStore
from services.api.main import initialize
from services.api.paths import ROOT


def verify(output, *, encrypted_api=False, web_port=18176, api_port=18177):
    host();output=Path(output)
    if type(encrypted_api) is not bool or '..' in output.parts or web_port==api_port:raise ValueError('fresh_private_https_rehearsal_required')
    output=local(output)
    if output==ROOT/'.local' or not output.is_relative_to(ROOT/'.local') or output.exists():raise ValueError('fresh_private_https_rehearsal_required')
    with ExitStack() as stack:
        api_probe=stack.enter_context(reserve(api_port));web_probe=stack.enter_context(reserve(web_port))
        output.mkdir(parents=True,exist_ok=False);bundle=output/'tls';material=create(bundle)
        state=output/'state';state.mkdir();database=state/'ain.sqlite3';initialize(database)
        password=secrets.token_urlsafe(32);auth=AuthStore(database)
        auth.create_user('https-fixture-admin',password,'admin');auth.create_user('https-fixture-viewer',password,'viewer')
        env={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'}
        env.update(AIN_ENV='test',AIN_CONTAINER='0',AIN_SESSION_COOKIE='ain_test_session',
            AIN_AGENT_JOBS='0',AIN_MONITOR_ENABLED='0',AIN_LOCAL_HTTPS='1',AIN_LOCAL_API_HTTPS='1' if encrypted_api else '0',
            AIN_LOCAL_TLS_DIRECTORY=str(bundle),AIN_LOCAL_TLS_SHA256=material['certificate_sha256'],
            AIN_STATE_ROOT=str(state),AIN_DB_PATH=str(database),AIN_BIND_HOST='127.0.0.1',AIN_API_HOST='127.0.0.1',
            PORT=str(web_port),AIN_API_PORT=str(api_port),OMP_NUM_THREADS='2')
        result={'format':'ain-local-https-rehearsal-v1',**identity(),'scope':'Loopback HTTPS gateway with plaintext loopback API; synthetic accounts; no original-user browser or deployment',
            'checks':{},'passed':False,'failure_type':None,'production_ready':False}
        result['backend_transport']='verified_https_loopback' if encrypted_api else 'plaintext_loopback'
        if encrypted_api:result.update(format='ain-local-https-api-rehearsal-v1',scope='Verified HTTPS gateway and loopback API; synthetic accounts; no original-user browser, mutual TLS or deployment')
        checks=result['checks'];api=None;gateway=None
        context=ssl.create_default_context(cafile=str(bundle/CERT))
        def client(port=web_port,trust=context):
            value=Client(port);value.base=f'https://127.0.0.1:{port}'
            value.opener=build_opener(ProxyHandler({}),HTTPSHandler(context=trust),HTTPCookieProcessor(value.cookies),NoRedirect())
            return value
        def check(name,condition):
            checks[name]=bool(condition)
            if not condition:raise RuntimeError('local_https_check_failed')
        try:
            api_log=stack.enter_context((output/'api.log').open('wb'));web_log=stack.enter_context((output/'gateway.log').open('wb'))
            def launch_api(tls_bundle):
                command=[sys.executable,'-m','uvicorn','services.api.main:app','--host','127.0.0.1','--port',str(api_port),'--no-access-log','--log-level','error']
                if encrypted_api:command+=['--ssl-certfile',str(tls_bundle/CERT),'--ssl-keyfile',str(tls_bundle/KEY)]
                return subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=api_log,stderr=subprocess.STDOUT)
            api_probe.close()
            api=launch_api(bundle)
            web_probe.close()
            gateway=subprocess.Popen(['node','scripts/dev.mjs'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=web_log,stderr=subprocess.STDOUT)
            anonymous=client();ready=False;limit=time.monotonic()+40
            while api.poll() is None and gateway.poll() is None and time.monotonic()<limit:
                try:
                    code,data,_=anonymous.request('/__ain/ready');ready=code==200 and data.get('backend_ready') is True
                    if ready:break
                except (OSError,ValueError):pass
                time.sleep(.1)
            check('owned_https_gateway_and_api_ready',ready and api.poll() is None and gateway.poll() is None)
            with socket.create_connection(('127.0.0.1',web_port),timeout=3) as connection:
                with context.wrap_socket(connection,server_hostname='127.0.0.1') as secured:
                    check('served_certificate_matches_pin',hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest()==material['certificate_sha256'])
                    check('tls_version_at_least_12',secured.version() in ('TLSv1.2','TLSv1.3'))
            untrusted=False
            try:
                with socket.create_connection(('127.0.0.1',web_port),timeout=3) as connection:
                    with ssl.create_default_context().wrap_socket(connection,server_hostname='127.0.0.1'):pass
            except ssl.SSLCertVerificationError:untrusted=True
            check('untrusted_certificate_rejected',untrusted)
            code,_,headers=anonymous.request('/')
            check('dashboard_security_headers',code==200 and headers.get('x-content-type-options')=='nosniff' and bool(headers.get('content-security-policy')))
            protected='/api/v1/research/june-evaluation'
            check('anonymous_research_denied',anonymous.request(protected)[0]==401)
            owner=client();owner.login('https-fixture-admin',password)
            cookies=list(owner.cookies)
            check('secure_test_cookie_only',len(cookies)==1 and cookies[0].name=='ain_test_session' and cookies[0].secure and cookies[0].path=='/api')
            check('httponly_samesite_cookie',cookies[0].has_nonstandard_attr('HttpOnly') and cookies[0].get_nonstandard_attr('SameSite','').lower()=='strict')
            plain=Request(f'http://127.0.0.1:{api_port}/api/v1/auth/session');owner.cookies.add_cookie_header(plain)
            check('secure_cookie_not_sent_over_http',plain.get_header('Cookie') is None)
            code,session,_=owner.request('/api/v1/auth/session')
            check('https_session_authenticated',code==200 and session['authenticated'] and session['user']['username']=='https-fixture-admin')
            code,_,headers=owner.request(protected)
            check('https_authenticated_research_read',code==200 and headers.get('cache-control')=='no-store')
            logout='/api/v1/auth/logout'
            check('csrf_required',owner.request(logout,{},csrf=False)[0]==403)
            check('http_origin_rejected',owner.request(logout,{},extra={'Origin':f'http://127.0.0.1:{web_port}'})[0]==403)
            check('api_port_origin_rejected',owner.request(logout,{},extra={'Origin':f'https://127.0.0.1:{api_port}'})[0]==403)
            check('foreign_origin_rejected',owner.request(logout,{},extra={'Origin':'https://outside.invalid'})[0]==403)
            viewer=client();viewer.login('https-fixture-viewer',password)
            check('viewer_mutation_denied',viewer.request('/api/v1/research/agent-jobs',{'objective':'SYNTHETIC forbidden job'},extra={'Idempotency-Key':str(uuid4())})[0]==403)
            stale=client();stale.cookies.set_cookie(cookies[0])
            code,_,headers=owner.request(logout,{})
            check('logout_clears_secure_cookie',code==200 and 'secure' in headers.get('set-cookie','').lower())
            check('logout_revokes_old_cookie',owner.request(protected)[0]==401 and stale.request(protected)[0]==401)
            cleartext=False;plain_client=http.client.HTTPConnection('127.0.0.1',web_port,timeout=3)
            try:
                plain_client.request('GET','/__ain/health');cleartext=plain_client.getresponse().status!=200
            except (OSError,http.client.HTTPException):cleartext=True
            finally:plain_client.close()
            check('http_not_served_on_https_port',cleartext)
            if encrypted_api:
                with socket.create_connection(('127.0.0.1',api_port),timeout=3) as connection:
                    with context.wrap_socket(connection,server_hostname='127.0.0.1') as secured:
                        check('backend_certificate_matches_pin',hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest()==material['certificate_sha256'])
                probe="""import fs from 'node:fs';import path from 'node:path';import {fetchApi} from './scripts/api-transport.mjs';
const c={apiHost:'127.0.0.1',sessionCookie:'ain_test_session',profile:'test',container:false,localHttps:true,localApiHttps:true,tlsPin:'0'.repeat(64),backendTlsCertificate:fs.readFileSync(path.join(process.env.AIN_LOCAL_TLS_DIRECTORY,'certificate.pem'))};
try{await fetchApi('/health/ready',Number(process.env.AIN_API_PORT),c,{signal:AbortSignal.timeout(3000)});process.exitCode=1;}
catch(error){const expected=error.message==='Local API certificate rejected.';process.stdout.write(expected?'pinned-rejection':'other-failure');process.exitCode=expected?0:2;}"""
                pinned=subprocess.run(['node','--input-type=module','-e',probe],cwd=ROOT,env=env,capture_output=True,text=True,timeout=10)
                check('trusted_certificate_with_wrong_pin_rejected',pinned.returncode==0 and pinned.stdout=='pinned-rejection')
                api.terminate();api.wait(timeout=10)
                unexpected=output/'unexpected-api-tls';create(unexpected)
                api=launch_api(unexpected)
                direct=client(api_port,ssl.create_default_context(cafile=str(unexpected/CERT)))
                healthy=False;limit=time.monotonic()+40
                while api.poll() is None and time.monotonic()<limit:
                    try:
                        healthy=direct.request('/health/ready')[0]==200
                        if healthy:break
                    except (OSError,ValueError):pass
                    time.sleep(.1)
                check('unexpected_certificate_backend_is_running',healthy)
                check('unexpected_certificate_blocks_readiness',anonymous.request('/__ain/ready')[0]==503)
                check('unexpected_certificate_blocks_proxy',anonymous.request(protected)[0]==503)
                check('frontend_stays_live_during_certificate_failure',anonymous.request('/')[0]==200)
                api.terminate();api.wait(timeout=10);api=launch_api(bundle)
                recovered=False;limit=time.monotonic()+40
                while api.poll() is None and time.monotonic()<limit:
                    try:
                        recovered=anonymous.request('/__ain/ready')[0]==200
                        if recovered:break
                    except (OSError,ValueError):pass
                    time.sleep(.1)
                check('trusted_backend_certificate_recovers_readiness',recovered)
                owner.login('https-fixture-admin',password)
                check('authenticated_https_read_recovers',owner.request(protected)[0]==200)
        except Exception as error:result['failure_type']=type(error).__name__
        finally:
            for process in (gateway,api):
                if process is not None:
                    if process.poll() is None:process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            checks['owned_services_stopped']=all(p is None or p.poll() is not None for p in (gateway,api))
        result['passed']=result['failure_type'] is None and all(checks.values())
        with (output/'evaluation.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--web-port',type=int,default=18176);parser.add_argument('--api-port',type=int,default=18177)
    parser.add_argument('--encrypted-api',action='store_true')
    args=parser.parse_args();result=verify(args.output,encrypted_api=args.encrypted_api,web_port=args.web_port,api_port=args.api_port)
    print(json.dumps({k:result[k] for k in ('passed','checks','failure_type')},indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
