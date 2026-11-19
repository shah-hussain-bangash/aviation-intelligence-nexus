import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { test } from 'node:test';
import { renderResearchSummary } from '../apps/web/live-research.mjs';
import { proxyResearchRequest } from '../scripts/api-proxy.mjs';
import { renderPrediction } from '../apps/web/research-scenario.mjs';
import { renderHistory } from '../apps/web/research-history.mjs';

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
