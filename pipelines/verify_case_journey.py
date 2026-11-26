"""Disposable API rehearsal with deterministic or explicit live local AI execution."""
import argparse
from contextlib import closing, ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from agents.distribution_evidence import observation, LIMIT
from agents.jobs import JobQueue
from agents.quality import assess_report
from agents.store import AgentStore, sha
from agents.tools import gate_sample
from rag import ollama,index as knowledge_index
from rag.service import Knowledge,validate_claims
from agents import runtime, tools
from pipelines.synthetic_ingestion import host, local
from pipelines.verify_import_safety import identity
from rag.history import EvidenceHistory
from services.api.history import ResearchHistory
from services.api.main import create_app, initialize
from services.api.paths import ROOT
from services.api.research_cases import ResearchCaseService, digest
from services.api.case_jobs import CaseJobs

SOURCES=('pipelines/verify_case_journey.py','services/api/research_cases.py',
         'services/api/case_jobs.py','services/api/case_agents.py','services/api/case_gates.py',
         'agents/jobs.py','agents/store.py','agents/distribution_evidence.py',
         'agents/runtime.py','agents/tools.py','agents/quality.py','rag/ollama.py',
         'rag/index.py','rag/service.py','rag/history.py')
BASE='/api/v1/research/cases'
ORIGIN={'Origin':'http://localhost:8080'}


def wait_for_job(queue,owner,run_id,worker,*,timeout=150):
    """Read bounded local checkpoints; never enqueue, claim, retry or fabricate a report."""
    deadline=time.monotonic()+timeout
    while True:
        saved=queue.get(owner,run_id)
        if saved['state'] not in ('queued','running'):return saved
        if not worker.task or worker.task.done() or worker.last_error:
            raise RuntimeError('journey_check_failed:live_worker_unavailable')
        if time.monotonic()>=deadline:raise RuntimeError('journey_check_failed:live_worker_deadline')
        time.sleep(.25)


def validate_live_qa(saved,index_path,expected_models):
    """Check frozen retrieval/quote consistency, not semantic entailment or usefulness."""
    pin,payload,*_=Knowledge(index_path).load()
    def require(ok):
        if not ok:raise RuntimeError('journey_check_failed:live_qa_binding')
    require(saved.get('mode')=='generated' and saved.get('index_sha256')==pin
        and saved.get('research_only') is True and saved.get('operational_approval') is False)
    generation=saved.get('generation',{})
    require(generation.get('requested') is True and generation.get('status')=='completed'
        and generation.get('model')==ollama.CHAT_MODEL
        and generation.get('answer_style')=='verbatim_source_extracts'
        and generation.get('model_digest')==expected_models.get(ollama.CHAT_MODEL)
        and payload['embedding_digest']==expected_models.get(ollama.EMBED_MODEL))
    evidence=saved.get('evidence');claims=saved.get('claims')
    require(isinstance(evidence,list) and 1<=len(evidence)<=3 and isinstance(claims,list) and 1<=len(claims)<=3)
    chunks={c['id']:c for c in payload['chunks']};sources={s['path']:s['sha256'] for s in payload['sources']}
    for e in evidence:
        c=chunks.get(e.get('id'))
        require(c is not None and all(e.get(k)==c[k] for k in ('source','heading','start_line','end_line','text'))
            and e.get('source_sha256')==sources[c['source']]
            and e.get('source_url')=='https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/'+payload['revision']+'/'+c['source']+'#L'+str(c['start_line']))
    validate_claims({'claims':claims},evidence)
    require(all(c['text']==c['quote'] for c in claims))
    return {'index_sha256':pin,'index_file_sha256':hashlib.sha256(Path(index_path).read_bytes()).hexdigest(),
        'embedding_model':payload['embedding_model'],'embedding_digest':payload['embedding_digest'],
        'generation_model':generation['model'],'generation_digest':generation['model_digest'],'answer_style':generation['answer_style'],
        'sources':payload['sources'],'retrieved_ids':[e['id'] for e in evidence],
        'saved_run_id':saved['run_id'],'snapshot_sha256':digest(saved),'claim_count':len(claims),
        'semantic_usefulness_assessed':False}


def exercise(directory,*,live_ai=False,live_rag=False):
    """Create only a new isolated fixture. Existing directories are never adopted."""
    if type(live_ai) is not bool:raise ValueError('explicit_live_ai_boolean_required')
    if type(live_rag) is not bool:raise ValueError('explicit_live_rag_boolean_required')
    if live_rag and not live_ai:raise ValueError('live_rag_requires_live_ai')
    host();directory=local(directory);directory.mkdir(parents=True,exist_ok=False)
    private_index=directory/'knowledge/index.json';index_calls=0
    if live_rag:
        installed=ollama.models()
        if not all(name in installed for name in (ollama.EMBED_MODEL,ollama.CHAT_MODEL)):
            raise RuntimeError('journey_check_failed:local_rag_models_unavailable')
        with patch.object(ollama,'embed',wraps=ollama.embed) as embedded:
            knowledge_index.build(destination=private_index)
            index_calls=embedded.call_count
    database=directory/'ain.sqlite3';sidecar=directory/'research-cases.sqlite3'
    initialize(database);cases=ResearchCaseService(database,sidecar)
    app=create_app(database,research_cases=cases,knowledge_index=private_index);password=secrets.token_urlsafe(32)
    for name,role in [('journey-owner','admin'),('journey-other','admin'),('journey-viewer','viewer')]:
        app.state.auth_store.create_user(name,password,role)
    with closing(sqlite3.connect(database)) as db:
        row=db.execute("SELECT id,username,role FROM auth_users WHERE username='journey-owner'").fetchone()
    owner=dict(zip(('id','username','role'),row));store=AgentStore(database)
    source=ResearchHistory(database).save(str(uuid4()),{'scope':'SYNTHETIC combined journey'},
        {'model_version':'delay-v2','artifact_sha256':'a'*64,'research_only':True,
         'operational_serving_approved':False,'arrival_delay_15_probability':0.2,
         'limitations':['SYNTHETIC stored prediction; no inference executed']},owner)
    evidence=None if live_rag else EvidenceHistory(database).save(owner,{'question':'SYNTHETIC combined journey evidence',
        'mode':'evidence_only','evidence':[{'text':'SYNTHETIC saved evidence; no retrieval executed'}],
        'claims':[],'research_only':True,'operational_approval':False})
    checks={};trace=[]

    def check(name,condition):
        checks[name]=bool(condition)
        if not condition:raise RuntimeError('journey_check_failed:'+name)

    def login(client,name):
        r=client.post('/api/v1/auth/login',json={'username':name,'password':password},headers=ORIGIN)
        check('login_'+name,r.status_code==200)
        return {**ORIGIN,'X-CSRF-Token':r.json()['csrf_token']}

    def request(client,path,body,headers,status=200):
        r=client.post(path,json=body,headers=headers)
        if r.status_code!=status:raise RuntimeError('unexpected_journey_response:'+str(r.status_code))
        return r.json()

    def checkpoint(record):
        # Mutation replay metadata is not part of the canonical case projection.
        record={k:v for k,v in record.items() if k!='replayed'}
        trace.append({'version':record['version'],'status':record['status'],
                      'action':record['events'][-1]['action'],'case_sha256':digest(record)})

    # Default mode is deterministic. Live mode spies wrap the original functions;
    # they record real calls and never supply fixture responses or checkpoints.
    with ExitStack() as stack:
        worker=app.state.job_worker
        model=ollama.models().get(ollama.CHAT_MODEL) if live_ai else None
        if live_ai and not model:raise RuntimeError('journey_check_failed:local_model_unavailable')
        provider=stack.enter_context(patch('rag.ollama.generate',**({'wraps':ollama.generate} if live_ai else {'side_effect':RuntimeError('provider_forbidden_in_fixture')})))
        planner=stack.enter_context(patch('agents.runtime.select_tools',**({'wraps':runtime.select_tools} if live_ai else {'side_effect':RuntimeError('planner_forbidden_in_fixture')})))
        tool_calls=stack.enter_context(patch('agents.tools.execute',wraps=tools.execute))
        if not live_ai:
            stack.enter_context(patch.object(worker,'start'))
            stack.enter_context(patch.object(worker,'stop',new=AsyncMock()))
            worker.task=SimpleNamespace(done=lambda:False)
        worker.enabled=True
        client=stack.enter_context(TestClient(app))
        check('anonymous_denied',client.get(BASE).status_code==401)
        headers=login(client,'journey-owner')
        source_ref=client.get('/api/v1/research/case-sources').json()['sources'][0]
        check('saved_prediction_pin',source_ref['run_id']==source['run_id'] and source_ref['source_sha256']==digest(source))
        opened=request(client,BASE,{'source_run_id':source['run_id'],'source_sha256':source_ref['source_sha256'],
            'title':'SYNTHETIC combined journey; no airline action'}, {**headers,'Idempotency-Key':str(uuid4())})
        path=BASE+'/'+opened['id'];checkpoint(opened)
        check('csrf_denied',client.post(path+'/events',json={'expected_version':1,'action':'note','note':'SYNTHETIC forbidden note'},headers=ORIGIN).status_code==403)
        noted=request(client,path+'/events',{'expected_version':1,'action':'note','note':'SYNTHETIC investigation note'},headers);checkpoint(noted)
        qa_execution=None
        if live_rag:
            expected_models=ollama.models()
            before_generation=provider.call_count
            with patch.object(ollama,'embed',wraps=ollama.embed) as query_embeddings:
                evidence=request(client,'/api/v1/research/knowledge-query',{'question':'What limitations of the recorded delay model concern UAE airline transfer, live schedules, weather and seasonal robustness?','generate':True,'verbatim':True},headers)
            qa_execution=validate_live_qa(evidence,private_index,expected_models)
            qa_execution.update(index_embedding_calls=index_calls,query_embedding_calls=query_embeddings.call_count,generation_calls=provider.call_count-before_generation)
            check('live_qa_model_calls',index_calls>0 and query_embeddings.call_count==1 and qa_execution['generation_calls']==1)
            sources=client.get('/api/v1/research/case-evidence-sources').json()['sources']
            check('live_qa_owned_saved_source',any(s['run_id']==evidence['run_id'] and s['sha256']==digest(evidence) for s in sources))
            with closing(sqlite3.connect(database)) as db:
                stored=db.execute('SELECT result_json FROM knowledge_runs WHERE id=? AND owner_id=?',(evidence['run_id'],owner['id'])).fetchone()
            check('live_qa_saved_exactly',stored is not None and json.loads(stored[0])==evidence)
            missing=private_index.with_suffix('.offline');private_index.rename(missing)
            try:
                with patch.object(ollama,'embed',wraps=ollama.embed) as unavailable_embed:
                    unavailable=client.post('/api/v1/research/knowledge-query',json={'question':'What are the model limitations?','generate':True},headers=headers)
                    check('missing_qa_index_fails_before_model_call',unavailable.status_code==503 and unavailable_embed.call_count==0)
            finally:missing.rename(private_index)
            with closing(sqlite3.connect(database)) as db:
                check('failed_qa_not_saved',db.execute('SELECT count(*) FROM knowledge_runs').fetchone()[0]==1)
        agent_generation_start=provider.call_count
        qa=request(client,path+'/evidence',{'expected_version':2,'evidence_run_id':evidence['run_id'],'evidence_sha256':digest(evidence)},headers);checkpoint(qa)
        if live_rag:
            retained=client.get(path+'/evidence/'+evidence['run_id']).json()
            check('live_qa_retained_exactly',retained['snapshot']==evidence and retained['sha256']==digest(evidence))
        payload={'expected_version':3,'investigation':{'objective':'SYNTHETIC deterministic journey fixture; no planner execution',
            'include_distribution_evidence':True,'required_tools':['distribution_evidence']}}
        if live_ai:payload['investigation']['objective']='SYNTHETIC case: use distribution_evidence to compare the recorded January-March and May input distributions. Quote population counts and the exact limitations. Do not explain an individual flight or recommend an airline action.'
        worker.enabled=False
        check('worker_unavailable_refuses_submission',client.post(path+'/jobs',json=payload,headers={**headers,'Idempotency-Key':str(uuid4())}).status_code==503)
        worker.enabled=True;job_headers={**headers,'Idempotency-Key':str(uuid4())}
        captured=client.get(path).json()
        queued=request(client,path+'/jobs',payload,job_headers,202)
        replay=request(client,path+'/jobs',payload,job_headers,202)
        check('submission_replay_same_job',replay['run_id']==queued['run_id'] and replay['replayed'])
        check('captured_case_pin',queued['request']['case_context']['case_sha256']==digest(captured))
        queue=JobQueue(store,CaseJobs(cases))
        if live_ai:
            run=wait_for_job(queue,owner,queued['run_id'],worker)
            check('live_report_awaiting_explicit_review',run['state']=='awaiting_review' and run['reviews']==[])
            check('live_model_digest_bound',run.get('model')=={'name':ollama.CHAT_MODEL,'digest':model})
            check('real_planner_generator_and_tool_calls',planner.call_count>0 and provider.call_count>0 and tool_calls.call_count>0)
            check('live_call_budgets',0<planner.call_count<=3 and 0<provider.call_count-agent_generation_start<=2 and 0<tool_calls.call_count<=3)
            check('live_worker_poll_recorded',worker.last_poll is not None and worker.task is not None and not worker.task.done())
            check('live_distribution_checkpoint',any(s['tool']=='distribution_evidence' and s['state']=='completed' and s['observation']==observation() for s in run['steps']))
            check('live_report_hash',run['report_sha256']==sha({k:run[k] for k in ('request','steps','claims')}))
        else:
            claimed=queue.claim()
            check('claimed_owned_bound_job',claimed is not None and claimed[2]['run_id']==queued['run_id'])
            run=claimed[2];observed=observation()
            quotes=[observed['evidence_text'].splitlines()[0],LIMIT]
            run.update(state='awaiting_review',steps=[{'id':'T1','tool':'distribution_evidence','arguments':{},'state':'completed','observation':observed}],
                claims=[{'text':q,'quote':q,'citation':'T1'} for q in quotes],
                evidence_origin='SYNTHETIC deterministic checkpoint; recorded-distribution reader executed; no planner or generator',
                finding_style='verbatim_source_extracts')
            run['report_sha256']=sha({k:run[k] for k in ('request','steps','claims')});store.checkpoint(run)
        check('automated_coverage',assess_report(run)['passed'])
        check('pending_draft_not_attachable',not any(s['run_id']==run['run_id'] for s in client.get('/api/v1/research/case-agent-sources').json()['sources']))
        review={'run_id':run['run_id'],'report_sha256':run['report_sha256'],'decision':'needs_changes',
                'note':'SYNTHETIC workflow review fixture; not genuine human acceptance'}
        check('changed_report_pin_denied',client.post('/api/v1/research/agent-review',json={**review,'report_sha256':'0'*64},headers=headers).status_code==409)
        reviewed=request(client,'/api/v1/research/agent-review',review,headers)
        check('explicit_needs_changes_review',reviewed['state']=='needs_changes' and len(reviewed['reviews'])==1)
        agent_ref=client.get('/api/v1/research/case-agent-sources').json()['sources'][0]
        attachment={'expected_version':3,'agent_run_id':run['run_id'],'agent_sha256':agent_ref['sha256']}
        attached=request(client,path+'/agents',attachment,headers);checkpoint(attached)
        check('stale_case_edit_denied',client.post(path+'/events',json={'expected_version':3,'action':'note','note':'SYNTHETIC stale write'},headers=headers).status_code==409)
        gate=request(client,'/api/v1/research/optimize-gates',gate_sample().model_dump(mode='json'),{**headers,'Idempotency-Key':str(uuid4())})
        request(client,'/api/v1/research/gate-review',{'run_id':gate['run_id'],'proposal_sha256':gate['proposal_sha256'],
            'review_key':str(uuid4()),'decision':'needs_changes','note':'SYNTHETIC workflow review; no airport decision','acknowledged':True},headers)
        gate_ref=client.get('/api/v1/research/case-gate-sources').json()['sources'][0]
        with_gate=request(client,path+'/gates',{'expected_version':4,'gate_run_id':gate['run_id'],'gate_sha256':gate_ref['sha256']},headers);checkpoint(with_gate)
        repeated=request(client,path+'/agents',attachment,headers)
        check('attachment_replay_no_duplicate',repeated['replayed'] and repeated['version']==5 and len(repeated['agent_links'])==1)
        closed=request(client,path+'/events',{'expected_version':5,'action':'close','note':'SYNTHETIC closing outcome; unresolved findings retained; no airline action'},headers);checkpoint(closed)
        check('closed_case_write_denied',client.post(path+'/events',json={'expected_version':6,'action':'note','note':'SYNTHETIC late note'},headers=headers).status_code==409)
        agent_snapshot=client.get(path+'/agents/'+run['run_id']).json()
        check('retained_agent_exact_pin',digest(agent_snapshot['snapshot'])==agent_ref['sha256'] and agent_snapshot['review_state']=='needs_changes')
        check('all_retained_links_readable',client.get(path+'/evidence/'+evidence['run_id']).status_code==200 and client.get(path+'/gates/'+gate['run_id']).status_code==200)
        sidecar.rename(directory/'temporarily-unavailable.sqlite3')
        try:check('missing_case_store_fail_closed',client.get(path).status_code==503 and not sidecar.exists())
        finally:(directory/'temporarily-unavailable.sqlite3').rename(sidecar)
        check('dependency_recovered_unchanged',client.get(path).json()==closed)
        login(client,'journey-other')
        check('other_admin_private_case_denied',client.get(path).status_code==404 and client.get('/api/v1/research/agent-jobs/'+run['run_id']).status_code==404)
        viewer_headers=login(client,'journey-viewer')
        check('viewer_private_records_denied',client.get(path).status_code==404 and client.get(BASE).json()['cases']==[])
        check('viewer_review_and_case_writes_denied',client.post('/api/v1/research/agent-review',json=review,headers=viewer_headers).status_code==403 and client.post(path+'/events',json={'expected_version':6,'action':'note','note':'SYNTHETIC forbidden'},headers=viewer_headers).status_code==403)
        if not live_ai:check('no_provider_or_planner_execution',provider.call_count==planner.call_count==0)
    # A new app/service instance must read the same saved case, not the prior Python object.
    restarted=create_app(database,research_cases=ResearchCaseService(database,sidecar),knowledge_index=private_index)
    restarted.state.job_worker.enabled=False
    with TestClient(restarted) as client:
        login(client,'journey-owner')
        check('new_application_instance_preserves_closed_case',client.get(path).json()==closed)
    if live_ai:check('live_worker_stopped',worker.task.done())
    return {'checks':checks,'passed':all(checks.values()),'trace':trace,'case_id':closed['id'],
        'planner_executed':bool(live_ai and planner.call_count),'generator_executed':bool(live_ai and provider.call_count),
        'worker_loop_executed':live_ai,'worker_availability_stubbed':not live_ai,'deterministic_checkpoint_fixture':not live_ai,
        'provider_calls':{'planner':planner.call_count,'generator':provider.call_count-agent_generation_start,'tools':tool_calls.call_count},
        'retrieval_executed':live_rag,'qa_generation_executed':live_rag,'qa_fixture':not live_rag,'qa_execution':qa_execution,
        'local_model':{'name':ollama.CHAT_MODEL,'digest':model} if live_ai else None,
        'captured_case_sha256':queued['request']['case_context']['case_sha256'],
        'source_run_id':source['run_id'],'prediction_source_sha256':source_ref['source_sha256'],
        'agent_run_id':run['run_id'],'report_sha256':run['report_sha256'],
        'recorded_distribution_reader_executed':True,'synthetic_milp_executed':True,
        'agent_snapshot_sha256':agent_ref['sha256'],'gate_run_id':gate['run_id'],
        'gate_snapshot_sha256':gate_ref['sha256'],'final_case_sha256':digest(closed)}


def verify(directory,*,live_ai=False,live_rag=False):
    if type(live_ai) is not bool:raise ValueError('explicit_live_ai_boolean_required')
    if type(live_rag) is not bool:raise ValueError('explicit_live_rag_boolean_required')
    if live_rag and not live_ai:raise ValueError('live_rag_requires_live_ai')
    host()
    directory=local(directory)
    if not directory.is_relative_to(ROOT/'.local') or directory==ROOT/'.local':
        raise ValueError('new_private_directory_under_local_required')
    report={'format':'ain-combined-case-journey-v1','checked_at':datetime.now(timezone.utc).isoformat(),
        **identity(),'passed':False,'synthetic_only':True,'transport':'in_process_asgi_testclient','live_ai_requested':live_ai,
        'scope':'Synthetic accounts, predictions, reviews and gate scenarios; fixed public project evidence, not an airline operations dataset.',
        'prediction_inference_executed':False,'retrieval_executed':None if live_rag else False,'live_rag_requested':live_rag,
        'qa_generation_executed':None if live_rag else False,'qa_fixture':not live_rag,'planner_executed':None if live_ai else False,
        'generator_executed':None if live_ai else False,'worker_loop_executed':None if live_ai else False,
        'worker_availability_stubbed':not live_ai,'deterministic_checkpoint_fixture':not live_ai,
        'recorded_distribution_reader_executed':None if live_ai else False,'synthetic_milp_executed':None if live_ai else False,
        'genuine_human_acceptance':False,'primary_database_accessed':False,
        'deployment_performed':False,'production_ready':False}
    before={p:hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest() for p in (*SOURCES,*(knowledge_index.SOURCES if live_rag else ()))}
    # Refuse an existing target before creating any files or publishing a report.
    if directory.exists():raise ValueError('fresh_fixture_directory_required')
    try:
        report.update(exercise(directory,live_ai=True,live_rag=True) if live_rag else exercise(directory,live_ai=True) if live_ai else exercise(directory))
        report['source_sha256'].update(before)
        report['checks']['source_unchanged']=all(hashlib.sha256((ROOT/p).read_text(encoding='utf-8').encode()).hexdigest()==h for p,h in before.items())
        report['passed']=all(report['checks'].values())
    except Exception as error:
        report['passed']=False
        report['error']=str(error) if isinstance(error,RuntimeError) and str(error).startswith(('journey_check_failed:','unexpected_journey_response:')) else 'combined_journey_check_failed'
    if directory.is_dir():(directory/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--live-ai',action='store_true',help='Explicitly run the real local Ollama worker; fixtures still use synthetic reviews.')
    parser.add_argument('--live-rag',action='store_true',help='With --live-ai, build a fresh private index and attach an actual saved generated Q&A.')
    args=parser.parse_args()
    try:report=verify(args.directory,live_ai=args.live_ai,live_rag=args.live_rag)
    except ValueError as error:parser.exit(2,str(error)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
