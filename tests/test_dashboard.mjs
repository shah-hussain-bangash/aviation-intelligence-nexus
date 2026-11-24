import {validateLineage,renderLineage} from '../apps/web/batch-lineage.mjs';
import {validateIntake,renderIntake} from '../apps/web/intake-overview.mjs';
import {validateRetrieval,retrievalCases,renderRetrieval,retrievalExport} from '../apps/web/retrieval-evaluation.mjs';
import {validateScopedResult,renderScopedResult,scopedExport} from '../apps/web/scoped-answer-lab.mjs';
import {validateQuality,renderQuality} from '../apps/web/data-quality.mjs';
import {canWithdrawSharing} from '../apps/web/sharing-withdrawal.mjs';
import {validateTradeoffs,tradeoffScenario,renderTradeoffs} from '../apps/web/threshold-tradeoffs.mjs';
import {validateDuration,renderDuration} from '../apps/web/duration-evaluation.mjs';
import {validateDurationSnapshot,renderDurationSnapshot} from '../apps/web/agent-duration-evidence.mjs';
import {archiveQuery,validateArchive} from '../apps/web/agent-archive-contract.mjs';
import {validateSecurity,renderSecurity} from '../apps/web/account-security.mjs';
import {validateDistributions,renderDistributions} from '../apps/web/input-distributions.mjs';
import {validateDistributionSnapshot} from '../apps/web/agent-distribution-evidence.mjs';
import {renderArchive} from '../apps/web/agent-archive.mjs';
import {gateReviewEligible,renderGateReview} from '../apps/web/gate-review.mjs';
import {validateOperations,renderOperations} from '../apps/web/agent-operations.mjs';
import {validateModelSnapshot,renderModelSnapshot} from '../apps/web/agent-model-evidence.mjs';
import {renderExplanations,validateExplanations} from '../apps/web/model-explanations.mjs';
import {renderDiagnostics,validateDiagnostics} from '../apps/web/model-diagnostics.mjs';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { test } from 'node:test';
import { renderResearchSummary } from '../apps/web/live-research.mjs';
import { proxyResearchRequest } from '../scripts/api-proxy.mjs';
import { renderPrediction } from '../apps/web/research-scenario.mjs';
import { renderHistory } from '../apps/web/research-history.mjs';
import { sampleGateScenario, renderGatePlan } from '../apps/web/gate-lab.mjs';
import { renderKnowledge } from '../apps/web/knowledge-lab.mjs';
import { renderInvestigation, investigationPayload,canReviewInvestigation } from '../apps/web/investigation-lab.mjs';
import {renderInbox,validateInbox} from '../apps/web/review-inbox.mjs';
import {renderPlatform,rollbackExport,renderObserver,observerAfterDelay} from '../apps/web/platform-status.mjs';

function observerFixture(){return {state:'healthy',components:{api_readiness:true,frontend_liveness:true},sample_age_seconds:2,checked_at:'2026-11-23T10:00:00Z',source_mode:'container_readonly_mount',task_runtime_verified:false,external_alert_delivery:false,production_ready:false};}
test('observer accounts conservatively for response delay and never renews an expired sample',()=>{
 assert.equal(observerAfterDelay(observerFixture(),1).sample_age_seconds,3);
 assert.equal(observerAfterDelay(observerFixture(),13).state,'unknown');
 assert.equal(observerAfterDelay(observerAfterDelay(observerFixture(),13),0).state,'unknown');
 assert.throws(()=>observerAfterDelay(observerFixture(),-1));
});
test('observer display distinguishes observations, unavailable endpoints and unknown health',()=>{
 assert.match(renderObserver(observerFixture()),/Fresh observation · endpoints healthy/);
 const degraded=observerFixture();degraded.state='degraded';degraded.components.api_readiness=false;
 assert.match(renderObserver(degraded),/Observed unavailable/);
 assert.match(renderObserver(),/No fresh observation available/);
 assert.match(renderObserver(observerFixture()),/does not verify that the Windows task is running/);
});
test('observer rejects stale and contradictory observations and unsafe readiness claims',()=>{
 for(const change of [v=>v.sample_age_seconds=15,v=>v.sample_age_seconds=-1,v=>v.sample_age_seconds=NaN,v=>v.state='degraded',v=>v.components.api_readiness='true',v=>v.components=[],v=>v.state='unknown',v=>v.source_mode='not_configured',v=>v.task_runtime_verified=true,v=>v.external_alert_delivery=true,v=>v.production_ready=true,v=>v.checked_at='<img src=x onerror=alert(1)>']){
  const value=observerFixture();change(value);assert.throws(()=>renderObserver(value));
 }
});
import {runtimeConfig,routing} from '../scripts/runtime-config.mjs';
import {renderMonitoring,validateMonitoring,monitoringView,monitoringExport} from '../apps/web/monitoring-lab.mjs';
import fs from 'node:fs';
import {renderReadiness,filterReadiness} from '../apps/web/release-readiness.mjs';
import {renderPatterns,validatePatterns} from '../apps/web/route-patterns.mjs';
import {renderRouteHistory,validateRouteHistory} from '../apps/web/route-history.mjs';

const routeHistoryFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Route_History_Lookup.json',import.meta.url),'utf8')).example;
const archiveFixture=()=>({runs:[{run_id:'00000000-0000-4000-8000-000000000001',actor:'fixture-owner',objective:'Review saved <script> evidence.',state:'cancelled',created_at:'2026-11-21T00:00:00Z',updated_at:'2026-11-21T00:00:00Z'}],through:'9223372036854775807',next_before:null,page_size:10,order:'newest_created_first',search_scope:'objective_literal_ascii_case_insensitive',research_only:true,operational_approval:false});
const securityFixture=()=>({active_sessions:3,other_active_sessions:2,checked_at:'2026-11-21T10:00:00Z',current_expires_at:'2026-11-21T18:00:00Z',scope:'current_account_local_sessions',production_ready:false});
const distributionFixture=()=>({...JSON.parse(fs.readFileSync(new URL('../docs/reports/Input_Distributions.json',import.meta.url),'utf8')),integrity_verified:true,report_sha256:'a'.repeat(64)});
const distributionAgentFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Distribution_Agent_Integration.json',import.meta.url),'utf8')).run;
const peerFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Second_Account_Review.json',import.meta.url),'utf8'));
test('second-account review is explicit and author access is fail-closed while old reports retain behavior',()=>{
 const f=peerFixture();assert.equal(canReviewInvestigation(f.pending,{role:'admin'}),false);assert.equal(canReviewInvestigation(f.peer_view,{role:'researcher'}),true);assert.equal(canReviewInvestigation(f.peer_view,{role:'viewer'}),false);assert.equal(canReviewInvestigation({...f.peer_view,review_access:undefined},{role:'admin'}),false);assert.equal(canReviewInvestigation(distributionAgentFixture(),{role:'researcher'}),true);
 assert.match(renderInvestigation(f.reviewed),/research review recorded/);assert.doesNotMatch(renderInvestigation(f.reviewed),/human review required/);
 const input={objective:'Review recorded research evidence.',month:'2025-05',simulation:false,requirePeerReview:false};assert.ok(!Object.hasOwn(investigationPayload(input),'require_peer_review'));input.requirePeerReview=true;assert.equal(investigationPayload(input).require_peer_review,true);assert.match(renderInvestigation(f.pending),/Different accounts do not prove different people/);
});
test('review inbox metadata is bounded, escaped and rejects unexpected scope',()=>{
 const run=peerFixture().peer_view,data={runs:[{run_id:run.run_id,author:'<script>',objective:'Review <img> evidence.',updated_at:run.updated_at}],limit:20,has_more:false,checked_at:run.updated_at,scope:'explicit_pending_second_account_reports',research_only:true,operational_approval:false};
 const html=renderInbox(data);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.throws(()=>validateInbox({...data,operational_approval:true}));assert.throws(()=>validateInbox({...data,runs:[...data.runs,...data.runs]}));assert.match(renderInbox({...data,runs:[]}),/No pending reports/);
});
test('review inbox proxy permits only a fixed read and filters unrelated cookies',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/agent-review-inbox');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,backend)){res.writeHead(404);res.end();}});const url=`http://127.0.0.1:${frontend}/api/v1/research/agent-review-inbox`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);assert.equal((await fetch(url+'?account=other')).status,422);assert.equal((await fetch(url,{method:'POST'})).status,405);
});
test('agent distribution permission is explicit, excluded when false and counts against the same three slots',()=>{
 const input={objective:'Review recorded input distributions.',month:'2025-05',simulation:false,requireFlights:true,requireKnowledge:true,includeDistributionEvidence:false};assert.ok(!Object.hasOwn(investigationPayload(input),'include_distribution_evidence'));
 input.includeDistributionEvidence=true;assert.equal(investigationPayload(input).required_tools.length,3);assert.equal(investigationPayload(input).include_distribution_evidence,true);input.includeModelEvidence=true;assert.throws(()=>investigationPayload(input));
});
test('saved distribution snapshots retain all five inputs and limitations beyond generated extracts',()=>{
 const run=distributionAgentFixture();run.claims=[];const html=renderInvestigation(run);assert.match(html,/1,611,046/);assert.match(html,/597,574/);assert.match(html,/0.046677/);assert.match(html,/No live drift alert/);assert.match(html,/Three largest absolute share changes/);
 run.request.include_distribution_evidence=false;assert.match(renderInvestigation(run),/distribution evidence could not be verified/);
});
test('distribution snapshot display rejects bad arithmetic and cached mismatch and escapes evidence text',()=>{
 let run=distributionAgentFixture();run.steps[0].observation.snapshot.features.origin.comparison_unseen_records=999999;assert.throws(()=>validateDistributionSnapshot(run.steps[0].observation));assert.match(renderInvestigation(run),/has been withheld/);
 run=distributionAgentFixture();run.quality.distribution_evidence_mismatches=['T1'];assert.match(renderInvestigation(run),/has been withheld/);
 run=distributionAgentFixture();run.steps[0].observation.snapshot.limitations=['<script>bad()</script>'];assert.match(renderInvestigation(run),/&lt;script&gt;/);assert.doesNotMatch(renderInvestigation(run),/<script>/);
});
test('distribution comparisons retain measured populations, all five inputs and explicit descriptive limits',()=>{
 const data=distributionFixture(),html=renderDistributions(data,'origin');assert.match(html,/1,611,046/);assert.match(html,/597,574/);assert.match(html,/Jensen–Shannon/);assert.match(html,/No significance test/);assert.match(html,/No live alert/);assert.match(renderDistributions(data,'origin',true),/Signed change/);assert.throws(()=>renderDistributions(data,'unknown'));
});
test('distribution arithmetic rejects fabricated alerts, counts and distances and escapes source text',()=>{
 let data=distributionFixture();data.features.carrier.total_variation=1;assert.throws(()=>validateDistributions(data));data=distributionFixture();data.features.origin.categories[0].comparison_count++;assert.throws(()=>validateDistributions(data));data=distributionFixture();data.alert_threshold=.1;assert.throws(()=>validateDistributions(data));data=distributionFixture();data.limitations=['<script>unsafe</script>'];const html=renderDistributions(data);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('distribution proxy is a fixed authenticated read without a profiling request',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/input-distributions');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});const url=`http://127.0.0.1:${frontend}/api/v1/research/input-distributions`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});
test('security counts and receipts preserve current-session scope and require fresh consistent observations',()=>{
 const data=securityFixture(),now=Date.parse(data.checked_at);assert.match(renderSecurity(data,now),/Other active sessions/);assert.throws(()=>validateSecurity({...data,other_active_sessions:3},now));assert.throws(()=>validateSecurity(data,now+90001));assert.throws(()=>validateSecurity(data,now-5001));assert.throws(()=>validateSecurity({...data,current_expires_at:data.checked_at},now));
 const receipt={...data,active_sessions:1,other_active_sessions:0,revoked_other_sessions:2,current_session_preserved:true};assert.match(renderSecurity(receipt,now),/2 other active sessions signed out/);assert.throws(()=>validateSecurity({...receipt,current_session_preserved:false},now));assert.throws(()=>validateSecurity(data,now,true));
});
test('security rejects untrusted scope and renders only validated numbers and dates',()=>{
 const data=securityFixture(),now=Date.parse(data.checked_at);assert.throws(()=>renderSecurity({...data,active_sessions:'<script>'},now));assert.throws(()=>renderSecurity({...data,current_expires_at:'<script>'},now));assert.throws(()=>renderSecurity({...data,scope:'all_accounts'},now));assert.throws(()=>renderSecurity({...data,production_ready:true},now));
 assert.doesNotMatch(renderSecurity({...data,unexpected:'<script>'},now),/<script>/);
});
test('security proxy forwards only fixed self-session endpoints with scoped cookie and CSRF',async t=>{
 const backend=await serve(t,async(req,res)=>{assert.equal(req.headers.cookie,'ain_session=fixture');if(req.method==='POST'){assert.equal(req.url,'/api/v1/auth/revoke-other-sessions');assert.equal(req.headers['x-csrf-token'],'fixture-csrf');let body='';for await(const c of req)body+=c;assert.equal(body,'{"acknowledged":true}');}else assert.equal(req.url,'/api/v1/auth/security');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,backend)){res.writeHead(404);res.end();}});const base=`http://127.0.0.1:${frontend}`,headers={Cookie:'ain_session=fixture; unrelated=secret','Content-Type':'application/json','X-CSRF-Token':'fixture-csrf'};
 assert.equal((await fetch(base+'/api/v1/auth/security',{headers})).status,200);assert.equal((await fetch(base+'/api/v1/auth/revoke-other-sessions',{method:'POST',headers,body:'{"acknowledged":true}'})).status,200);
 assert.equal((await fetch(base+'/api/v1/auth/security?user_id=other')).status,422);assert.equal((await fetch(base+'/api/v1/auth/security',{method:'POST'})).status,405);assert.equal((await fetch(base+'/api/v1/auth/revoke-other-sessions')).status,405);
});
test('security audit proxy allows only the fixed read and strips unrelated cookies',async t=>{
 let calls=0;
 const backend=await serve(t,(req,res)=>{calls++;assert.equal(req.url,'/api/v1/research/security-audit');assert.equal(req.method,'GET');assert.equal(req.headers.cookie,'ain_session=fixture');assert.equal(req.headers['x-role'],undefined);res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,backend)){res.writeHead(404);res.end();}});
 const url=`http://127.0.0.1:${frontend}/api/v1/research/security-audit`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=private','X-Role':'admin'}})).status,200);
 assert.equal((await fetch(url+'?limit=1')).status,422);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal(calls,1);
});
test('archive canonical queries preserve literal search and exact 64-bit cursor strings',()=>{
 const q=archiveQuery(new URLSearchParams({q:' %_ 航空 ',state:'failed',before:'9223372036854775806',through:'9223372036854775807'}));assert.equal(q.get('q'),'%_ 航空');assert.equal(q.get('before'),'9223372036854775806');
 for(const query of ['q=a&q=b','before=1','through=9223372036854775808','state=approved','url=private','q='+('x'.repeat(121))])assert.throws(()=>archiveQuery(new URLSearchParams(query)));
});
test('archive metadata is escaped and invalid scope or pagination is withheld',()=>{
 const data=archiveFixture();assert.match(renderArchive(data),/&lt;script&gt;/);assert.doesNotMatch(renderArchive(data),/<script>/);assert.throws(()=>validateArchive({...data,operational_approval:true}));assert.throws(()=>validateArchive({...data,next_before:'2'}));assert.throws(()=>validateArchive({...data,runs:[...data.runs,...data.runs]}));
 assert.match(renderArchive({...data,runs:[]}),/No saved investigations match/);
});
test('archive proxy validates fixed read queries and strips unrelated cookies',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/agent-archive?q=%25_&state=failed');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,backend)){res.writeHead(404);res.end();}});const url=`http://127.0.0.1:${frontend}/api/v1/research/agent-archive`;
 assert.equal((await fetch(url+'?q=%25_&state=failed',{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);assert.equal((await fetch(url+'?q=a&q=b')).status,422);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});
const routeAgentFixture=()=>({research_only:true,operational_approval:false,state:'awaiting_review',request:{objective:'Compare the explicit historical route.',month:'2025-05',include_simulation:false,route:{origin:'JFK',destination:'LAX'}},steps:[{id:'T1',tool:'route_history',state:'completed',arguments:{origin:'JFK',destination:'LAX'},observation:{available:true,data_kind:'historical_route',evidence_text:'Recorded historical US route evidence for JFK to LAX.',profile:routeHistoryFixture()}}],claims:[],reviews:[],run_id:'fixture',actor:'fixture',updated_at:'2026-11-20',runtime:'fixture'});
test('agent route payload is explicit, scoped and still limited to three required tools',()=>{
  const input={objective:'Compare historical research evidence.',month:'2025-05',simulation:false,requireFlights:true,requireKnowledge:false,requireSimulation:false,documentScope:'',routeEnabled:false,routeOrigin:'jfk',routeDestination:'lax'};
  assert.ok(!Object.hasOwn(investigationPayload(input),'route'));
  const payload=investigationPayload({...input,routeEnabled:true});
  assert.deepEqual(payload.route,{origin:'JFK',destination:'LAX'});assert.ok(payload.required_tools.includes('route_history'));
  assert.throws(()=>investigationPayload({...input,routeEnabled:true,simulation:true,requireFlights:true,requireKnowledge:true,requireSimulation:true}));
  assert.throws(()=>investigationPayload({...input,routeEnabled:true,routeDestination:'JFK'}));
});
test('saved agent report retains structured route counts and intervals without generated claims',()=>{
  const run=routeAgentFixture(),html=renderInvestigation(run);
  assert.match(html,/Structured route evidence/);assert.match(html,/2,325/);assert.match(html,/95% Wilson/);assert.match(html,/independent of the generated/);
  run.steps[0].observation.profile.route.origin='SFO';
  assert.match(renderInvestigation(run),/Route evidence could not be verified and has been withheld/);
  assert.doesNotMatch(renderInvestigation(run),/2,325/);
});
test('agent quality shows route scope mismatch and escapes its source identifier',()=>{
  const run=routeAgentFixture();run.quality={passed:false,missing_tools:[],failed_steps:[],unavailable_steps:[],document_scope_mismatches:[],invalid_claims:[],route_scope_mismatches:['<script>'],covered_sources:0,available_sources:1};
  const html=renderInvestigation(run);assert.match(html,/Route scope or arithmetic mismatch/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('route history presents source counts, nominal uncertainty and descriptive change',()=>{
  const data=routeHistoryFixture(),html=renderRouteHistory(data);
  assert.match(html,/JFK to LAX/);assert.match(html,/2,325/);assert.match(html,/\+2\.1 pp/);
  assert.match(html,/95% Wilson interval/);assert.match(html,/does not assign a cluster/);
  assert.match(html,/not a significance or causal finding/);
});
test('route history rejects false claims, missing intervals and unsafe route content',()=>{
  const data=routeHistoryFixture();
  assert.throws(()=>validateRouteHistory({...data,production_ready:true}));
  assert.throws(()=>validateRouteHistory({...data,group_assignment:1}));
  assert.throws(()=>validateRouteHistory({...data,delay_15_change_percentage_points:99}));
  const missing=structuredClone(data);missing.periods[1].delay_15.wilson_95=null;assert.throws(()=>renderRouteHistory(missing));
  data.route.origin='<script>';assert.throws(()=>renderRouteHistory(data));
  const absent=routeHistoryFixture(),row=absent.periods[1];
  for(const key of ['flights','completed','delayed_15','delayed_60','cancelled','diverted','missing_arrival'])row[key]=0;
  row.available=false;row.meets_support=false;row.mean_positive_delay_capped_180=null;
  for(const key of ['delay_15','delay_60','cancellation'])row[key]={events:0,observations:0,rate:null,wilson_95:null};
  absent.comparison_support_met=false;absent.delay_15_change_percentage_points=null;
  assert.match(renderRouteHistory(absent),/Rates are unavailable/);assert.match(renderRouteHistory(absent),/Insufficient support/);
});
test('route history proxy forwards only bounded canonical airport parameters',async t=>{
  let calls=0;
  const backend=await serve(t,(req,res)=>{calls++;assert.equal(req.url,'/api/v1/research/route-profile?origin=JFK&destination=LAX');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{"research_only":true}');});
  const frontend=await serve(t,async(req,res)=>{const pathname=new URL(req.url,'http://127.0.0.1').pathname;if(!await proxyResearchRequest(req,res,pathname,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/route-profile`;
  assert.equal((await fetch(url+'?destination=LAX&origin=JFK',{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);
  for(const suffix of ['','?origin=JFK','?origin=JFK&destination=JFK','?origin=jfk&destination=LAX','?origin=JFK&destination=LAX&limit=100','?origin=JFK&origin=AAA&destination=LAX'])assert.equal((await fetch(url+suffix)).status,422);
  assert.equal((await fetch(url+'?origin=JFK&destination=LAX',{method:'POST'})).status,405);
  assert.equal(calls,1);
});

function patternsFixture(){
  const r=JSON.parse(fs.readFileSync(new URL('../docs/reports/Route_Segments_v1.json',import.meta.url),'utf8'));
  return {format:'ain-route-patterns-v1',integrity_verified:true,research_only:true,production_ready:false,selected_k:r.selected_k,recorded_at:r.checked_at,report_sha256:'0'.repeat(64),training_silhouette:r.candidates[0].training_silhouette,minimum_training_seed_ari:1,coverage:r.coverage,profiles:r.profiles,overlapping_routes:2447,changed_routes:875,transition_counts:[[1006,684],[191,566]],evaluation_routes_outside_training_support:910};
}
test('route pattern periods show reconciled recorded evidence and explicit temporal limits',()=>{
  const data=patternsFixture();
  assert.match(renderPatterns(data),/35.8% changed groups/);
  assert.match(renderPatterns(data),/1,705 routes/);
  assert.match(renderPatterns(data,'evaluation'),/1,734 routes/);
  assert.match(renderPatterns(data,'evaluation'),/May 2025/);
  assert.match(renderPatterns(data),/not accuracy/);
  assert.match(renderPatterns(data),/not live recalculation/);
  assert.throws(()=>renderPatterns(data,'unexpected'));
});
test('route patterns fail closed on false claims, inconsistent totals and unsafe numeric content',()=>{
  const data=patternsFixture();
  assert.throws(()=>validatePatterns({...data,production_ready:true}));
  assert.throws(()=>validatePatterns({...data,integrity_verified:false}));
  assert.throws(()=>validatePatterns({...data,changed_routes:1}));
  data.profiles.train[0].unweighted_mean_route_features.delay_15_rate='<script>';
  assert.throws(()=>renderPatterns(data));
});
test('route segmentation proxy is a fixed authenticated read-only route',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/route-segments');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{"research_only":true}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/route-segments`;
  assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);
  assert.equal((await fetch(url,{method:'POST'})).status,405);
  assert.equal((await fetch(url+'/arbitrary')).status,404);
});

test('rollback receipt stays separate from live release qualification and escapes revisions',()=>{
  const data={production_ready:false,recovery:{recorded:false,production_qualified:false},rollback_drill:{recorded:true,production_qualified:false,flight_records:100,checked_at:'2026-11-20',candidate_revision:'<script>',rollback_revision:'previous'}};
  const html=renderPlatform(data);
  assert.match(html,/Isolated application rollback drill recorded/);
  assert.match(html,/main deployment was not rolled back/);
  assert.match(html,/&lt;script&gt;/);
  assert.throws(()=>renderPlatform({...data,rollback_drill:{...data.rollback_drill,production_qualified:true}}));
});

test('background job proxy acknowledges submission and permits only fixed UUID reads',async t=>{
  const backend=await serve(t,(req,res)=>{res.setHeader('Content-Type','application/json');if(req.method==='POST'){assert.equal(req.headers['idempotency-key'],'fixture-job-key');res.writeHead(202);res.end('{"state":"queued"}');}else{assert.equal(req.url,'/api/v1/research/agent-jobs/11111111-1111-4111-8111-111111111111');res.end('{"state":"running"}');}});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const base=`http://127.0.0.1:${frontend}/api/v1/research/agent-jobs`;
  assert.equal((await fetch(base,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':'fixture-job-key'},body:'{}'})).status,202);
  assert.equal((await fetch(base+'/11111111-1111-4111-8111-111111111111')).status,200);
  assert.equal((await fetch(base+'/arbitrary-destination')).status,404);
  assert.equal((await fetch(base+'/11111111-1111-4111-8111-111111111111',{method:'POST'})).status,405);
});

test('queued investigation rendering offers no report approval claim',()=>{
  const run={state:'queued',execution:'local-background-queue-v1',research_only:true,operational_approval:false,steps:[],claims:[],reviews:[],request:{objective:'Fixture queued investigation',month:'2025-05',include_simulation:false},run_id:'fixture',actor:'fixture',updated_at:'2026-11-20',runtime:'bounded-ollama-tools-v2'};
  const html=renderInvestigation(run);
  assert.match(html,/Saved background job/);
  assert.match(html,/current call is not forcibly interrupted/);
  assert.doesNotMatch(html,/Coverage checks passed/);
});

function readinessFixture(){
  const data=JSON.parse(fs.readFileSync(new URL('../infra/readiness.json',import.meta.url),'utf8'));
  return {...data,total:24,production_accepted:0,production_open:24,source_revision:'main',checked_at:'2026-11-20T00:00:00Z',requirements:data.requirements.map(r=>({...r,assessment_state:r.evidence.length?'local_evidence':'planned',evidence:r.evidence.map(e=>({...e,integrity_verified:true,url:'https://github.com/zenithdevelopers7-source/aviation-intelligence-nexus/blob/main/'+e.path}))}))};
}

test('readiness keeps all requirements open and filters progress without accepting production',()=>{
  const data=readinessFixture();
  assert.equal(filterReadiness(data,'','planned').length,1);
  assert.equal(filterReadiness(data,'P20').length,1);
  assert.equal(filterReadiness(data,'nothing matches this phrase').length,0);
  const html=renderReadiness(data,'P20');
  assert.match(html,/1 of 24 requirements shown/);
  assert.match(html,/Production acceptance/);
  assert.match(html,/<strong>Open<\/strong>/);
  assert.doesNotMatch(html,/%/);
  assert.throws(()=>renderReadiness({...data,production_ready:true}));
  assert.throws(()=>renderReadiness({...data,requirements:data.requirements.slice(1)}));
});

test('readiness escapes content and refuses unapproved evidence destinations',()=>{
  const data=readinessFixture();data.requirements[0].local_progress='<script>bad</script>';
  assert.match(renderReadiness(data),/&lt;script&gt;/);
  data.requirements[0].evidence[0].url='javascript:alert(1)';
  assert.throws(()=>renderReadiness(data));
});

test('readiness proxy forwards only a read and scoped session',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/readiness');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{"production_ready":false}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/readiness`;
  assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);
  assert.equal((await fetch(url,{method:'POST'})).status,405);
});

test('encrypted recovery evidence labels a separate local drill and rejects unsupported qualification',()=>{
  const data={production_ready:false,runtime:'local-container',recovery:{recorded:false,production_qualified:false},encrypted_backup_drill:{recorded:true,flight_records:100,checked_at:'<script>',independent_recovery_qualified:false,production_qualified:false}};
  const html=renderPlatform(data);
  assert.match(html,/Separate encrypted local recovery drill passed/);
  assert.match(html,/separate local drill/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/No independent key escrow/);
  assert.throws(()=>renderPlatform({...data,encrypted_backup_drill:{...data.encrypted_backup_drill,independent_recovery_qualified:true}}));
});

function monitoringFixture(){return structuredClone(JSON.parse(fs.readFileSync(new URL('../docs/reports/Monitoring_Integrity.json',import.meta.url),'utf8')).snapshots.healthy);}
test('monitoring renderer withholds expired health and rejects malformed transition metadata',()=>{
 const data=monitoringFixture(),now=Date.parse(data.checked_at);let html=renderMonitoring(data,90,now);
 assert.match(html,/Current component health is unknown/);assert.doesNotMatch(html,/Check passed/);
 data.transitions=[{at:'<script>',component:'database',state:'unavailable'}];assert.throws(()=>renderMonitoring(data));assert.throws(()=>renderMonitoring({...data,production_ready:true}));
});

test('monitoring route uses the authenticated proxy and rejects writes',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{"state":"unknown"}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/monitoring`;
  assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture'}})).status,200);
  assert.equal((await fetch(url,{method:'POST'})).status,405);
});

test('release configuration restricts backend hosts, binding and cookie namespaces',()=>{
  assert.equal(runtimeConfig({}).bindHost,'127.0.0.1');
  assert.throws(()=>runtimeConfig({AIN_BIND_HOST:'0.0.0.0'}));
  assert.equal(runtimeConfig({AIN_CONTAINER:'1',AIN_BIND_HOST:'0.0.0.0',AIN_API_HOST:'api',AIN_SESSION_COOKIE:'ain_release_session'}).apiHost,'api');
  assert.throws(()=>routing({apiHost:'example.com'}));assert.throws(()=>routing({sessionCookie:'unrelated_session'}));
});

test('platform rendering never invents restore evidence or production qualification',()=>{
  const state={production_ready:false,runtime:'local-native',database_ready:true,active_model_verified:false,ai_models_present:false,release_revision:'<unsafe>',schema_version:7,recovery:{recorded:false,production_qualified:false}};
  const html=renderPlatform(state);assert.ok(html.includes('No verified restore receipt'));assert.ok(html.includes('&lt;unsafe&gt;'));assert.ok(!html.includes('Recorded restore checks passed'));
  assert.throws(()=>renderPlatform({...state,production_ready:true}));
});

test('release proxy forwards only the isolated release cookie',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.headers.cookie,'ain_release_session=release_fixture');res.setHeader('Set-Cookie',['ain_release_session=new_fixture; HttpOnly; SameSite=Strict','ain_session=do_not_forward']);res.end('{}');});
  const frontend=await serve(t,async(req,res)=>{await proxyResearchRequest(req,res,req.url,backend,{sessionCookie:'ain_release_session'});});
  const response=await fetch(`http://127.0.0.1:${frontend}/api/v1/auth/session`,{headers:{Cookie:'ain_session=native_fixture; ain_release_session=release_fixture; unrelated=private_fixture'}});
  assert.equal(response.status,200);assert.equal(response.headers.getSetCookie().length,1);assert.ok(response.headers.getSetCookie()[0].startsWith('ain_release_session='));
});

test('dashboard readiness reports backend outage separately from liveness',async t=>{
  let failed=false;
  const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/health/ready');assert.equal(req.headers.cookie,undefined);res.writeHead(failed?503:200,{'Content-Type':'application/json'});res.end(JSON.stringify({status:failed?'not_ready':'ready'}));});
  const reservation=http.createServer();await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve));const port=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  const child=spawn(process.execPath,['scripts/dev.mjs'],{cwd:process.cwd(),env:{...process.env,PORT:String(port),AIN_API_PORT:String(backend)},windowsHide:true,stdio:['ignore','pipe','pipe']});t.after(()=>child.kill());
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Dashboard did not start')),5000);child.once('error',reject);child.stdout.on('data',chunk=>{if(chunk.toString().includes('AIN dashboard:')){clearTimeout(timer);resolve();}});});
  assert.equal((await fetch(`http://127.0.0.1:${port}/__ain/ready`)).status,200);failed=true;
  assert.equal((await fetch(`http://127.0.0.1:${port}/__ain/ready`)).status,503);assert.equal((await fetch(`http://127.0.0.1:${port}/__ain/health`)).status,200);
});

test('quality-blocked reports show only source extracts and escape missing-tool labels',()=>{
  const run={research_only:true,operational_approval:false,state:'awaiting_review',request:{objective:'Research report',month:'2025-05',include_simulation:false},finding_style:'verbatim_source_extracts',steps:[{id:'T1',tool:'flight_metrics',state:'completed',arguments:{},observation:{data_kind:'historical_bts',evidence_text:'An exact source quotation for the report.'}}],claims:[{text:'UNSUPPORTED INTERPRETATION',citation:'T1',quote:'An exact source quotation for the report.'}],reviews:[],runtime:'fixture',quality:{passed:false,covered_sources:1,available_sources:1,missing_tools:['<unsafe>'],failed_steps:[],unavailable_steps:[]}};
  const html=renderInvestigation(run);assert.ok(html.includes('Coverage checks blocked acceptance'));assert.ok(html.includes('&lt;unsafe&gt;'));assert.ok(!html.includes('UNSUPPORTED INTERPRETATION'));assert.ok(html.includes('verbatim source wording'));
});

test('investigation rendering escapes trace content and rejects unsupported claims',()=>{
  const run={research_only:true,operational_approval:false,state:'awaiting_review',request:{objective:'<unsafe>',month:'2025-05',include_simulation:false},steps:[{id:'T1',tool:'flight_metrics',state:'completed',arguments:{},observation:{data_kind:'historical_bts',evidence_text:'An exact source quotation for the report.'}}],claims:[{text:'<script>bad</script>',citation:'T1',quote:'An exact source quotation for the report.'}],reviews:[],runtime:'fixture'};
  const html=renderInvestigation(run);assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
  run.claims[0].citation='invented';assert.throws(()=>renderInvestigation(run));
});

test('knowledge renderer escapes evidence and rejects invented citations',()=>{
  const result={research_only:true,operational_approval:false,mode:'generated',question:'<script>question</script>',
    generation:{status:'completed',model:'local'},claims:[{text:'<img>claim',citation:'c1',quote:'A source quotation with enough text.'}],
    evidence:[{id:'c1',text:'A source quotation with enough text. <script>bad</script>',source:'docs/TEST.md',heading:'Test',start_line:1,end_line:2,source_sha256:'hash',source_url:'javascript:alert(1)'}]};
  const html=renderKnowledge(result);
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('javascript:'));
  result.claims[0].citation='invented';assert.throws(()=>renderKnowledge(result));
});

function fixture() {
  return { generated_at: '2025-06-01T12:00:00Z', source_scope: '<unsafe>',
    dataset: { records: 100, carriers: 2, first_date: '2025-01-01', last_date: '2025-05-31',
      monthly: [{ period: '2025-01', records: 100, cancelled: 2, diverted: 1 }] }, model: null };
}

test('render escapes response text and withholds unavailable model scores', () => {
  const rendered = renderResearchSummary(fixture());
  assert.ok(rendered.includes('&lt;unsafe&gt;'));
  assert.ok(!rendered.includes('<unsafe>'));
  assert.ok(rendered.includes('Model report unavailable'));
  assert.ok(rendered.includes('no operational predictions served'));
  const invalid = fixture(); invalid.dataset.records = null;
  assert.throws(() => renderResearchSummary(invalid));
});

test('prediction rendering requires research-only output and escapes warnings', () => {
  const result = { arrival_delay_15_probability: .25, research_only: true, operational_serving_approved: false,
    model_version: 'delay-v2', scenario: { carrier: 'AA', origin: 'JFK', destination: 'LAX', flight_date: '2025-05-15', scheduled_departure: '09:00' }, warnings: ['<unsafe>'] };
  assert.ok(renderPrediction(result).includes('25.0%'));
  assert.ok(renderPrediction(result).includes('&lt;unsafe&gt;'));
  assert.throws(() => renderPrediction({ ...result, arrival_delay_15_probability: 2 }));
  assert.throws(() => renderPrediction({ ...result, research_only: false }));
});

test('history shows empty state, escapes saved text and rejects invalid probabilities', () => {
  assert.ok(renderHistory([]).includes('No saved research runs yet'));
  const run = {run_id:'test',saved_at:'2026-01-01T00:00:00Z',scenario:{carrier:'<unsafe>',origin:'JFK',destination:'LAX',flight_date:'2025-05-15',scheduled_departure:'09:00'},model_version:'test',arrival_delay_15_probability:.2};
  assert.ok(renderHistory([run]).includes('&lt;unsafe&gt;'));
  assert.ok(renderHistory([run]).includes('20.0%'));
  assert.throws(()=>renderHistory([{...run,arrival_delay_15_probability:NaN}]));
});

test('gate sample and output keep synthetic scope and reject unchecked plans',()=>{
  const scenario=sampleGateScenario(20,true);
  assert.equal(scenario.data_kind,'synthetic');assert.equal(scenario.flights.length,5);assert.equal(scenario.gates.length,3);
  assert.ok(scenario.flights.every(f=>Object.keys(f.costs).length===3));
  assert.throws(()=>renderGatePlan({research_only:true,operational_approval:false,candidate:{verification:{feasible:false}}}));
});

test('auth proxy preserves the session cookie and CSRF while filtering unrelated credentials', async t=>{
  const backend=await serve(t,async(req,res)=>{
    if(req.url==='/api/v1/auth/login'){
      for await(const chunk of req){}
      res.setHeader('Set-Cookie','ain_session=fixturetoken; HttpOnly; Path=/api; SameSite=Strict');
    }else{
      assert.equal(req.headers.cookie,'ain_session=fixturetoken');
      assert.equal(req.headers.authorization,undefined);
      assert.equal(req.headers['x-csrf-token'],'fixture-csrf');
    }
    res.end('{"authenticated":true}');
  });
  const frontend=await serve(t,async(req,res)=>{await proxyResearchRequest(req,res,req.url,backend);});
  const login=await fetch(`http://127.0.0.1:${frontend}/api/v1/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  assert.ok(login.headers.get('set-cookie').includes('HttpOnly'));
  const session=await fetch(`http://127.0.0.1:${frontend}/api/v1/auth/session`,{headers:{Cookie:'unrelated=private; ain_session=fixturetoken',Authorization:'local-test-only','X-CSRF-Token':'fixture-csrf'}});
  assert.equal(session.status,200);
});

test('prediction proxy limits methods, media type and body size', async t => {
  let forwarded = 0;
  const backend = await serve(t, async (req, res) => {
    assert.equal(req.url, '/api/v1/research/predict');
    let body = ''; for await (const chunk of req) body += chunk;
    assert.equal(JSON.parse(body).carrier, 'AA');
    assert.equal(req.headers['idempotency-key'], '00000000-0000-4000-8000-000000000001');
    forwarded++; res.end('{"research_only":true}');
  });
  const frontend = await serve(t, async (req, res) => {
    await proxyResearchRequest(req, res, req.url, backend);
  });
  const url = `http://127.0.0.1:${frontend}/api/v1/research/predict`;
  assert.equal((await fetch(url)).status, 405);
  assert.equal((await fetch(url, { method: 'POST', body: '{}' })).status, 415);
  assert.equal((await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: 'x'.repeat(5000) })).status, 413);
  assert.equal(forwarded, 0);
  assert.equal((await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key':'00000000-0000-4000-8000-000000000001' }, body: '{"carrier":"AA"}' })).status, 200);
  assert.equal(forwarded, 1);
});

test('actual dashboard server routes prediction POST before static method checks', async t => {
  const backend = await serve(t, async (req, res) => {
    for await (const chunk of req) { /* Drain the small test request. */ }
    res.end('{"research_only":true}');
  });
  const reservation = http.createServer();
  await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve));
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  const child = spawn(process.execPath, ['scripts/dev.mjs'], {
    cwd: new URL('..', import.meta.url), windowsHide: true,
    env: { ...process.env, PORT: String(port), AIN_API_PORT: String(backend) }, stdio: ['ignore', 'pipe', 'pipe']
  });
  t.after(() => { child.kill(); });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Dashboard did not start')), 5000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', code => { clearTimeout(timer); reject(new Error(`Dashboard exited: ${code}`)); });
    child.stdout.on('data', chunk => {
      if (chunk.toString().includes('AIN dashboard:')) { clearTimeout(timer); resolve(); }
    });
  });
  const result = await fetch(`http://127.0.0.1:${port}/api/v1/research/predict`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"carrier":"AA"}'
  });
  assert.equal(result.status, 200);
  assert.equal((await result.json()).research_only, true);
  assert.equal((await fetch(`http://127.0.0.1:${port}/index.html`, { method: 'POST' })).status, 405);
});

async function serve(t, handler) {
  const server = http.createServer(handler);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }));
  return server.address().port;
}

test('proxy forwards only the read-only summary route and returns safe failures', async t => {
  let fail = false;
  const backend = await serve(t, (req, res) => {
    assert.equal(req.url, '/api/v1/research/summary');
    assert.equal(req.headers.authorization, undefined);
    res.setHeader('Content-Type', 'application/json');
    if (fail) { res.writeHead(503); res.end('{"error":"database_unavailable"}'); }
    else res.end(JSON.stringify(fixture()));
  });
  const frontend = await serve(t, async (req, res) => {
    if (!await proxyResearchRequest(req, res, req.url, backend)) { res.writeHead(404); res.end(); }
  });
  const url = `http://127.0.0.1:${frontend}`;
  let result = await fetch(url + '/api/v1/research/summary', { headers: { Authorization: 'local-test-only' } });
  assert.equal(result.status, 200);
  assert.equal((await result.json()).dataset.records, 100);
  assert.equal((await fetch(url + '/api/v1/research/summary', { method: 'POST' })).status, 405);
  assert.equal((await fetch(url + '/api/v1/model/report')).status, 404);
  fail = true;
  assert.equal((await fetch(url + '/api/v1/research/summary')).status, 503);
});

function diagnosticsFixture(){
  const r=JSON.parse(fs.readFileSync(new URL('../docs/reports/Delay_v2.json',import.meta.url),'utf8'));
  const summary=m=>({...m,binned_ece:m.calibration_bins.reduce((n,b)=>n+b.count*Math.abs(b.mean_probability-b.observed_rate),0)/m.records,false_alerts:m.confusion_matrix_labels_0_1[0][1],missed_delays:m.confusion_matrix_labels_0_1[1][0],alert_count:m.confusion_matrix_labels_0_1[0][1]+m.confusion_matrix_labels_0_1[1][1]});
  return {format:'ain-model-diagnostics-v1',integrity_verified:true,research_only:true,production_ready:false,report_sha256:'a'.repeat(64),threshold:r.threshold,periods:Object.fromEntries(['validation','test'].map(k=>[k,{model:summary(r[k].model),baseline:r[k].constant_training_prior}])),carriers:Object.fromEntries(Object.entries(r.test_by_carrier).map(([k,m])=>[k,summary(m)])),method:'Recorded evidence',limitations:r.limitations};
}
test('model diagnostics exposes fixed-threshold errors, calibration and supported cohorts',()=>{
  const data=diagnosticsFixture();const html=renderDiagnostics(data);
  assert.match(html,/241,732 false alerts/);assert.match(html,/36,371 missed delays/);assert.match(html,/4.09%/);assert.match(html,/0.6506/);
  assert.match(html,/No confidence intervals/);assert.match(renderDiagnostics(data,'validation'),/April 2025/);
  assert.match(renderDiagnostics(data,'test','AA'),/84,496/);
  assert.throws(()=>renderDiagnostics(data,'validation','AA'));assert.throws(()=>renderDiagnostics(data,'test','EK'));
});
test('diagnostics rejects inconsistent populations and escapes descriptive evidence',()=>{
  let data=diagnosticsFixture();data.periods.test.model.calibration_bins[0].bin='<img>';
  assert.throws(()=>validateDiagnostics(data));data=diagnosticsFixture();data.periods.test.model.false_alerts=0;assert.throws(()=>validateDiagnostics(data));
  data=diagnosticsFixture();data.carriers.AA.records=1;assert.throws(()=>validateDiagnostics(data));
  data=diagnosticsFixture();data.limitations=['<script>bad()</script>'];assert.match(renderDiagnostics(data),/&lt;script&gt;/);assert.doesNotMatch(renderDiagnostics(data),/<script>/);
});
test('model diagnostics proxy is authenticated, fixed and read-only',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/model-diagnostics');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/model-diagnostics`;
  assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);
  assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});

const explanationFixture=()=>({...JSON.parse(fs.readFileSync(new URL('../docs/reports/Delay_v2_Permutation.json',import.meta.url),'utf8')),integrity_verified:true,report_sha256:'a'.repeat(64)});
test('input reliance preserves exact measures, repeat variation and scope',()=>{
  const data=explanationFixture(),html=renderExplanations(data);
  assert.match(html,/Scheduled departure time/);assert.match(html,/\+0.02729/);assert.match(html,/not a confidence interval/);assert.match(html,/No May outcomes analyzed/);
  assert.match(renderExplanations(data,'roc_auc_decrease'),/\+0.09506/);assert.match(renderExplanations(data,'brier_increase'),/\+0.00815/);
  assert.throws(()=>renderExplanations(data,'individual_cause'));
});
test('input reliance rejects inconsistent evidence and supports negative signed measurements',()=>{
  let data=explanationFixture();data.groups[0].mean.log_loss_increase=99;assert.throws(()=>validateExplanations(data));
  data=explanationFixture();data.protocol.period='2025-05';assert.throws(()=>validateExplanations(data));
  data=explanationFixture();const row=data.groups[0];row.repeats.forEach(v=>v.log_loss_increase=-.01);row.mean.log_loss_increase=-.01;row.repeat_std.log_loss_increase=0;data.limitations=['<script>bad()</script>'];
  const html=renderExplanations(data);assert.match(html,/-0.01000/);assert.match(html,/explanation-negative/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('input reliance proxy forwards only fixed authenticated reads',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/model-explanations');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/model-explanations`;
  assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);
  assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});

const modelAgentFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Model_Agent_Integration.json',import.meta.url),'utf8')).run;
test('model investigation opt-in preserves old payloads and shared three-tool limit',()=>{
  const input={objective:'Review frozen model evidence.',month:'2025-05',simulation:false,requireFlights:true,requireKnowledge:true,requireSimulation:false,routeEnabled:false,includeModelEvidence:false};
  assert.ok(!Object.hasOwn(investigationPayload(input),'include_model_evidence'));
  input.includeModelEvidence=true;const payload=investigationPayload(input);assert.equal(payload.include_model_evidence,true);assert.ok(payload.required_tools.includes('model_evidence'));assert.equal(payload.required_tools.length,3);
  assert.throws(()=>investigationPayload({...input,routeEnabled:true,routeOrigin:'JFK',routeDestination:'LAX'}),/at most three/);
});
test('saved structured model evidence survives omitted extracts and withholds invalid scope or counts',()=>{
  let run=modelAgentFixture();run.claims=[];let html=renderInvestigation(run);assert.match(html,/241,732/);assert.match(html,/4.09%/);assert.match(html,/Scheduled departure time/);assert.match(html,/not a confidence interval/);
  run.request.include_model_evidence=false;assert.match(renderInvestigation(run),/has been withheld/);
  run=modelAgentFixture();run.steps[0].arguments={period:'2025-05'};assert.match(renderInvestigation(run),/has been withheld/);
  run=modelAgentFixture();run.steps[0].observation.snapshot.periods.test.false_alerts=0;assert.throws(()=>validateModelSnapshot(run.steps[0].observation));assert.match(renderInvestigation(run),/has been withheld/);
});
test('model snapshot warnings and descriptive evidence are escaped and mismatch blocks display',()=>{
  let run=modelAgentFixture();run.steps[0].observation.snapshot.limitations=['<script>bad()</script>'];const html=renderModelSnapshot(run.steps[0].observation);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  run=modelAgentFixture();run.quality.model_evidence_mismatches=[run.steps[0].id];assert.match(renderInvestigation(run),/has been withheld/);
  run.quality.model_limitations_uncited=['<img>'];assert.match(renderInvestigation(run),/Required model limitation quotation missing: &lt;img&gt;/);
});

const operationsFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Agent_Operations_Dashboard.json',import.meta.url),'utf8')).fixture;
test('operations distinguishes retained totals, recent tool time and saved coverage flags',()=>{
  const data=operationsFixture(),html=renderOperations(data,Date.parse(data.checked_at)+1000);
  assert.equal(data.total_background_runs,7);assert.match(html,/Local worker: active/);assert.match(html,/2.0 minutes/);assert.match(html,/p95 30.00 ms/);assert.match(html,/does not recompute them or measure semantic accuracy/);assert.match(html,/exclude queue waiting, model planning/);assert.match(html,/Synchronous engineering runs are excluded/);
  assert.match(html,/Not reported by this snapshot/);data.recent_window.tools.distribution_evidence={attempted:0,completed:0,failed_or_unfinished:0};assert.match(renderOperations(data,Date.parse(data.checked_at)+1000),/Recorded input distributions/);
});
test('operations hides stale observations and rejects inconsistent counters or timings',()=>{
  let data=operationsFixture();const html=renderOperations(data,Date.parse(data.checked_at)+91000);assert.match(html,/snapshot is stale/);assert.doesNotMatch(html,/Local worker: active/);
  data.total_background_runs=0;assert.throws(()=>validateOperations(data));data=operationsFixture();data.recent_window.tools.model_evidence.completed=99;assert.throws(()=>validateOperations(data));
  data=operationsFixture();data.recent_window.tool_time.p95_ms=NaN;assert.throws(()=>validateOperations(data));data=operationsFixture();data.worker.state='<script>';assert.throws(()=>validateOperations(data));
});
test('operations proxy is fixed, read-only and strips unrelated cookies',async t=>{
  const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/agent-operations');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/agent-operations`;
  assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);
  assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});

const gateReviewFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Gate_Proposal_Review.json',import.meta.url),'utf8'));
test('gate review is limited by role, exact pending scope and expiry boundary',()=>{
  const run=gateReviewFixture().pending,now=Date.parse(run.saved_at)+1000;
  assert.equal(gateReviewEligible(run,{role:'researcher'},now),true);assert.equal(gateReviewEligible(run,{role:'admin'},now),true);
  assert.equal(gateReviewEligible(run,{role:'viewer'},now),false);assert.equal(gateReviewEligible(run,{role:'admin'},Date.parse(run.review_expires_at)),false);
  assert.equal(gateReviewEligible({...run,review_status:{state:'legacy',eligible:false}},{role:'admin'},now),false);
  assert.throws(()=>renderGatePlan({...run,review_status:{state:'invalid'}}),/integrity/);
});
test('gate review retains proposal and decision fingerprints and escapes review notes',()=>{
  const run=gateReviewFixture().reviewed;run.review.note='<script>bad()</script>';const html=renderGateReview(run);
  assert.match(html,/Reviewed as research/);assert.match(html,/Decision SHA-256/);assert.match(html,/Exact proposal fingerprint/);assert.match(html,/not independent approval/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  assert.match(renderGateReview({...run,review:null,review_status:{state:'legacy',eligible:false}}),/Compute a new proposal/);
});
test('gate review proxy forwards bounded Unicode notes, session and CSRF only to fixed writes',async t=>{
  const note='🚀'.repeat(1000),body=JSON.stringify({note,acknowledged:true});
  const backend=await serve(t,async(req,res)=>{assert.equal(req.url,'/api/v1/research/gate-review');assert.equal(req.headers.cookie,'ain_session=fixture');assert.equal(req.headers['x-csrf-token'],'fixture-csrf');let received='';for await(const chunk of req)received+=chunk;assert.equal(received,body);res.setHeader('Content-Type','application/json');res.end('{}');});
  const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});
  const url=`http://127.0.0.1:${frontend}/api/v1/research/gate-review`;
  assert.equal((await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','Cookie':'ain_session=fixture; unrelated=secret','X-CSRF-Token':'fixture-csrf'},body})).status,200);
  assert.equal((await fetch(url)).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});

function qualityFixture(){
 const r=JSON.parse(fs.readFileSync(new URL('../docs/reports/BTS_Data_Quality.json',import.meta.url),'utf8')),d=JSON.parse(fs.readFileSync(new URL('../docs/reports/BTS_Jan_May_2025_Dataset_v2.json',import.meta.url),'utf8'));
 const eligible=Object.fromEntries(r.months.map(m=>[m.period,m.cohorts.eligible_arrivals]));
 return {...r,integrity_verified:true,report_sha256:'a'.repeat(64),dataset_report_sha256:'b'.repeat(64),modelling_alignment:Object.fromEntries(Object.entries(d.period_groups).map(([key,periods])=>{const n=periods.reduce((n,p)=>n+eligible[p],0),frozen=d.splits[key].eligible_records;return [key,{audited_eligible:n,frozen_eligible:frozen,counts_match:n===frozen}];}))};
}

test('a running stop request is acknowledged without claiming immediate cancellation',()=>{
 const run=modelAgentFixture();run.state='running';run.claims=[];delete run.report_sha256;delete run.quality;run.cancel_requested_at='2026-11-20T12:00:00Z';
 const html=renderInvestigation(run);assert.match(html,/Stop requested/);assert.match(html,/current bounded call may finish/);assert.match(html,/running · research only/);assert.doesNotMatch(html,/Report SHA-256/);
});

test('a cancelled investigation retains completed evidence with no reviewable draft',()=>{
 const run=modelAgentFixture();run.state='cancelled';run.claims=[];delete run.report_sha256;delete run.quality;run.cancel_requested_at='2026-11-20T12:00:00Z';
 const html=renderInvestigation(run);assert.match(html,/Stop completed/);assert.match(html,/Completed tool evidence is retained/);assert.match(html,/241,732/);assert.doesNotMatch(html,/Report SHA-256/);
});

test('terminal interrupted stop requests do not claim completed cancellation',()=>{
 const run=modelAgentFixture();run.state='interrupted';run.claims=[];delete run.report_sha256;delete run.quality;run.cancel_requested_at='2026-11-20T12:00:00Z';run.error='<script>untrusted</script>';
 const html=renderInvestigation(run);assert.match(html,/request was recorded/);assert.doesNotMatch(html,/Stop completed|<script>/);assert.match(html,/&lt;script&gt;/);
});
test('data quality exposes full release counts, exclusion populations and recorded lineage',()=>{
 const data=qualityFixture(),html=renderQuality(data);assert.match(html,/2,835,101/);assert.match(html,/1,611,046/);assert.match(html,/597,574/);assert.match(html,/not reopen archive files/);assert.match(html,/Not a live database check/);
 assert.match(renderQuality(data,'2025-01'),/2025-01 · Structural checks/);assert.throws(()=>renderQuality(data,'2026-01'));
});
test('data quality rejects inconsistent cohorts and false pass claims and escapes limitations',()=>{
 let data=qualityFixture();data.months[0].cohorts.eligible_arrivals=0;assert.throws(()=>validateQuality(data));data=qualityFixture();data.checks_passed=false;assert.throws(()=>validateQuality(data));
 data=qualityFixture();data.months[0].import_reconciliation='mismatched';assert.throws(()=>validateQuality(data));data=qualityFixture();data.limitations=['<script>bad()</script>'];const html=renderQuality(data);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('data quality proxy is fixed read-only and forwards only the session cookie',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/data-quality');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}});const url=`http://127.0.0.1:${frontend}/api/v1/research/data-quality`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/arbitrary')).status,404);
});

const withdrawalFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Sharing_Withdrawal.json',import.meta.url),'utf8'));
test('sharing withdrawal requires exact pending sharing context and hides review after withdrawal',()=>{
 const fixture=withdrawalFixture(),user={id:'fixture',role:'viewer'};
 assert.equal(canWithdrawSharing(fixture.pending,user),true);assert.equal(canWithdrawSharing(fixture.peer_view,user),false);
 assert.equal(canWithdrawSharing(fixture.withdrawn,user),false);assert.equal(canWithdrawSharing(fixture.pending,null),false);
 assert.equal(canWithdrawSharing({...fixture.pending,report_sha256:'invalid'},user),false);
 assert.equal(canWithdrawSharing({...fixture.pending,request:{}},user),false);
 assert.equal(canReviewInvestigation(fixture.withdrawn,{role:'admin'}),false);
 fixture.withdrawn.sharing_withdrawal.note='<script>bad()</script>';const html=renderInvestigation(fixture.withdrawn);
 assert.match(html,/Sharing withdrawn by/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|human review required/);assert.match(html,/exported copies cannot be recalled/);
});
test('withdrawn archive state is supported while older operations snapshots do not imply zero withdrawals',()=>{
 assert.match(archiveQuery(new URLSearchParams({state:'withdrawn'})).toString(),/state=withdrawn/);
 const fixture=operationsFixture();assert.match(renderOperations(fixture,Date.parse(fixture.checked_at)),/Sharing withdrawn<\/th><td>Not reported/);
 fixture.totals.withdrawn=1;fixture.total_background_runs++;assert.match(renderOperations(fixture,Date.parse(fixture.checked_at)),/Sharing withdrawn<\/th><td>1/);
});
test('sharing withdrawal proxy forwards bounded writes and only the session cookie',async t=>{
 const body=JSON.stringify({note:'End fixture sharing.',acknowledged:true});let writes=0;
 const backend=await serve(t,async(req,res)=>{writes++;assert.equal(req.url,'/api/v1/research/agent-withdraw-sharing');assert.equal(req.headers.cookie,'ain_session=fixture');assert.equal(req.headers['x-csrf-token'],'fixture-csrf');let received='';for await(const chunk of req)received+=chunk;assert.equal(received,body);res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url,backend)){res.writeHead(404);res.end();}}),url=`http://127.0.0.1:${frontend}/api/v1/research/agent-withdraw-sharing`;
 const headers={'Content-Type':'application/json',Cookie:'ain_session=fixture; unrelated=secret','X-CSRF-Token':'fixture-csrf'};
 assert.equal((await fetch(url,{method:'POST',headers,body})).status,200);assert.equal((await fetch(url)).status,405);
 assert.equal((await fetch(url,{method:'POST',headers,body:'x'.repeat(4097)})).status,413);assert.equal((await fetch(url+'/arbitrary')).status,404);assert.equal(writes,1);
});

const thresholdFixture=()=>({...JSON.parse(fs.readFileSync(new URL('../docs/reports/April_Threshold_Tradeoffs.json',import.meta.url),'utf8')),report_sha256:'a'.repeat(64),integrity_verified:true});
test('threshold scenarios reconcile costs, capacity, baselines and undefined precision',()=>{
 const r=thresholdFixture(),s=tradeoffScenario(r,{threshold:17,falseAlertCost:1,missedDelayCost:5,capacityPercent:25});
 assert.equal(s.selected.fp,243401);assert.equal(s.selected.fn,31539);assert.equal(s.selected.cost_per_1000,1000*(243401+31539*5)/577730);assert.equal(s.selected.within_capacity,false);assert.equal(s.no_alerts.precision,null);assert.equal(s.no_alerts.alerts,0);
 const zero=tradeoffScenario(r,{threshold:0,falseAlertCost:0,missedDelayCost:0,capacityPercent:100});assert.equal(zero.selected.cost_per_1000,0);assert.equal(zero.selected.within_capacity,true);assert.equal(zero.selected.alerts,r.records);
 assert.equal(tradeoffScenario(r,{threshold:100}).selected.alerts,0);assert.match(renderTradeoffs(r),/243,401/);assert.match(renderTradeoffs(r),/Not defined/);
});
test('threshold evidence rejects inconsistent populations and invalid assumptions and escapes limitations',()=>{
 for(const assumptions of [{threshold:17.5},{falseAlertCost:NaN},{missedDelayCost:-1},{capacityPercent:101},{falseAlertCost:'1'}])assert.throws(()=>tradeoffScenario(thresholdFixture(),assumptions));
 let r=thresholdFixture();r.rows[1].tp++;assert.throws(()=>validateTradeoffs(r));r=thresholdFixture();r.period='2025-05';assert.throws(()=>validateTradeoffs(r));r=thresholdFixture();r.rows.reverse();assert.throws(()=>validateTradeoffs(r));
 r=thresholdFixture();r.limitations[0]='<script>bad()</script>';const html=renderTradeoffs(r);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/No automatic threshold selection/);
});
test('threshold evidence proxy is fixed read-only, rejects query overrides and strips unrelated cookies',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/threshold-tradeoffs');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url.split('?')[0],backend)){res.writeHead(404);res.end();}}),url=`http://127.0.0.1:${frontend}/api/v1/research/threshold-tradeoffs`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'?period=2025-05')).status,422);assert.equal((await fetch(url+'/arbitrary')).status,404);
});
const durationFixture=()=>({...JSON.parse(fs.readFileSync(new URL('../docs/reports/Delay_Duration_v1.json',import.meta.url),'utf8')),integrity_verified:true,report_sha256:'a'.repeat(64)});
test('duration evaluation distinguishes regression, failed research checks, baselines and severe errors',()=>{
 const r=durationFixture(),html=renderDuration(r);assert.match(html,/Did not pass/);assert.match(html,/55.67/);assert.match(html,/18.16/);assert.match(html,/124.55/);assert.match(html,/not accuracy/);assert.match(html,/no duration inference|No duration inference/);assert.match(html,/globally untouched/);
 assert.match(renderDuration(r,'validation','mae'),/Median baseline comparison/);assert.throws(()=>renderDuration(r,'train'));assert.throws(()=>renderDuration(r,'test','accuracy'));
});
test('duration evaluation validates arithmetic and rejects false success while escaping source text',()=>{
 let r=durationFixture();r.research_check.passed=true;assert.throws(()=>validateDuration(r));r=durationFixture();r.test.model.rmse=1;assert.throws(()=>validateDuration(r));r=durationFixture();r.test.residual_histogram.counts[0]++;assert.throws(()=>validateDuration(r));
 r=durationFixture();r.limitations[0]='<script>bad()</script>';const html=renderDuration(r);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);assert.ok(r.test.training_mean_baseline.r2<0);assert.doesNotThrow(()=>validateDuration(r));
});
test('duration evidence proxy permits only fixed authenticated reads without query overrides',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/duration-evaluation');assert.equal(req.headers.cookie,'ain_session=fixture');res.setHeader('Content-Type','application/json');res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,req.url.split('?')[0],backend)){res.writeHead(404);res.end();}}),url=`http://127.0.0.1:${frontend}/api/v1/research/duration-evaluation`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret'}})).status,200);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'?target=anything')).status,422);assert.equal((await fetch(url+'/arbitrary')).status,404);
});
const durationAgentFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Duration_Agent_Integration.json',import.meta.url),'utf8')).run;
test('duration agent opt-in preserves old payloads and consumes one of three tool slots',()=>{
 const input={objective:'Review the frozen negative duration experiment.',month:'2025-05',simulation:false,requireFlights:false,requireKnowledge:false};
 assert.equal(Object.hasOwn(investigationPayload(input),'include_duration_evidence'),false);input.includeDurationEvidence=true;assert.deepEqual(investigationPayload(input).required_tools,['duration_evidence']);assert.equal(investigationPayload(input).include_duration_evidence,true);
 assert.equal(investigationPayload({...input,requireFlights:true,requireKnowledge:true}).required_tools.length,3);assert.throws(()=>investigationPayload({...input,requireFlights:true,requireKnowledge:true,includeModelEvidence:true}),/at most three/);
});
test('duration agent retains negative evidence beyond extracts and withholds changed scope or approval',()=>{
 let run=durationAgentFixture();run.claims=[];let html=renderInvestigation(run);assert.match(html,/55.67/);assert.match(html,/124.55/);assert.match(html,/failed its fixed research check/);assert.match(html,/not a group identified prospectively/);
 run.request.include_duration_evidence=false;assert.match(renderInvestigation(run),/duration evidence could not be verified/);run=durationAgentFixture();run.steps[0].arguments={model_path:'private'};assert.match(renderInvestigation(run),/duration evidence could not be verified/);
 run=durationAgentFixture();run.quality.duration_evidence_mismatches=['T1'];assert.match(renderInvestigation(run),/duration evidence could not be verified/);run=durationAgentFixture();run.steps[0].observation.snapshot.evaluation.research_check.passed=true;assert.throws(()=>validateDurationSnapshot(run.steps[0].observation));
 run=durationAgentFixture();run.steps[0].observation.snapshot.evaluation.limitations[0]='<script>bad()</script>';html=renderDurationSnapshot(run.steps[0].observation);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('operations distinguishes duration tool counts from older unreported snapshots',()=>{
 const r=operationsFixture();let html=renderOperations(r,Date.parse(r.checked_at));assert.match(html,/Recorded duration regression<\/th><td colspan="3">Not reported by this snapshot/);
 r.recent_window.tools.distribution_evidence={attempted:0,completed:0,failed_or_unfinished:0};assert.doesNotThrow(()=>validateOperations(r));r.recent_window.tools.duration_evidence={attempted:1,completed:1,failed_or_unfinished:0};html=renderOperations(r,Date.parse(r.checked_at));assert.match(html,/Recorded duration regression<\/th><td>1<\/td><td>1/);
 r.recent_window.tools.duration_evidence.completed=2;assert.throws(()=>validateOperations(r));
});

test('monitoring validates complete health evidence and finite bounded latency windows',()=>{
 const r=monitoringFixture();assert.doesNotThrow(()=>validateMonitoring(r));
 for(const change of [v=>v.components.database=false,v=>v.latency.p95_ms=NaN,v=>v.latency.sample_size=201,v=>v.request_counts['private-url']=1,v=>v.checked_at='<script>',v=>v.account='private',v=>v.recent_server_failures.push({at:v.checked_at,status:503})]){const bad=structuredClone(r);change(bad);assert.throws(()=>validateMonitoring(bad));}
 const legacy=structuredClone(r);delete legacy.latency.invalid_samples;assert.doesNotThrow(()=>validateMonitoring(legacy));assert.match(renderMonitoring(legacy,0,Date.parse(legacy.checked_at)),/Not reported by this snapshot/);
});
test('monitoring expires without a new response and rejects future or replayed health',()=>{
 const r=monitoringFixture(),now=Date.parse(r.checked_at);r.sample_age_seconds=89;
 assert.equal(monitoringView(r,.5,now).state,'healthy');assert.equal(monitoringView(r,1,now).state,'unknown');assert.deepEqual(monitoringView(r,1,now).components,{});
 assert.equal(monitoringView(r,0,now+91000).state,'unknown');assert.equal(monitoringView(r,0,now-6000).freshness_reason,'clock_mismatch');assert.throws(()=>monitoringView(r,-1,now));assert.throws(()=>monitoringView(r,NaN,now));
 const degraded=monitoringFixture();degraded.components.active_model=false;degraded.state='degraded';assert.equal(monitoringView(degraded,0,now).state,'degraded');
});
test('monitoring diagnostic export preserves unknown scope and contains only aggregate evidence',()=>{
 const r=monitoringFixture(),receipt=monitoringExport(r,91,Date.parse(r.checked_at));assert.equal(receipt.format,'ain-monitoring-diagnostic-v1');assert.equal(receipt.observation.state,'unknown');assert.deepEqual(receipt.observation.components,{});assert.equal(receipt.external_alert_delivery,false);assert.equal(receipt.production_ready,false);assert.equal(receipt.observation.request_counts['2xx'],r.request_counts['2xx']);
 assert.ok(!JSON.stringify(receipt).includes('password'));assert.throws(()=>monitoringExport({...r,user_token:'private'}));
});
function rollbackFixture(){return {production_ready:false,release_revision:'a'.repeat(40),schema_version:7,recovery:{recorded:false,production_qualified:false},rollback_drill:{recorded:true,production_qualified:false,flight_records:100,checked_at:'2026-11-21T00:00:00Z',candidate_revision:'a'.repeat(40),rollback_revision:'b'.repeat(40),binding:{relation:'matches_current_candidate',candidate_matches_current_build:true,current_revision:'a'.repeat(40),schema_matches:true,state_contracts_match:true}}};}
test('rollback binding distinguishes current, historical and incompatible evidence',()=>{
 const value=rollbackFixture();assert.match(renderPlatform(value),/matches this source build/);
 for(const relation of ['different_release','schema_mismatch','contract_mismatch','unverified_build','unavailable_contracts','legacy_unbound']){
  const data=structuredClone(value);data.rollback_drill.binding.relation=relation;data.rollback_drill.binding.candidate_matches_current_build=false;
  assert.doesNotMatch(renderPlatform(data),/Recorded drill matches this source build/);
 }
 delete value.rollback_drill.binding;assert.match(renderPlatform(value),/Historical receipt/);
});
test('rollback renderer rejects falsely matched evidence',()=>{
 for(const change of [b=>b.current_revision='b'.repeat(40),b=>b.schema_matches=false,b=>b.state_contracts_match=false,b=>b.candidate_matches_current_build=false,b=>b.relation='invented']){
  const value=rollbackFixture();change(value.rollback_drill.binding);assert.throws(()=>renderPlatform(value));
 }
});
test('rollback export excludes private fields and preserves limited scope',()=>{
 const data=rollbackFixture();data.rollback_drill.password_hash='DO-NOT-EXPOSE';data.rollback_drill.binding.private_path='DO-NOT-EXPOSE';
 const value=rollbackExport(data);assert.equal(value.production_qualified,false);assert.equal(value.rollback_drill.binding.candidate_matches_current_build,true);
 assert.doesNotMatch(JSON.stringify(value),/DO-NOT-EXPOSE/);assert.match(value.scope,/selected checks only/);
 assert.throws(()=>rollbackExport({...data,rollback_drill:{recorded:false}}));
});
const retrievalFixture=()=>({...JSON.parse(fs.readFileSync(new URL('../docs/reports/Retrieval_Diagnostics.json',import.meta.url),'utf8')),integrity_verified:true,report_sha256:'eb8a40b32b0d30af8d1f2e7a8815fd220808f28bf53a019ef6d12258b6e0c57f'});
test('recorded retrieval comparison exposes misses, filters and limited metric meaning',()=>{
 const r=retrievalFixture();assert.equal(retrievalCases(r).length,4);assert.equal(retrievalCases(r,'lexical').length,5);
 assert.equal(retrievalCases(r,'hybrid','all').length,24);assert.equal(retrievalCases(r,'hybrid','outside').length,6);assert.equal(retrievalCases(r,'hybrid','issues','wind').length,1);
 let html=renderRetrieval(r);assert.match(html,/not answer accuracy/);assert.match(html,/Keyword search ranked relevant passages higher overall/);assert.match(html,/4 of 24 questions/);assert.match(html,/Out-of-corpus question returned evidence/);
 r.cases[0].question='<script>alert(1)</script>';html=renderRetrieval(r,'hybrid','all');assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('retrieval validation rejects contradictory evidence and export excludes unrelated fields',()=>{
 for(const change of [r=>r.production_ready=true,r=>r.integrity_verified=false,r=>r.metrics.hybrid.target_hits_at_3=18,r=>r.cases[0].hybrid.target_ranks=[0],r=>r.cases[0].hybrid.retrieved[0].source='../private',r=>r.cases[0].hybrid.available=false]){
  const r=retrievalFixture();change(r);assert.throws(()=>validateRetrieval(r));
 }
 const r=retrievalFixture();r.private_path='DO-NOT-EXPOSE';r.metrics.hybrid.private_path='DO-NOT-EXPOSE';r.cases[0].private_path='DO-NOT-EXPOSE';
 const result=retrievalExport(r,'lexical','outside','wind');assert.equal(result.production_ready,false);assert.equal(result.recorded_evaluation_only,true);assert.equal(result.displayed_case_ids.length,1);assert.doesNotMatch(JSON.stringify(result),/DO-NOT-EXPOSE/);
 assert.throws(()=>retrievalCases(r,'invented'));assert.throws(()=>retrievalCases(r,'hybrid','unsupported'));
});
test('retrieval evaluation proxy permits only fixed reads and forwards only the session cookie',async t=>{
 const backend=await serve(t,(req,res)=>{assert.equal(req.url,'/api/v1/research/retrieval-diagnostics');assert.equal(req.headers.cookie,'ain_session=fixture');assert.equal(req.headers.authorization,undefined);res.end('{}');});
 const frontend=await serve(t,async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,backend)){res.writeHead(404);res.end();}});
 const url=`http://127.0.0.1:${frontend}/api/v1/research/retrieval-diagnostics`;
 assert.equal((await fetch(url,{headers:{Cookie:'ain_session=fixture; unrelated=secret',Authorization:'do-not-forward'}})).status,200);
 assert.equal((await fetch(url+'?source=private')).status,422);assert.equal((await fetch(url,{method:'POST'})).status,405);assert.equal((await fetch(url+'/anything')).status,404);
});

const scopedFixtures=()=>JSON.parse(fs.readFileSync(new URL('./scoped_lab_fixtures.json',import.meta.url),'utf8')).cases;
test('scoped lab distinguishes refusals, unavailable selection and exact cited excerpts',()=>{
 const fixtures=scopedFixtures();for(const {request,response} of Object.values(fixtures))assert.equal(validateScopedResult(response,request),response);
 assert.match(renderScopedResult(fixtures.coverage.response,fixtures.coverage.request),/Source vocabulary mismatch/);
 assert.match(renderScopedResult(fixtures.conflict.response,fixtures.conflict.request),/Clarify the experiment/);
 assert.match(renderScopedResult(fixtures.unavailable.response,fixtures.unavailable.request),/not a successful abstention/);
 assert.match(renderScopedResult(fixtures.excerpts.response,fixtures.excerpts.request),/probability quality is worse/);
 assert.match(renderScopedResult(fixtures.excerpts.response,fixtures.excerpts.request),/github.com\/shah-hussain-bangash/);
 const x=structuredClone(fixtures.excerpts);x.response.claims[0].text=x.response.claims[0].quote='<img src=x onerror=alert(1)> literal source excerpt';
 const html=renderScopedResult(x.response,x.request);assert.ok(!html.includes('<img'));assert.match(html,/&lt;img/);
});
test('scoped lab rejects stale identities and contradictions and exports only public fields',()=>{
 const f=scopedFixtures();for(const change of [r=>r.experiment='delay-v2',r=>r.source='../private',r=>r.claims[0].text='Invented',r=>r.context_added_count=99,r=>r.coverage.missing_terms=['inventedterm'],r=>r.production_ready=true]){
  const r=structuredClone(f.excerpts.response);change(r);assert.throws(()=>validateScopedResult(r,f.excerpts.request));
 }
 const r=structuredClone(f.excerpts.response);r.private_error='PRIVATE-ERROR';r.claims[0].private_token='PRIVATE-ERROR';r.scope_guard.extra='PRIVATE-ERROR';r.coverage.extra='PRIVATE-ERROR';
 const exported=scopedExport(r,f.excerpts.request);assert.ok(!JSON.stringify(exported).includes('PRIVATE-ERROR'));assert.equal(exported.saved_to_history,false);
 const unavailable=structuredClone(f.unavailable.response);unavailable.mode='abstained';assert.throws(()=>validateScopedResult(unavailable,f.unavailable.request));
});
test('scoped query proxy is bounded POST with CSRF and session cookie only',async()=>{
 let received;const backend=http.createServer(async(req,res)=>{let body='';for await(const part of req)body+=part;received={url:req.url,method:req.method,headers:req.headers,body};res.setHeader('Content-Type','application/json');res.end(JSON.stringify({ok:true}));});
 await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));const port=backend.address().port;
 const front=http.createServer(async(req,res)=>{if(!await proxyResearchRequest(req,res,new URL(req.url,'http://127.0.0.1').pathname,port)){res.writeHead(404);res.end();}});
 await new Promise(resolve=>front.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+front.address().port;
 try{let r=await fetch(base+'/api/v1/research/scoped-query',{method:'POST',headers:{'Content-Type':'application/json','Cookie':'ain_session=fixture-session; private=secret','X-CSRF-Token':'csrf-fixture','Authorization':'Bearer PRIVATE-ERROR'},body:'{}'});assert.equal(r.status,200);assert.equal(received.url,'/api/v1/research/scoped-query');assert.equal(received.headers['x-csrf-token'],'csrf-fixture');assert.ok(!received.headers.authorization);assert.equal(received.headers.cookie,'ain_session=fixture-session');
 assert.equal((await fetch(base+'/api/v1/research/scoped-query')).status,405);
 assert.equal((await fetch(base+'/api/v1/research/scoped-query?x=1',{method:'POST'})).status,422);
 assert.equal((await fetch(base+'/api/v1/research/scoped-query',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(4097)})).status,413);
 }finally{front.closeAllConnections();backend.closeAllConnections();await Promise.all([new Promise(r=>front.close(r)),new Promise(r=>backend.close(r))]);}
});

function intakeFixture(){return {format:'ain-intake-overview-v1',checked_at:'2026-11-23T12:00:00Z',runs_checked:4,accepted_runs:2,quarantined_runs:1,unverifiable_runs:1,unique_archives:1,repeated_accepted_runs:1,declared_rows:100,archives:[{period:'2025-01',sha256:'a'.repeat(64),bytes:1000,declared_rows:100,runs:2}],quarantine_reasons:{invalid_zip:1},receipt_authenticated:false,rows_rescanned:false,import_authorized:false,import_performed:false,production_ready:false};}
test('intake snapshot distinguishes deduplicated unsigned claims from imported records',()=>{const r=intakeFixture();assert.equal(validateIntake(r),r);const html=renderIntake(r);assert.match(html,/unsigned receipt claims/);assert.match(html,/Not imported flight counts/);assert.match(html,/repeated accepted checks excluded/);assert.match(html,/invalid zip: 1/);});
test('intake snapshot rejects duplicate hashes, corrupt accounting and readiness claims',()=>{for(const change of [r=>r.production_ready=true,r=>r.declared_rows++,r=>r.accepted_runs=true,r=>r.archives.push({...r.archives[0]}),r=>r.archives[0].runs=1,r=>r.quarantine_reasons.invalid_zip=2,r=>r.archives[0].period='<script>']){const r=intakeFixture();change(r);assert.throws(()=>validateIntake(r));}});
test('intake proxy rejects query controls and writes before upstream access',async()=>{for(const [method,url,expected] of [['GET','/api/v1/research/intake-overview?path=secret',422],['POST','/api/v1/research/intake-overview',405]]){let status;const res={writeHead(code){status=code;},end(){}};assert.equal(await proxyResearchRequest({method,url,headers:{}},res,'/api/v1/research/intake-overview',1),true);assert.equal(status,expected);}});

function lineageFixture(){return {format:'ain-batch-lineage-view-v1',relation:'archive_identity_recheck',dataset:{period:'2025-01',recorded_rows:539747,archive_sha256:'a'.repeat(64),audit_report_sha256:'b'.repeat(64)},intake:{run_id:'c'.repeat(32),record:'accepted/'+'c'.repeat(32),receipt_sha256:'d'.repeat(64),checked_at:'2026-11-24T10:00:00Z',declared_source_url:'https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip',disposition:'accepted'},receipt_authenticated:false,original_import_receipt:false,live_database_checked:false,import_performed:false,production_ready:false};}
test('batch lineage displays exact source, receipt and recorded dataset while separating original import',()=>{const r=lineageFixture();assert.equal(validateLineage(r),r);const html=renderLineage(r);assert.match(html,/539,747/);assert.ok(html.includes(r.intake.record));assert.ok(html.includes(r.intake.receipt_sha256));assert.match(html,/not the original import receipt/);assert.match(html,/Analyst access/);});
test('batch lineage full receipt remains admin-only and unsafe receipt text stays literal',()=>{const r=lineageFixture();r.admin_receipt={run_id:r.intake.run_id,archive_sha256:r.dataset.archive_sha256,note:'<script>unsafe</script>'};assert.doesNotMatch(renderLineage(r,false),/unsafe/);assert.match(renderLineage(r,true),/&lt;script&gt;/);assert.doesNotMatch(renderLineage(r,true),/<script>/);});
test('batch lineage refuses changed identities, source controls and approval claims',()=>{for(const mutate of [r=>r.production_ready=true,r=>r.original_import_receipt=true,r=>r.intake.record='../../private',r=>r.intake.declared_source_url='javascript:alert(1)',r=>r.dataset.archive_sha256='invalid']){const r=lineageFixture();mutate(r);assert.throws(()=>validateLineage(r));}});
test('batch lineage proxy rejects writes and arbitrary selectors',async()=>{for(const [method,url,status] of [['POST','/api/v1/research/batch-lineage',405],['GET','/api/v1/research/batch-lineage?file=private',422]]){let code;const res={writeHead(v){code=v;},end(){}};assert.equal(await proxyResearchRequest({method,url,headers:{}},res,'/api/v1/research/batch-lineage',1),true);assert.equal(code,status);}});
