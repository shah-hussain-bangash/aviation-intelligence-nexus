// Fixed local research routes; never forward arbitrary destinations or browser credentials.
import {routing} from './runtime-config.mjs';
export async function proxyResearchRequest(req, res, pathname, apiPort,config={}) {
  const {apiHost,sessionCookie:cookieName}=routing(config);
  const prediction = pathname === '/api/v1/research/predict';
  const optimization = pathname === '/api/v1/research/optimize-gates';
  const knowledge = pathname === '/api/v1/research/knowledge-query';
  const agent = pathname === '/api/v1/research/agent-run';
  const jobSubmit = pathname === '/api/v1/research/agent-jobs';
  const jobRead = /^\/api\/v1\/research\/agent-jobs\/[0-9a-fA-F-]{36}$/.test(pathname);
  const jobCancel = pathname === '/api/v1/research/agent-cancel';
  const routeProfile = pathname === '/api/v1/research/route-profile';
  const agentReview = pathname === '/api/v1/research/agent-review';
  const authWrite = ['/api/v1/auth/login','/api/v1/auth/logout'].includes(pathname);
  const write = jobSubmit || jobCancel || prediction || optimization || knowledge || agent || agentReview || authWrite;
  if (!['/api/v1/research/summary', '/api/v1/research/history','/api/v1/research/gate-history','/api/v1/auth/session','/api/v1/research/knowledge-status','/api/v1/research/knowledge-history','/api/v1/research/agent-status','/api/v1/research/agent-history','/api/v1/research/platform-status','/api/v1/research/readiness','/api/v1/research/monitoring','/api/v1/research/route-segments','/api/v1/research/model-diagnostics'].includes(pathname) && !write && !jobRead && !routeProfile) return false;
  if (req.method !== (write ? 'POST' : 'GET')) {
    res.writeHead(405); res.end(); return true;
  }
  let targetPath = pathname;
  if (routeProfile) {
    const parameters = new URL(req.url, 'http://127.0.0.1').searchParams;
    if ([...parameters].length !== 2 || [...parameters.keys()].sort().join(',') !== 'destination,origin' || !/^[A-Z]{3}$/.test(parameters.get('origin') || '') || !/^[A-Z]{3}$/.test(parameters.get('destination') || '') || parameters.get('origin') === parameters.get('destination')) {
      res.writeHead(422, {'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify({error:'invalid_route_query'}));return true;
    }
    targetPath += '?' + new URLSearchParams({origin:parameters.get('origin'),destination:parameters.get('destination')});
  }
  let requestBody;
  if (write) {
    if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || '')) {
      res.writeHead(415); res.end(); return true;
    }
    const chunks = [];
    let bytes = 0;
    for await (const chunk of req) {
      bytes += chunk.length;
      if (bytes > (optimization ? 16384 : 4096)) {
        res.writeHead(413); res.end(); return true;
      }
      chunks.push(chunk);
    }
    requestBody = Buffer.concat(chunks).toString('utf8');
  }
  try {
    const sessionCookie = (req.headers.cookie || '').split(';').map(value=>value.trim()).find(value=>new RegExp('^'+cookieName+'=[A-Za-z0-9_-]{1,128}$').test(value));
    const response = await fetch(`http://${apiHost}:${apiPort}${targetPath}`, {
      method: write ? 'POST' : 'GET', body: requestBody,
      headers: { Accept: 'application/json', ...(sessionCookie ? {Cookie:sessionCookie}:{}),
        ...(req.headers.origin ? {Origin:req.headers.origin}:{}),
        ...(req.headers['x-csrf-token'] ? {'X-CSRF-Token':req.headers['x-csrf-token']}:{}),
        ...(write ? { 'Content-Type': 'application/json',
        ...(req.headers['idempotency-key'] ? { 'Idempotency-Key': req.headers['idempotency-key'] } : {}) } : {}) },
      redirect: 'error', signal: AbortSignal.timeout(agent ? 150000 : knowledge ? 100000 : 8000)
    });
    const body = await response.text();
    if (body.length > 1024 * 1024) throw new Error('Unexpected response size');
    JSON.parse(body);
    const cookies = response.headers.getSetCookie().filter(value=>value.startsWith(cookieName+'='));
    res.writeHead(response.status, { 'Content-Type': 'application/json; charset=utf-8', ...(cookies.length ? {'Set-Cookie':cookies}:{}),
      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(body);
  } catch {
    res.writeHead(503, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'backend_unavailable' }));
  }
  return true;
}
