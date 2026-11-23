import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import http from 'node:http';
import {test} from 'node:test';

async function dashboard(t){
  const backend=http.createServer(async(req,res)=>{
    for await(const chunk of req){ /* Drain only the isolated fixture request. */ }
    if(req.url==='/health/ready'){res.setHeader('Content-Type','application/json');res.end('{"status":"ready"}');}
    else if(req.url==='/api/v1/auth/login'){
      res.setHeader('Content-Type','application/json');
      res.setHeader('Set-Cookie',['ain_session=fixture_session; HttpOnly; SameSite=strict; Path=/api','unrelated=not-forwarded']);
      res.end('{"authenticated":true,"user":{"username":"fixture"}}');
    }else{res.end('invalid backend JSON');}
  });
  await new Promise(resolve=>backend.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>{backend.closeAllConnections();backend.close(resolve);}));
  const reservation=http.createServer();await new Promise(resolve=>reservation.listen(0,'127.0.0.1',resolve));
  const port=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  const child=spawn(process.execPath,['scripts/dev.mjs'],{cwd:new URL('..',import.meta.url),windowsHide:true,
    env:{...process.env,PORT:String(port),AIN_API_PORT:String(backend.address().port),AIN_CONTAINER:'0',AIN_BIND_HOST:'127.0.0.1',AIN_API_HOST:'127.0.0.1',AIN_SESSION_COOKIE:'ain_session'},stdio:['ignore','pipe','pipe']});
  t.after(()=>child.kill());
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('Fixture dashboard startup timed out')),8000);
    child.once('error',error=>{clearTimeout(timer);reject(error);});
    child.once('exit',()=>{clearTimeout(timer);reject(new Error('Fixture dashboard exited'));});
    child.stdout.on('data',chunk=>{if(chunk.toString().includes('AIN dashboard:')){clearTimeout(timer);resolve();}});
  });
  return 'http://127.0.0.1:'+port;
}

function assertHeaders(response){
  assert.equal(response.headers.get('x-content-type-options'),'nosniff');
  assert.equal(response.headers.get('x-frame-options'),'DENY');
  const csp=response.headers.get('content-security-policy');
  assert.match(csp,/frame-ancestors 'none'/);assert.match(csp,/object-src 'none'/);assert.match(csp,/base-uri 'self'/);
  assert.equal(response.headers.get('referrer-policy'),'no-referrer');
  assert.match(response.headers.get('permissions-policy'),/camera=\(\), microphone=\(\), geolocation=\(\)/);
  assert.equal(response.headers.get('cache-control'),'no-store');
}

test('real frontend headers cover HTML, HEAD, module, CSS, image and health responses',async t=>{
  const base=await dashboard(t);
  for(const [path,type] of [['/','text/html'],['/platform-status.mjs','text/javascript'],['/live-research.css','text/css'],['/assets/login-family-aviation.png','image/png'],['/__ain/health','application/json'],['/__ain/ready','application/json']]){
    const response=await fetch(base+path);assert.equal(response.status,200,path);assertHeaders(response);
    assert.ok(response.headers.get('content-type').startsWith(type));await response.arrayBuffer();
  }
  const head=await fetch(base+'/',{method:'HEAD'});assertHeaders(head);assert.equal(await head.text(),'');
});

test('browser hardening remains present on frontend errors, rejected writes and backend failure',async t=>{
  const base=await dashboard(t);
  const requests=[['/missing-security-fixture',{},404],['/%ZZ',{},404],['/',{method:'POST'},405],
    ['/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'text/plain'},body:'{}'},415],
    ['/api/v1/research/scoped-query?unexpected=1',{method:'POST'},422],['/api/v1/research/summary',{},503]];
  for(const [path,options,status] of requests){const response=await fetch(base+path,options);assert.equal(response.status,status,path);assertHeaders(response);await response.text();}
});

test('hardening preserves filtered session-cookie forwarding and proxied login JSON',async t=>{
  const base=await dashboard(t);
  const response=await fetch(base+'/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json','Origin':base},body:'{"username":"fixture","password":"synthetic-only"}'});
  assert.equal(response.status,200);assertHeaders(response);assert.equal((await response.json()).authenticated,true);
  assert.equal(response.headers.getSetCookie().length,1);assert.match(response.headers.get('set-cookie'),/^ain_session=fixture_session;/);
  assert.doesNotMatch(response.headers.get('set-cookie'),/unrelated/);
});
