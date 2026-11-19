// Fixed local research routes; never forward arbitrary destinations or browser credentials.
export async function proxyResearchRequest(req, res, pathname, apiPort) {
  const prediction = pathname === '/api/v1/research/predict';
  if (!['/api/v1/research/summary', '/api/v1/research/history'].includes(pathname) && !prediction) return false;
  if (req.method !== (prediction ? 'POST' : 'GET')) {
    res.writeHead(405); res.end(); return true;
  }
  let requestBody;
  if (prediction) {
    if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || '')) {
      res.writeHead(415); res.end(); return true;
    }
    const chunks = [];
    let bytes = 0;
    for await (const chunk of req) {
      bytes += chunk.length;
      if (bytes > 4096) {
        res.writeHead(413); res.end(); return true;
      }
      chunks.push(chunk);
    }
    requestBody = Buffer.concat(chunks).toString('utf8');
  }
  try {
    const response = await fetch(`http://127.0.0.1:${apiPort}${pathname}`, {
      method: prediction ? 'POST' : 'GET', body: requestBody,
      headers: { Accept: 'application/json', ...(prediction ? { 'Content-Type': 'application/json',
        ...(req.headers['idempotency-key'] ? { 'Idempotency-Key': req.headers['idempotency-key'] } : {}) } : {}) },
      redirect: 'error', signal: AbortSignal.timeout(8000)
    });
    const body = await response.text();
    if (body.length > 1024 * 1024) throw new Error('Unexpected response size');
    JSON.parse(body);
    res.writeHead(response.status, { 'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(body);
  } catch {
    res.writeHead(503, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ error: 'backend_unavailable' }));
  }
  return true;
}
