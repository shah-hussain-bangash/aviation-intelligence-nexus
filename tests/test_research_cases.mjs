import assert from 'node:assert/strict';
import http from 'node:http';
import {test} from 'node:test';
import {validateCase,validateSources,renderCase} from '../apps/web/research-cases.mjs';
import {proxyResearchRequest} from '../scripts/api-proxy.mjs';
const id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',source='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const record=()=>({id,source_run_id:source,source_sha256:'a'.repeat(64),title:'<img src=x onerror=alert(1)>',status:'open',version:1,outcome:null,created_at:'2026-11-26T00:00:00Z',updated_at:'2026-11-26T00:00:00Z',scope:'historical_us_research',operational_approval:false,production_ready:false,source_snapshot:{run_id:source,model_version:'delay-v2',research_only:true,operational_serving_approved:false,limitations:['SYNTHETIC FIXTURE']},events:[{version:1,action:'opened',note:'<script>bad()</script>',created_at:'2026-11-26T00:00:00Z'}]});
test('case contract rejects changed identity, scope, chronology and unsafe approval claims',()=>{
 assert.equal(validateCase(record()).version,1);
 for(const change of [{id:'../private'},{source_sha256:'bad'},{version:2},{scope:'operational'},{production_ready:true},{operational_approval:true},{status:'closed'},{source_snapshot:{...record().source_snapshot,run_id:id}},{events:[{...record().events[0],action:'close'}]}])assert.throws(()=>validateCase({...record(),...change}));
 const html=renderCase(record());assert.ok(html.includes('&lt;img'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(html.includes(source));assert.ok(html.includes('not independently authenticated'));
 const closed={...record(),status:'closed',version:2,outcome:'Synthetic outcome',events:[...record().events,{version:2,action:'close',note:'Synthetic outcome',created_at:'2026-11-26T00:01:00Z'}]};assert.equal(validateCase(closed).status,'closed');
});
test('saved-source contract rejects duplicate IDs and invalid pins',()=>{
 const r={sources:[{run_id:source,source_sha256:'b'.repeat(64)}],production_ready:false};assert.equal(validateSources(r).length,1);
 assert.throws(()=>validateSources({...r,sources:[...r.sources,...r.sources]}));assert.throws(()=>validateSources({...r,production_ready:true}));assert.throws(()=>validateSources({...r,sources:[{run_id:source,source_sha256:'x'}]}));
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
