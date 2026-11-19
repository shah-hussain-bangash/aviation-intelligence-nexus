import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { proxyResearchRequest } from './api-proxy.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../apps/web');
const port = Number(process.env.PORT || 8080);
const apiPort = Number(process.env.AIN_API_PORT || 8002);
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) throw new Error('AIN_API_PORT must be a valid local port.');
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be a valid local port.');
const types = { '.mjs': 'text/javascript; charset=utf-8', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.jpg': 'image/jpeg', '.png': 'image/png' };
const inside = value => value === root || value.startsWith(root + path.sep);
const server = http.createServer(async (req, res) => {
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
    if (pathname === '/__ain/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({service:'ain-dashboard',api_port:apiPort})); return;
    }
    if (await proxyResearchRequest(req, res, pathname, apiPort)) return;
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
    const target = path.resolve(root, '.' + pathname, pathname.endsWith('/') ? 'index.html' : '');
    if (!inside(target)) { res.writeHead(403); res.end('Forbidden'); return; }
    const real = await fs.realpath(target);
    if (!inside(real)) { res.writeHead(403); res.end('Forbidden'); return; }
    const data = await fs.readFile(real);
    res.writeHead(200, { 'Content-Type': types[path.extname(real)] || 'application/octet-stream', 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' });
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch { res.writeHead(404); res.end('Not found'); }
});
server.on('error', error => { console.error(error.code === 'EADDRINUSE' ? `Port ${port} is already in use. Set PORT to another local port.` : 'Local server could not start.'); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`AIN dashboard: http://127.0.0.1:${port}`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
