import assert from 'node:assert/strict';
import http from 'node:http';
import {test} from 'node:test';
import {proxyResearchRequest} from '../scripts/api-proxy.mjs';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
async function server(t,handler){const s=http.createServer(handler);await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{s.closeAllConnections();s.close(resolve);}));return s.address().port;}
async function gateway(t,apiPort){return server(t,(req,res)=>proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,apiPort));}

test('proxy preserves a valid backend correlation ID without forwarding a caller ID',async t=>{
  const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';let incoming;
  const api=await server(t,(req,res)=>{incoming=req.headers['x-request-id'];res.writeHead(200,{'Content-Type':'application/json','X-Request-ID':id});res.end('{"ok":true}');});
  const port=await gateway(t,api);const response=await fetch(`http://127.0.0.1:${port}/api/v1/auth/session`,{headers:{'X-Request-ID':'caller-controlled'}});
  assert.equal(response.headers.get('x-request-id'),id);assert.equal(incoming,undefined);assert.equal(response.status,200);await response.text();
});
test('proxy gives malformed backend replies and local rejections safe distinct IDs',async t=>{
  const api=await server(t,(req,res)=>{res.writeHead(200,{'Content-Type':'application/json','X-Request-ID':'private-backend-value'});res.end('{}');});
  const port=await gateway(t,api);const base=`http://127.0.0.1:${port}`;
  const responses=[await fetch(base+'/api/v1/auth/session'),await fetch(base+'/api/v1/auth/session',{method:'POST'}),await fetch(base+'/api/v1/research/batch-lineage?path=private')];
  assert.deepEqual(responses.map(r=>r.status),[200,405,422]);const ids=responses.map(r=>r.headers.get('x-request-id'));ids.forEach(id=>assert.match(id,uuid));assert.equal(new Set(ids).size,3);await Promise.all(responses.map(r=>r.text()));
});
test('proxy backend failure has a matching gateway ID in its response header and error body',async t=>{
  const api=await server(t,(req,res)=>{res.writeHead(200,{'Content-Type':'application/json'});res.end('invalid JSON');});
  const port=await gateway(t,api);const response=await fetch(`http://127.0.0.1:${port}/api/v1/auth/session`);const data=await response.json();
  assert.equal(response.status,503);assert.match(data.request_id,uuid);assert.equal(response.headers.get('x-request-id'),data.request_id);assert.equal(data.error,'backend_unavailable');
});
