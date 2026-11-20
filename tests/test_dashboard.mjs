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
import { renderInvestigation, investigationPayload } from '../apps/web/investigation-lab.mjs';
import {renderPlatform} from '../apps/web/platform-status.mjs';
import {runtimeConfig,routing} from '../scripts/runtime-config.mjs';
import {renderMonitoring} from '../apps/web/monitoring-lab.mjs';
import fs from 'node:fs';
import {renderReadiness,filterReadiness} from '../apps/web/release-readiness.mjs';
import {renderPatterns,validatePatterns} from '../apps/web/route-patterns.mjs';
import {renderRouteHistory,validateRouteHistory} from '../apps/web/route-history.mjs';

const routeHistoryFixture=()=>JSON.parse(fs.readFileSync(new URL('../docs/reports/Route_History_Lookup.json',import.meta.url),'utf8')).example;
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
  assert.match(html,/Isolated application rollback drill passed/);
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
  assert.match(html,/running tools are not forcibly stopped/);
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

test('monitoring renderer withholds stale component health and escapes transition text',()=>{
  const data={production_ready:false,external_alert_delivery:false,state:'unknown',request_counts:{'2xx':4,'5xx':1},latency:{p95_ms:25,sample_size:5},components:{database:true},transitions:[{at:'<script>',component:'database',state:'unavailable'}],recent_server_failures:[],persistence_ok:true};
  const html=renderMonitoring(data);
  assert.match(html,/Current component health is unknown/);
  assert.doesNotMatch(html,/Check passed/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  assert.throws(()=>renderMonitoring({...data,production_ready:true}));
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
