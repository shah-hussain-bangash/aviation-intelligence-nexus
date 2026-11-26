import assert from 'node:assert/strict';
import http from 'node:http';
import {test} from 'node:test';
import {validateCase,validateSources,renderCase} from '../apps/web/research-cases.mjs';
import {proxyResearchRequest} from '../scripts/api-proxy.mjs';
import {validateEvidenceSources,validateAttachments,renderEvidenceSnapshot} from '../apps/web/case-evidence.mjs';
import {validateAgentSources,validateAgentLinks,renderAgentSnapshot} from '../apps/web/case-agent-links.mjs';
import {validateGateSources,validateGateLinks,renderGateSnapshot} from '../apps/web/case-gate-links.mjs';
import {CaseJobClient,validateCaseJobs,validateCaseJob,renderCaseJob,caseJobRequest} from '../apps/web/case-jobs.mjs';
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',source='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const record=()=>({id,source_run_id:source,source_sha256:'a'.repeat(64),title:'<img src=x onerror=alert(1)>',status:'open',version:1,outcome:null,attachments:[],agent_links:[],gate_links:[],created_at:'2026-11-26T00:00:00Z',updated_at:'2026-11-26T00:00:00Z',scope:'historical_us_research',operational_approval:false,production_ready:false,source_snapshot:{run_id:source,model_version:'delay-v2',research_only:true,operational_serving_approved:false,limitations:['SYNTHETIC FIXTURE']},events:[{version:1,action:'opened',note:'<script>bad()</script>',created_at:'2026-11-26T00:00:00Z'}]});
test('case contract rejects changed identity, scope, chronology and unsafe approval claims',()=>{
 assert.equal(validateCase(record()).version,1);
 for(const change of [{id:'../private'},{source_sha256:'bad'},{version:2},{scope:'operational'},{production_ready:true},{operational_approval:true},{status:'closed'},{source_snapshot:{...record().source_snapshot,run_id:id}},{events:[{...record().events[0],action:'close'}]}])assert.throws(()=>validateCase({...record(),...change}));
 const html=renderCase(record());assert.ok(html.includes('&lt;img'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(html.includes(source));assert.ok(html.includes('not independently authenticated'));
 const closed={...record(),status:'closed',version:2,outcome:'Synthetic outcome',events:[...record().events,{version:2,action:'close',note:'Synthetic outcome',created_at:'2026-11-26T00:01:00Z'}]};assert.equal(validateCase(closed).status,'closed');
});
test('evidence references bind each attachment to its exact case event and reject omissions',()=>{
 const ref={run_id:source,sha256:'c'.repeat(64),question:'<script>SYNTHETIC</script>',mode:'evidence_only',evidence_count:1,attached_version:2};
 const r={...record(),version:2,events:[...record().events,{version:2,action:'evidence',note:'Attached saved research evidence '+source,created_at:'2026-11-26T00:01:00Z'}],attachments:[ref]};
 assert.equal(validateAttachments(r).length,1);assert.equal(validateCase(r).version,2);assert.ok(renderCase(r).includes('&lt;script&gt;SYNTHETIC'));
 for(const changed of [{attachments:[]},{attachments:[{...ref,attached_version:1}]},{attachments:[ref,ref]}])assert.throws(()=>validateAttachments({...r,...changed}));
 assert.equal(validateEvidenceSources({sources:[ref],production_ready:false}).length,1);assert.throws(()=>validateEvidenceSources({sources:[ref,ref],production_ready:false}));
 const response={...ref,case_id:id,case_version:2,research_only:true,operational_approval:false,production_ready:false,snapshot:{run_id:source,question:ref.question,mode:ref.mode,research_only:true,operational_approval:false,evidence:[{text:'<img onerror=bad>'}],claims:[]}};
 const html=renderEvidenceSnapshot(response,r,ref);assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));assert.ok(html.includes('not revalidated'));
 for(const changed of [{sha256:'d'.repeat(64)},{case_version:3},{case_id:source},{production_ready:true},{snapshot:{...response.snapshot,run_id:id}}])assert.throws(()=>renderEvidenceSnapshot({...response,...changed},r,ref));
});
test('saved-source contract rejects duplicate IDs and invalid pins',()=>{
 const r={sources:[{run_id:source,source_sha256:'b'.repeat(64)}],production_ready:false};assert.equal(validateSources(r).length,1);
 assert.throws(()=>validateSources({...r,sources:[...r.sources,...r.sources]}));assert.throws(()=>validateSources({...r,production_ready:true}));assert.throws(()=>validateSources({...r,sources:[{run_id:source,source_sha256:'x'}]}));
});
test('synthetic gate references bind plans, review and case version without HTML execution',()=>{
 const ref={run_id:source,sha256:'c'.repeat(64),proposal_sha256:'d'.repeat(64),scenario_sha256:'e'.repeat(64),data_kind:'synthetic',review_state:'needs_changes',flight_count:5,candidate_assigned:5,candidate_unassigned:0,baseline_assigned:4,baseline_unassigned:1,attached_version:2};
 const r={...record(),version:2,gate_links:[ref],events:[...record().events,{version:2,action:'gate',note:'Attached synthetic gate proposal '+source,created_at:'2026-11-26T00:01:00Z'}]};
 assert.equal(validateCase(r).version,2);assert.ok(renderCase(r).includes('Synthetic proposal'));assert.ok(renderCase(r).includes('Greedy baseline'));
 assert.equal(validateGateSources({sources:[ref],production_ready:false}).length,1);
 for(const patch of [{gate_links:[]},{gate_links:[{...ref,data_kind:'live'}]},{gate_links:[{...ref,candidate_assigned:4}]},{gate_links:[ref,ref]}])assert.throws(()=>validateGateLinks({...r,...patch}));
 const snapshot={run_id:source,proposal_sha256:ref.proposal_sha256,scenario_sha256:ref.scenario_sha256,engine:'scipy-highs-milp',formulation_version:'gate-v1',scenario:{data_kind:'synthetic',flights:Array(5).fill({})},review:{decision:'needs_changes',proposal_sha256:ref.proposal_sha256,note:'<img onerror=bad>'},candidate:{verification:{feasible:true,assigned:5,unassigned:0}},baseline:{verification:{feasible:true,assigned:4,unassigned:1}},research_only:true,operational_approval:false};
 const response={...ref,case_id:id,case_version:2,snapshot,research_only:true,operational_approval:false,production_ready:false};const html=renderGateSnapshot(response,r,ref);assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));assert.ok(html.includes('No gate allocation is applied'));
 for(const patch of [{case_version:3},{data_kind:'live'},{proposal_sha256:'f'.repeat(64)},{review_state:'reviewed'},{snapshot:{...snapshot,operational_approval:true}}])assert.throws(()=>renderGateSnapshot({...response,...patch},r,ref));
});
test('agent links preserve review state and exact event/version binding with escaped snapshots',()=>{
 const ref={run_id:source,sha256:'d'.repeat(64),report_sha256:'e'.repeat(64),objective:'<script>SYNTHETIC findings</script>',review_state:'needs_changes',review_kind:'standard',step_count:0,attached_version:2};
 const r={...record(),version:2,agent_links:[ref],events:[...record().events,{version:2,action:'agent',note:'Attached saved agent report '+source,created_at:'2026-11-26T00:01:00Z'}]};
 assert.equal(validateCase(r).version,2);assert.ok(renderCase(r).includes('needs_changes'));assert.ok(renderCase(r).includes('&lt;script&gt;SYNTHETIC'));
 assert.equal(validateAgentSources({sources:[ref],production_ready:false}).length,1);assert.throws(()=>validateAgentSources({sources:[ref,ref],production_ready:false}));
 for(const patch of [{agent_links:[],gate_links:[]},{agent_links:[{...ref,attached_version:1}]},{agent_links:[ref,ref]}])assert.throws(()=>validateAgentLinks({...r,...patch}));
 const snapshot={run_id:source,state:'needs_changes',report_sha256:ref.report_sha256,runtime:'bounded-ollama-tools-v2',request:{objective:ref.objective},steps:[],reviews:[{decision:'needs_changes',report_sha256:ref.report_sha256,note:'<img src=x onerror=bad>'}],research_only:true,operational_approval:false};
 const response={...ref,case_id:id,case_version:2,snapshot,research_only:true,operational_approval:false,production_ready:false};
 const html=renderAgentSnapshot(response,r,ref);assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));assert.ok(html.includes('not a fresh approval'));
 for(const patch of [{case_version:3},{sha256:'f'.repeat(64)},{review_state:'reviewed'},{operational_approval:true},{snapshot:{...snapshot,state:'reviewed'}}])assert.throws(()=>renderAgentSnapshot({...response,...patch},r,ref));
 const peer={...ref,review_kind:'second_account'};assert.throws(()=>renderAgentSnapshot({...response,review_kind:'second_account'},r,peer));
});
async function server(t,handler){const s=http.createServer(handler);await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{s.closeAllConnections();s.close(resolve);}));return s.address().port;}
test('case gateway forwards only the fixed routes and methods, retains CSRF and creation retry key',async t=>{
 const calls=[];const api=await server(t,async(req,res)=>{let body='';for await(const c of req)body+=c;calls.push({url:req.url,method:req.method,headers:req.headers,body});res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');});
 const port=await server(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,api)){res.writeHead(404);res.end();}});
 const root=`http://127.0.0.1:${port}/api/v1/research`;
 for(const path of ['/case-sources','/cases','/cases/'+id]){const r=await fetch(root+path);assert.equal(r.status,200);await r.text();}
 for(const path of ['/cases','/cases/'+id+'/events']){const r=await fetch(root+path,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':id,'X-CSRF-Token':'fixture','Origin':'http://127.0.0.1:8080',Cookie:'ain_session=fixture; unrelated=hidden'},body:JSON.stringify({note:'家'.repeat(2000)})});assert.equal(r.status,200);await r.text();}
 assert.equal(calls.length,5);assert.equal(calls[3].headers['idempotency-key'],id);assert.equal(calls[4].headers['x-csrf-token'],'fixture');assert.equal(calls[3].headers.cookie,'ain_session=fixture');
 for(const [path,method,status] of [['/cases','DELETE',405],['/cases/'+id,'POST',405],['/case-sources','POST',405],['/cases/'+id+'/events','GET',405],['/cases?owner=peer','GET',422],['/cases/'+id+'/private','GET',404],['/cases/not-a-uuid','GET',404]]){const r=await fetch(root+path,{method});assert.equal(r.status,status,path);await r.text();}
 const huge=await fetch(root+'/cases/'+id+'/events',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(17000)});assert.equal(huge.status,413);await huge.text();assert.equal(calls.length,5);
});
test('evidence gateway bounds methods and rejects caller-selected paths and query authority',async t=>{
 const calls=[];const api=await server(t,async(req,res)=>{for await(const c of req){}calls.push(req.url);res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');});
 const port=await server(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,api)){res.writeHead(404);res.end();}});
 const root=`http://127.0.0.1:${port}/api/v1/research`;
 for(const [path,method,status] of [['/case-evidence-sources','GET',200],['/cases/'+id+'/evidence','POST',200],['/cases/'+id+'/evidence/'+source,'GET',200],['/cases/'+id+'/evidence','GET',405],['/cases/'+id+'/evidence/'+source,'POST',405],['/case-evidence-sources?owner=peer','GET',422],['/cases/'+id+'/evidence/not-a-uuid','GET',404],['/cases/'+id+'/evidence/'+source+'?path=private','GET',422]]){const r=await fetch(root+path,{method,...(method==='POST'?{headers:{'Content-Type':'application/json'},body:'{}'}:{})});assert.equal(r.status,status,path);await r.text();}
 assert.equal(calls.length,3);
});
test('agent attachment gateway exposes only fixed reads and writes',async t=>{
 const calls=[];const api=await server(t,async(req,res)=>{for await(const c of req){}calls.push(req.url);res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');});
 const port=await server(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,api)){res.writeHead(404);res.end();}});const root=`http://127.0.0.1:${port}/api/v1/research`;
 for(const [path,method,status] of [['/case-agent-sources','GET',200],['/cases/'+id+'/agents','POST',200],['/cases/'+id+'/agents/'+source,'GET',200],['/cases/'+id+'/agents','GET',405],['/cases/'+id+'/agents/'+source,'POST',405],['/case-agent-sources?owner=peer','GET',422],['/cases/'+id+'/agents/not-a-uuid','GET',404]]){const r=await fetch(root+path,{method,...(method==='POST'?{headers:{'Content-Type':'application/json'},body:'{}'}:{})});assert.equal(r.status,status,path);await r.text();}assert.equal(calls.length,3);
});
test('gate attachment gateway rejects arbitrary paths, query authority and unsupported methods',async t=>{
 const calls=[];const api=await server(t,async(req,res)=>{for await(const c of req){}calls.push(req.url);res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');});
 const port=await server(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,api)){res.writeHead(404);res.end();}});const root=`http://127.0.0.1:${port}/api/v1/research`;
 for(const [path,method,status] of [['/case-gate-sources','GET',200],['/cases/'+id+'/gates','POST',200],['/cases/'+id+'/gates/'+source,'GET',200],['/cases/'+id+'/gates','GET',405],['/cases/'+id+'/gates/'+source,'POST',405],['/case-gate-sources?owner=peer','GET',422],['/cases/'+id+'/gates/not-a-uuid','GET',404]]){const r=await fetch(root+path,{method,...(method==='POST'?{headers:{'Content-Type':'application/json'},body:'{}'}:{})});assert.equal(r.status,status,path);await r.text();}assert.equal(calls.length,3);
});

test('case job gateway permits fixed GET and POST without query authority',async t=>{
 const calls=[];const api=await server(t,async(req,res)=>{for await(const c of req){}calls.push(req.url);res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');});
 const port=await server(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,api)){res.writeHead(404);res.end();}});
 const root=`http://127.0.0.1:${port}/api/v1/research/cases/`;
 for(const [path,method,status] of [[id+'/jobs','GET',200],[id+'/jobs','POST',200],[id+'/jobs?owner=peer','GET',422],[id+'/jobs?version=1','POST',422],[id+'/jobs','DELETE',405],['not-a-uuid/jobs','GET',404],[id+'/jobs/shell','POST',404]]){
  const r=await fetch(root+path,{method,...(method==='POST'?{headers:{'Content-Type':'application/json'},body:'{}'}:{})});assert.equal(r.status,status,path);await r.text();
 }assert.equal(calls.length,2);
});


const owner={username:'synthetic-owner',role:'admin'};
function savedCaseJob(r=record(),state='queued'){
 return {run_id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc',state,updated_at:'2026-11-26T01:00:00Z',runtime:'bounded-ollama-tools-v2',execution:'local-background-queue-v1',research_only:true,operational_approval:false,steps:[],claims:[],request:{...caseJobRequest(r,'SYNTHETIC distribution investigation'),case_context:null}};
}
function jobFixture(r=record(),state='queued'){
 const run=savedCaseJob(r,state);run.request={...caseJobRequest(r,'SYNTHETIC distribution investigation').investigation,case_context:{case_id:r.id,case_version:r.version,case_sha256:'d'.repeat(64),source_run_id:r.source_run_id,source_sha256:r.source_sha256,title:r.title,scope:'historical_us_research'}};return run;
}
const jobRef=run=>({run_id:run.run_id,state:run.state,updated_at:run.updated_at,case_context:run.request.case_context});
const response=value=>({ok:true,json:async()=>structuredClone(value)});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};

test('case job contract rejects cross-case, future versions, altered pins and approval claims',()=>{
 const r=record(),run=jobFixture(r);assert.equal(validateCaseJob(run,r).state,'queued');assert.equal(validateCaseJobs({jobs:[jobRef(run)],production_ready:false},r).length,1);
 for(const patch of [{operational_approval:true},{execution:'shell'},{request:{...run.request,case_context:{...run.request.case_context,case_id:source}}},{request:{...run.request,case_context:{...run.request.case_context,case_version:2}}},{request:{...run.request,case_context:{...run.request.case_context,source_sha256:'f'.repeat(64)}}},{request:{...run.request,require_peer_review:true}},{state:'awaiting_review'},{steps:Array(4).fill({})}])assert.throws(()=>validateCaseJob({...run,...patch},r));
 assert.throws(()=>validateCaseJobs({jobs:[jobRef(run),jobRef(run)],production_ready:false},r));
 const older={...r,version:2};assert.equal(validateCaseJob(run,older).request.case_context.case_version,1);
 assert.throws(()=>caseJobRequest({...r,status:'closed'},'SYNTHETIC investigation'));assert.throws(()=>caseJobRequest(r,'short'));
});

test('unreviewed draft renders quoted findings and context as escaped text',()=>{
 const r=record(),run=jobFixture(r,'awaiting_review');run.report_sha256='e'.repeat(64);run.quality={passed:true};run.claims=[{text:'<img src=x onerror=bad>',quote:'<img src=x onerror=bad>',citation:'<script>citation</script>'}];
 const html=renderCaseJob(run,r);assert.ok(html.includes('Unreviewed research draft'));assert.ok(html.includes('Automated coverage passed'));assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));assert.ok(!html.includes('<script>'));assert.ok(html.includes('do not establish answer usefulness'));
 assert.throws(()=>renderCaseJob({...run,claims:[{...run.claims[0],text:'Unsupported paraphrase'}]},r));
});

test('case job reads and viewer interactions never submit or cancel work',async()=>{
 const run=jobFixture(),calls=[];const client=new CaseJobClient(async(path,options)=>{calls.push({path,options});return response(path.endsWith('/jobs')?{jobs:[jobRef(run)],production_ready:false}:run);});
 await client.setContext({...owner,role:'viewer'},record(),true);await client.select(run.run_id);await client.load();
 assert.equal(await client.submit('SYNTHETIC distribution investigation',true),false);assert.equal(await client.cancel(),false);assert.ok(calls.every(c=>!c.options.method));assert.equal(client.selected.run_id,run.run_id);
});

test('start requires acknowledgement and verifies the submitted tool permissions',async()=>{
 const r=record(),calls=[];const client=new CaseJobClient(async(path,options)=>{calls.push({path,options});if(!options.method)return response({jobs:[],production_ready:false});const run=jobFixture(r);run.request={...JSON.parse(options.body).investigation,case_context:run.request.case_context};return response(run);},()=>{},()=>id);
 await client.setContext(owner,r,true);assert.equal(await client.submit('SYNTHETIC distribution investigation',false),false);assert.equal(calls.length,1);
 assert.equal(await client.submit('SYNTHETIC distribution investigation',true),true);assert.equal(client.pending,null);assert.equal(client.selected.state,'queued');assert.equal(calls[1].options.headers['Idempotency-Key'],id);
 assert.deepEqual(JSON.parse(calls[1].options.body).investigation.required_tools,['distribution_evidence']);assert.equal(client.rows.length,1);
});

test('uncertain submission preserves its exact key and body and blocks changed retry inputs',async()=>{
 const posts=[];let attempts=0;const r=record();const client=new CaseJobClient(async(path,options)=>{if(!options.method)return response({jobs:[],production_ready:false});posts.push(options);if(++attempts===1)throw Error('Synthetic response loss');return response(jobFixture(r));},()=>{},()=>id);
 await client.setContext(owner,r,true);assert.equal(await client.submit('SYNTHETIC distribution investigation',true),false);assert.ok(client.pending);
 assert.equal(await client.submit('SYNTHETIC changed objective',true),false);assert.equal(posts.length,1);
 assert.equal(await client.submit('SYNTHETIC distribution investigation',true),true);assert.equal(posts.length,2);assert.equal(posts[0].body,posts[1].body);assert.equal(posts[0].headers['Idempotency-Key'],posts[1].headers['Idempotency-Key']);
});

test('a saved response cannot silently expand a submitted simulation permission',async()=>{
 const r=record();const client=new CaseJobClient(async(path,options)=>{if(!options.method)return response({jobs:[],production_ready:false});const run=jobFixture(r);run.request.include_simulation=true;return response(run);});
 await client.setContext(owner,r,true);assert.equal(await client.submit('SYNTHETIC distribution investigation',true),false);assert.equal(client.selected,null);assert.equal(client.blocked,true);
});

test('switching cases with an in-flight run read clears and ignores the older response',async()=>{
 const old=jobFixture(),waiting=deferred();const next={...record(),id:'dddddddd-dddd-4ddd-8ddd-dddddddddddd'};
 const client=new CaseJobClient(async path=>path.endsWith('/jobs')?response({jobs:path.includes(next.id)?[]:[jobRef(old)],production_ready:false}):waiting.promise);
 await client.setContext(owner,record(),true);const pending=client.select(old.run_id);await client.setContext(owner,next,true);waiting.resolve(response(old));await pending;
 assert.equal(client.record.id,next.id);assert.equal(client.selected,null);assert.deepEqual(client.rows,[]);assert.equal(client.blocked,false);
});

test('sign-out during submission ignores completion and clears private client state',async()=>{
 const waiting=deferred();const client=new CaseJobClient(async(path,options)=>options.method?waiting.promise:response({jobs:[],production_ready:false}));
 await client.setContext(owner,record(),true);const submission=client.submit('SYNTHETIC distribution investigation',true);await client.setContext(null,null,false);waiting.resolve(response(jobFixture()));await submission;
 assert.equal(client.selected,null);assert.equal(client.pending,null);assert.equal(client.user,null);assert.deepEqual(client.rows,[]);assert.equal(client.message,'');
});

test('running cancellation requests a safe stop and never resubmits an investigation',async()=>{
 const run=jobFixture(record(),'running'),calls=[];const client=new CaseJobClient(async(path,options)=>{calls.push({path,options});if(options.method)return response({...run,cancel_requested_at:'2026-11-26T01:01:00Z'});return response(path.endsWith('/jobs')?{jobs:[jobRef(run)],production_ready:false}:run);});
 await client.setContext(owner,record(),true);await client.select(run.run_id);assert.equal(client.canCancel,true);assert.equal(await client.cancel(),true);assert.equal(client.canCancel,false);
 assert.equal(calls.at(-1).path,'/api/v1/research/agent-cancel');assert.deepEqual(JSON.parse(calls.at(-1).options.body),{run_id:run.run_id});assert.ok(client.message.includes('in-flight'));
});

test('conflicting saved state clears the selected draft and blocks writes until case refresh',async()=>{
 const run=jobFixture();let deny=false;const client=new CaseJobClient(async path=>deny?{ok:false,status:409}:response(path.endsWith('/jobs')?{jobs:[jobRef(run)],production_ready:false}:run));
 await client.setContext(owner,record(),true);await client.select(run.run_id);deny=true;await client.cancel();assert.equal(client.selected,null);assert.equal(client.canStart,false);
});

test('refresh and queued cancellation keep selector state aligned with saved checkpoints',async()=>{
 const queued=jobFixture(),running={...queued,state:'running'};
 const client=new CaseJobClient(async(path,options)=>response(options.method?{...running,state:'cancelled'}:path.endsWith('/jobs')?{jobs:[jobRef(queued)],production_ready:false}:running));
 await client.setContext(owner,record(),true);assert.equal(client.rows[0].state,'queued');await client.select(queued.run_id);assert.equal(client.rows[0].state,'running');
 await client.cancel();assert.equal(client.selected.state,'cancelled');assert.equal(client.rows[0].state,'cancelled');
 const stopped={...client.selected,cancel_requested_at:'2026-11-26T01:01:00Z'};
 assert.ok(!renderCaseJob(stopped,record()).includes('An in-flight call may finish'));
});

const draftFixture=()=>({...jobFixture(record(),'awaiting_review'),report_sha256:'e'.repeat(64),quality:{passed:true},reviews:[]});
const reviewedFixture=(draft=draftFixture(),decision='reviewed',note='SYNTHETIC UI contract review only')=>({...draft,state:decision,reviews:[{actor:owner.username,decision,note,report_sha256:draft.report_sha256,at:'2026-11-26T02:00:00Z'}]});
async function selectedClient(run,handler){
 const client=new CaseJobClient(async(path,options)=>{if(handler){const value=await handler(path,options);if(value)return value;}return response(path.endsWith('/jobs')?{jobs:[jobRef(run)],production_ready:false}:run);});
 await client.setContext(owner,record(),true);await client.select(run.run_id);return client;
}
test('case review requires explicit acknowledgement, note, role and automated coverage for acceptance',async()=>{
 let posts=0;const draft=draftFixture(),client=await selectedClient(draft,(path,options)=>{if(options.method){posts++;const b=JSON.parse(options.body);assert.equal(path,'/api/v1/research/agent-review');assert.equal(b.report_sha256,draft.report_sha256);return response(reviewedFixture(draft,b.decision,b.note));}});
 assert.equal(await client.review('reviewed','SYNTHETIC review',false),false);assert.equal(await client.review('reviewed','bad',true),false);
 client.selected.quality.passed=false;assert.equal(await client.review('reviewed','SYNTHETIC review',true),false);assert.equal(posts,0);
 assert.equal(await client.review('needs_changes','SYNTHETIC fixture requires changes',true),true);assert.equal(client.selected.state,'needs_changes');assert.equal(posts,1);assert.equal(client.record.version,1);assert.deepEqual(client.record.agent_links,[]);
 const viewer=await selectedClient(draft);viewer.user={...owner,role:'viewer'};assert.equal(await viewer.review('needs_changes','SYNTHETIC review',true),false);assert.equal(viewer.canAttach,false);
});
test('case review rejects an altered receipt or report fingerprint',async()=>{
 for(const patch of [{report_sha256:'f'.repeat(64)},{reviews:[]},{reviews:[{...reviewedFixture().reviews[0],note:'Altered server response'}]}]){
  const client=await selectedClient(draftFixture(),(path,options)=>options.method?response({...reviewedFixture(),...patch}):null);
  assert.equal(await client.review('reviewed','SYNTHETIC UI contract review only',true),false);assert.equal(client.selected,null);assert.equal(client.blocked,true);
 }
});
test('uncertain review clears selection and cannot blindly repeat the write',async()=>{
 let posts=0;const client=await selectedClient(draftFixture(),(path,options)=>{if(options.method){posts++;throw Error('SYNTHETIC response loss');}});
 assert.equal(await client.review('reviewed','SYNTHETIC review fixture',true),false);assert.equal(await client.review('reviewed','SYNTHETIC review fixture',true),false);assert.equal(posts,1);assert.ok(client.message.includes('inspect saved'));
});
const sourceFixture=run=>({run_id:run.run_id,sha256:'f'.repeat(64),report_sha256:run.report_sha256,objective:run.request.objective,review_state:run.state,review_kind:'standard',step_count:run.steps.length});
function attachedFixture(run){const r=record();return {...r,version:2,events:[...r.events,{version:2,action:'agent',note:'Attached saved agent report '+run.run_id,created_at:r.updated_at}],agent_links:[{...sourceFixture(run),attached_version:2}]};}
test('attachment pins refreshed owned source and displayed case version, preserving needs-changes label',async()=>{
 const run=reviewedFixture(draftFixture(),'needs_changes'),calls=[];let attached=null;
 const client=await selectedClient(run,(path,options)=>{calls.push({path,options});if(path.endsWith('/'+id))return response(record());if(path.endsWith('/case-agent-sources'))return response({sources:[sourceFixture(run)],production_ready:false});if(options.method)return response(attachedFixture(run));});
 assert.equal(await client.attach(validateCase,r=>{attached=r;}),true);assert.equal(attached.version,2);assert.equal(attached.agent_links[0].review_state,'needs_changes');
 const post=calls.filter(c=>c.options.method);assert.equal(post.length,1);assert.deepEqual(JSON.parse(post[0].options.body),{expected_version:1,agent_run_id:run.run_id,agent_sha256:'f'.repeat(64)});
});
test('attachment rejects changed case versions, source pins and review state without posting',async()=>{
 for(const kind of ['version','source','review']){const run=reviewedFixture();let posts=0,called=false;
  const client=await selectedClient(run,(path,options)=>{if(options.method){posts++;throw Error('unexpected');}if(path.endsWith('/'+id))return response(kind==='version'?{...record(),version:2,events:[...record().events,{version:2,action:'note',note:'SYNTHETIC concurrent edit',created_at:record().updated_at}]}:record());if(path.endsWith('/case-agent-sources'))return response({sources:[{...sourceFixture(run),report_sha256:'a'.repeat(64)}],production_ready:false});if(path.includes('/agent-jobs/')&&kind==='review'&&called)return response(reviewedFixture(draftFixture(),'needs_changes'));called=true;});
  assert.equal(await client.attach(validateCase,()=>assert.fail('must not attach')),false);assert.equal(posts,0);assert.equal(client.selected,null);
 }
});
test('signing out during attachment preflight prevents the mutation',async()=>{
 const wait=deferred(),run=reviewedFixture();let posts=0;const client=await selectedClient(run,(path,options)=>{if(options.method)posts++;if(path.endsWith('/'+id))return wait.promise;});
 const pending=client.attach(validateCase,()=>assert.fail('late case result'));await client.setContext(null,null,false);wait.resolve(response(record()));await pending;assert.equal(posts,0);assert.equal(client.selected,null);
});
test('closed, full and already-linked cases disallow attachment',async()=>{
 const run=reviewedFixture(),client=await selectedClient(run);assert.equal(client.canAttach,true);
 client.record={...record(),status:'closed'};assert.equal(client.canAttach,false);client.record={...record(),version:100};assert.equal(client.canAttach,false);
 client.record={...record(),agent_links:[sourceFixture(run)]};assert.equal(client.canAttach,false);client.record={...record(),agent_links:Array(5).fill({run_id:id})};assert.equal(client.canAttach,false);
});
