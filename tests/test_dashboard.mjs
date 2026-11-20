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
import { renderInvestigation } from '../apps/web/investigation-lab.mjs';
import {renderPlatform} from '../apps/web/platform-status.mjs';
import {runtimeConfig,routing} from '../scripts/runtime-config.mjs';
import {renderMonitoring} from '../apps/web/monitoring-lab.mjs';

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
