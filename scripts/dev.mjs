import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { proxyResearchRequest } from './api-proxy.mjs';
import {runtimeConfig} from './runtime-config.mjs';
import {securityHeaders} from './security-headers.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../apps/web');
const config=runtimeConfig();
const port=config.webPort,apiPort=config.apiPort;
const types = { '.mjs': 'text/javascript; charset=utf-8', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.jpg': 'image/jpeg', '.png': 'image/png' };
const inside = value => value === root || value.startsWith(root + path.sep);
const server = http.createServer(async (req, res) => {
  for(const [name,value] of Object.entries(securityHeaders))res.setHeader(name,value);
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
    if (pathname === '/__ain/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({service:'ain-dashboard',api_port:apiPort})); return;
    }
    if(pathname==='/__ain/ready'&&req.method==='GET'){
      try{const check=await fetch(`http://${config.apiHost}:${apiPort}/health/ready`,{signal:AbortSignal.timeout(2000),redirect:'error'});const state=await check.json();if(!check.ok||state.status!=='ready')throw new Error();
        res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify({service:'ain-dashboard',backend_ready:true,production_ready:false}));}
      catch{res.writeHead(503,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify({service:'ain-dashboard',backend_ready:false,production_ready:false}));}return;
    }
    if (await proxyResearchRequest(req, res, pathname, apiPort,config)) return;
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
server.listen(port, config.bindHost, () => console.log(`AIN dashboard: http://${config.bindHost}:${port}`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
