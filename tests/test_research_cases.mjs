import assert from 'node:assert/strict';
import http from 'node:http';
import {test} from 'node:test';
import {validateCase,validateSources,renderCase} from '../apps/web/research-cases.mjs';
import {proxyResearchRequest} from '../scripts/api-proxy.mjs';
import {validateEvidenceSources,validateAttachments,renderEvidenceSnapshot} from '../apps/web/case-evidence.mjs';
import {validateAgentSources,validateAgentLinks,renderAgentSnapshot} from '../apps/web/case-agent-links.mjs';
import {validateGateSources,validateGateLinks,renderGateSnapshot} from '../apps/web/case-gate-links.mjs';
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
