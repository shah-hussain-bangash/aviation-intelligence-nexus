"""Isolated authenticated June queue rehearsal through the real loopback gateway/API."""
import argparse
import copy
from contextlib import ExitStack
from http.cookiejar import CookieJar
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
from threading import Thread
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler, HTTPCookieProcessor
from uuid import UUID, uuid4

import uvicorn
from agents import runtime
from agents.evaluate_june_agent import OBJECTIVE, write_new
from agents.june_evidence import required_quotes, valid_observation
from agents.quality import assess_report
from agents.runtime import Investigation
from pipelines.synthetic_ingestion import host, local
from pipelines.verify_import_safety import identity
from rag import ollama
from services.api.auth import COOKIE
from services.api.june_evaluation import load_june_evaluation
from services.api.main import create_app, initialize
from services.api.paths import ROOT

SOURCES=('agents/verify_june_http.py','scripts/dev.mjs','scripts/api-proxy.mjs',
         'scripts/runtime-config.mjs','services/api/main.py','services/api/auth.py',
         'agents/jobs.py','agents/runtime.py','agents/tools.py','agents/quality.py',
         'agents/june_evidence.py','rag/ollama.py','services/api/june_evaluation.py')


class Client:
    def __init__(self, port):
        self.base=f'http://127.0.0.1:{port}';self.csrf='';self.cookies=CookieJar()
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(self.cookies),ollama.NoRedirect())

    def request(self, path, body=None, *, extra=None, csrf=True):
        headers={'Accept':'application/json','Origin':self.base,**(extra or {})}
        if body is not None:
            headers['Content-Type']='application/json'
            if csrf and self.csrf:headers['X-CSRF-Token']=self.csrf
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:response=self.opener.open(req,timeout=10)
        except HTTPError as error:response=error
        with response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('oversized_rehearsal_response')
            kind=response.headers.get('Content-Type','')
            data=json.loads(raw) if 'application/json' in kind else None
            return response.status,data,{k.lower():v for k,v in response.headers.items()}

    def login(self, name, password):
        code,data,_=self.request('/api/v1/auth/login',{'username':name,'password':password},csrf=False)
        if code!=200:raise RuntimeError('temporary_account_login_failed')
        self.csrf=data['csrf_token']


def reserve(port):
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('unprivileged_port_required')
    sock=socket.socket()
    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    try:sock.bind(('127.0.0.1',port))
    except OSError:
        sock.close();raise ValueError('isolated_port_unavailable') from None
    return sock


def verify(output, *, live_ai=False, peer_withdrawal=False, web_port=18172, api_port=18173):
    host()
    if type(live_ai) is not bool or type(peer_withdrawal) is not bool or web_port==api_port:raise ValueError('explicit_mode_and_distinct_ports_required')
    if '..' in Path(output).parts:raise ValueError('fresh_private_rehearsal_required')
    output=local(output)
    if not output.is_relative_to(ROOT/'.local') or output==ROOT/'.local' or output.exists():raise ValueError('fresh_private_rehearsal_required')
    summary=load_june_evaluation();provenance=identity()
    sources=SOURCES+('agents/store.py','agents/review_access.py','agents/review_inbox.py','agents/withdrawal.py') if peer_withdrawal else SOURCES
    source_hashes={p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in sources}
    with ExitStack() as ports:
        api_socket=ports.enter_context(reserve(api_port));web_probe=ports.enter_context(reserve(web_port))
        output.mkdir(parents=True,exist_ok=False)
        env={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'}
        env.update(AIN_ENV='test',AIN_CONTAINER='0',AIN_AGENT_JOBS='1',AIN_MONITOR_ENABLED='0',
                   PORT=str(web_port),AIN_API_PORT=str(api_port),AIN_BIND_HOST='127.0.0.1',
                   AIN_API_HOST='127.0.0.1',AIN_OLLAMA_HOST='127.0.0.1',AIN_SESSION_COOKIE=COOKIE)
        result={'format':'ain-june-authenticated-http-v1','scope':'Real loopback Node gateway and Uvicorn API; temporary synthetic accounts; not an original-user browser journey or human usefulness assessment',
                **provenance,'execution_source_sha256':source_hashes,'provider_mode':'live_ollama' if live_ai else 'deterministic_fixture',
                'ports':{'web':web_port,'api':api_port},'recorded_june_report_sha256':summary['report_sha256'],
                'checks':{},'provider_calls':[],'run':None,'passed':False,'failure_type':None,
                'genuine_human_usefulness_assessed':False,'production_ready':False}
        if peer_withdrawal:
            result.update(format='ain-june-sharing-http-v1',
                sharing_scope='Explicit pending sharing with other local researchers; withdrawal ends future access, not previously received copies')
        checks=result['checks'];gateway=None;server=None;thread=None;worker=None;started=time.perf_counter()
        def check(name, ok):
            checks[name]=bool(ok)
            if not ok:raise RuntimeError('authenticated_rehearsal_check_failed')
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,env,clear=True))
            if live_ai:
                original=ollama.call
                def observed(route,payload=None,**kwargs):
                    event={'route':route,'purpose':'planner' if payload and 'tools' in payload else 'generator' if route=='chat' else 'inventory'}
                    result['provider_calls'].append(event)
                    try:
                        response=original(route,payload,**kwargs);event['state']='returned'
                        if route=='chat':event.update(done=response.get('done'),done_reason=response.get('done_reason'))
                        return response
                    except Exception as error:
                        event.update(state='failed',error_type=type(error).__name__);raise
                stack.enter_context(patch.object(ollama,'call',side_effect=observed))
            else:
                stack.enter_context(patch.object(ollama,'models',return_value={ollama.CHAT_MODEL:'e'*64}))
                stack.enter_context(patch.object(runtime,'select_tools',side_effect=[[{'function':{'name':'june_evidence','arguments':{}}}],[]]))
                def extracts(question,evidence,**kwargs):
                    row=evidence[0]
                    return {'claims':[{'text':q,'quote':q,'citation':row['id']} for q in required_quotes({'evidence_text':row['text']}).values()]}
                stack.enter_context(patch.object(ollama,'generate',side_effect=extracts))
            try:
                database=output/'checkpoints.sqlite3';initialize(database)
                app=create_app(database,model_directory=output/'absent-baseline',research_model_directory=output/'absent-model',knowledge_index=output/'absent-index')
                password=secrets.token_urlsafe(32)
                for name,role in [('admin','admin'),('owner','researcher'),('peer','researcher'),('viewer','viewer')]:
                    app.state.auth_store.create_user('june-http-'+name,password,role)
                worker=app.state.job_worker
                server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=api_port,log_level='error',access_log=False))
                thread=Thread(target=lambda:server.run(sockets=[api_socket]),daemon=True);thread.start()
                limit=time.monotonic()+15
                while not server.started and thread.is_alive() and time.monotonic()<limit:time.sleep(.05)
                check('isolated_api_started',server.started and thread.is_alive())
                web_probe.close()
                log=stack.enter_context((output/'gateway.log').open('wb'))
                gateway=subprocess.Popen(['node','scripts/dev.mjs'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                anonymous=Client(web_port);limit=time.monotonic()+15;ready=False
                while gateway.poll() is None and time.monotonic()<limit:
                    try:
                        code,data,_=anonymous.request('/__ain/health');ready=code==200 and data.get('service')=='ain-dashboard' and data.get('api_port')==api_port
                        if ready:break
                    except (OSError,ValueError):pass
                    time.sleep(.1)
                check('owned_gateway_and_api_ready',ready and anonymous.request('/__ain/ready')[0]==200)
                code,_,headers=anonymous.request('/')
                check('dashboard_security_headers',code==200 and bool(headers.get('content-security-policy')) and headers.get('x-content-type-options')=='nosniff')
                path='/api/v1/research/agent-jobs';request=Investigation(objective=OBJECTIVE,include_june_evidence=True,required_tools=['june_evidence']).model_dump()
                if peer_withdrawal:request['require_peer_review']=True
                check('anonymous_denied',anonymous.request('/api/v1/research/june-evaluation')[0]==401 and anonymous.request(path,request,extra={'Idempotency-Key':str(uuid4())})[0]==401)
                viewer=Client(web_port);viewer.login('june-http-viewer',password)
                check('viewer_submission_denied',viewer.request(path,request,extra={'Idempotency-Key':str(uuid4())})[0]==403)
                owner=Client(web_port);owner.login('june-http-owner',password)
                check('csrf_enforced',owner.request(path,request,extra={'Idempotency-Key':str(uuid4())},csrf=False)[0]==403)
                check('origin_enforced',owner.request(path,request,extra={'Idempotency-Key':str(uuid4()),'Origin':'http://unapproved.invalid'})[0]==403)
                check('researcher_operations_denied',owner.request('/api/v1/research/agent-operations')[0]==403)
                code,status,_=owner.request('/api/v1/research/agent-status')
                check('worker_and_provider_available',code==200 and status['available'] and status['background_worker']['alive'])
                key=str(uuid4());code,queued,_=owner.request(path,request,extra={'Idempotency-Key':key})
                check('authenticated_enqueue',code==202 and queued['execution']=='local-background-queue-v1')
                run=None;limit=time.monotonic()+160
                while time.monotonic()<limit:
                    code,run,headers=owner.request(path+'/'+queued['run_id'])
                    if code!=200:break
                    if run['state'] not in ('queued','running'):break
                    time.sleep(.2)
                result['run']=run
                check('owned_completed_draft',code==200 and run['state']=='awaiting_review' and run['execution']=='local-background-queue-v1')
                check('authenticated_response_headers',headers.get('cache-control')=='no-store' and UUID(headers['x-request-id']).version==4)
                check('canonical_june_tool_and_coverage',len(run['steps'])==1 and run['steps'][0]['tool']=='june_evidence' and valid_observation(run['steps'][0].get('observation')) and assess_report(run)['passed'])
                check('unreviewed_research_only',not run['reviews'] and run['operational_approval'] is False)
                model=run.get('model',{});digest=model.get('digest')
                check('model_identity_recorded',model.get('name')==ollama.CHAT_MODEL and isinstance(digest,str) and bool(re.fullmatch('[a-f0-9]{64}',digest)))
                calls=len(result['provider_calls']);code,replay,_=owner.request(path,request,extra={'Idempotency-Key':key})
                check('same_key_replay_without_provider_calls',code==202 and replay.get('replayed') is True and replay['run_id']==run['run_id'] and replay['report_sha256']==run['report_sha256'] and len(result['provider_calls'])==calls)
                peer=Client(web_port);peer.login('june-http-peer',password)
                if peer_withdrawal:
                    read=path+'/'+run['run_id'];inbox='/api/v1/research/agent-review-inbox'
                    code,shared,_=peer.request(read)
                    check('explicit_peer_draft_visible',code==200 and shared['report_sha256']==run['report_sha256'] and shared['review_access']['can_review'] is True)
                    code,pending,_=peer.request(inbox)
                    check('peer_inbox_lists_exact_draft',code==200 and [r['run_id'] for r in pending['runs']]==[run['run_id']])
                    check('author_cannot_self_review',run['review_access']['can_review'] is False and run['review_access']['can_withdraw'] is True)
                    check('viewer_shared_draft_denied',viewer.request(read)[0]==404 and viewer.request(inbox)[0]==403)
                    body={'run_id':run['run_id'],'report_sha256':run['report_sha256'],'withdrawal_key':str(uuid4()),
                          'note':'SYNTHETIC access rehearsal: end temporary sharing without submitting a review.','acknowledged':True}
                    withdraw='/api/v1/research/agent-withdraw-sharing'
                    check('peer_cannot_withdraw',peer.request(withdraw,body)[0]==404)
                    check('withdrawal_csrf_enforced',owner.request(withdraw,body,csrf=False)[0]==403)
                    check('withdrawal_origin_enforced',owner.request(withdraw,body,extra={'Origin':'http://unapproved.invalid'})[0]==403)
                    code,closed,_=owner.request(withdraw,body)
                    check('owner_withdrawal_retained',code==200 and closed['state']=='withdrawn' and closed['reviews']==[])
                    check('withdrawal_preserves_evidence',all(closed[k]==run[k] for k in ('request','steps','claims','report_sha256','reviews')))
                    code,repeated,_=owner.request(withdraw,body)
                    check('withdrawal_idempotent',code==200 and repeated['withdrawal_replayed'] is True and repeated['sharing_withdrawal']==closed['sharing_withdrawal'])
                    check('changed_withdrawal_conflicts',owner.request(withdraw,{**body,'note':'SYNTHETIC different reason.'})[0]==409)
                    code,empty,_=peer.request(inbox)
                    check('peer_access_ends_after_withdrawal',peer.request(read)[0]==404 and code==200 and empty['runs']==[])
                    check('viewer_access_stays_denied',viewer.request(read)[0]==404)
                    result['withdrawn_run']=closed
                else:
                    check('cross_owner_read_denied',peer.request(path+'/'+run['run_id'])[0]==404 and viewer.request(path+'/'+run['run_id'])[0]==404)
                admin=Client(web_port);admin.login('june-http-admin',password)
                code,operations,_=admin.request('/api/v1/research/agent-operations')
                check('admin_named_execution_observed',code==200 and operations['total_background_runs']==1 and operations['recent_window']['tools']['june_evidence']['completed']==1)
                stale=Client(web_port)
                for cookie in owner.cookies:stale.cookies.set_cookie(copy.copy(cookie))
                check('logout_revokes_access',owner.request('/api/v1/auth/logout',{})[0]==200 and owner.request(path+'/'+run['run_id'])[0]==401 and stale.request(path+'/'+run['run_id'])[0]==401)
                owner.login('june-http-owner',password);code,saved,_=owner.request(path+'/'+run['run_id'])
                check('fresh_session_reads_same_saved_draft',code==200 and saved['report_sha256']==run['report_sha256'] and saved['reviews']==[])
                if peer_withdrawal:check('withdrawal_survives_fresh_session',saved['state']=='withdrawn' and saved['sharing_withdrawal']==result['withdrawn_run']['sharing_withdrawal'])
                if live_ai:
                    chats=[e for e in result['provider_calls'] if e['route']=='chat']
                    check('actual_provider_completed_within_bounds',{'planner','generator'}.issubset({e['purpose'] for e in chats}) and all(e.get('done') is True and e.get('done_reason')=='stop' for e in chats) and sum(e['purpose']=='planner' for e in chats)<=3 and sum(e['purpose']=='generator' for e in chats)<=2)
            except Exception as error:
                result['failure_type']=type(error).__name__
            finally:
                if gateway is not None:
                    if gateway.poll() is None:gateway.terminate()
                    try:gateway.wait(timeout=5)
                    except subprocess.TimeoutExpired:gateway.kill();gateway.wait(timeout=5)
                if server is not None:server.should_exit=True
                if thread is not None:thread.join(timeout=50)
                checks['isolated_services_stopped']=(gateway is None or gateway.poll() is not None) and (thread is None or not thread.is_alive()) and (worker is None or worker.task is None or worker.task.done())
        try:checks['execution_source_unchanged']=all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==value for p,value in source_hashes.items())
        except OSError:checks['execution_source_unchanged']=False
        result.update(passed=result['failure_type'] is None and all(checks.values()),elapsed_ms=round((time.perf_counter()-started)*1000,2))
        write_new(output/'evaluation.json',result)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--live-ai',action='store_true');parser.add_argument('--peer-withdrawal',action='store_true');parser.add_argument('--web-port',type=int,default=18172);parser.add_argument('--api-port',type=int,default=18173)
    args=parser.parse_args();r=verify(args.output,live_ai=args.live_ai,peer_withdrawal=args.peer_withdrawal,web_port=args.web_port,api_port=args.api_port)
    print(json.dumps({k:r[k] for k in ('passed','provider_mode','checks','failure_type','elapsed_ms')},indent=2));return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
