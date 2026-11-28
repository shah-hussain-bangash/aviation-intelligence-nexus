import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import {runtimeConfig,environmentDiagnostic} from '../scripts/runtime-config.mjs';
import {routing} from '../scripts/runtime-config.mjs';
import {proxyResearchRequest} from '../scripts/api-proxy.mjs';
import http from 'node:http';
function childEnv(values={}){return {...Object.fromEntries(Object.entries(process.env).filter(([k])=>!k.startsWith('AIN_')&&k!=='PORT')),...values};}

test('local HTTPS requires native test cookies and a private pinned bundle',()=>{
 const valid={AIN_ENV:'test',AIN_SESSION_COOKIE:'ain_test_session',AIN_LOCAL_HTTPS:'1',AIN_LOCAL_TLS_DIRECTORY:'.local/test-tls',AIN_LOCAL_TLS_SHA256:'e'.repeat(64)};
 assert.equal(runtimeConfig(valid).localHttps,true);assert.equal(runtimeConfig({}).localHttps,false);
 assert.equal(runtimeConfig({...valid,AIN_LOCAL_API_HTTPS:'1'}).localApiHttps,true);
 for(const change of [{AIN_ENV:'local'},{AIN_CONTAINER:'1'},{AIN_SESSION_COOKIE:'ain_session'},{AIN_LOCAL_HTTPS:'true'},{AIN_LOCAL_TLS_DIRECTORY:'outside'},{AIN_LOCAL_TLS_DIRECTORY:'.local/../outside'},{AIN_LOCAL_TLS_SHA256:'invalid'},{AIN_LOCAL_HTTPS:'0'}])assert.throws(()=>runtimeConfig({...valid,...change}));
 for(const env of [{AIN_LOCAL_API_HTTPS:'true'},{AIN_LOCAL_API_HTTPS:'1'},{...valid,AIN_LOCAL_HTTPS:'0',AIN_LOCAL_API_HTTPS:'1'}])assert.throws(()=>runtimeConfig(env));
});

test('preview cookie routing is restricted to native test profile',()=>{
 const c=runtimeConfig({AIN_ENV:'test',AIN_SESSION_COOKIE:'ain_test_session'});assert.equal(c.sessionCookie,'ain_test_session');assert.equal(routing(c).sessionCookie,'ain_test_session');
 for(const change of [{AIN_ENV:'local'},{AIN_ENV:'production'},{AIN_CONTAINER:'1'}])assert.throws(()=>runtimeConfig({AIN_ENV:'test',AIN_SESSION_COOKIE:'ain_test_session',...change}));
 assert.throws(()=>routing({sessionCookie:'ain_test_session'}));assert.throws(()=>routing({sessionCookie:'ain_test_session',profile:'test',apiHost:'api'}));
});
test('actual gateway preflight accepts test namespace only under test profile',()=>{
 for(const [profile,code] of [['test',0],['local',2]]){const r=spawnSync(process.execPath,['scripts/check-environment.mjs'],{env:childEnv({AIN_ENV:profile,AIN_SESSION_COOKIE:'ain_test_session'}),encoding:'utf8',timeout:10000,windowsHide:true});assert.equal(r.status,code);assert.equal(JSON.parse(r.stdout).valid,code===0);}
});
test('preview proxy isolates both incoming and outgoing cookies from normal namespaces',async t=>{
 async function server(handler){const s=http.createServer(handler);await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>{s.close(resolve);s.closeAllConnections();}));return s.address().port;}
 const backend=await server((req,res)=>{assert.equal(req.headers.cookie,'ain_test_session=preview_fixture');res.setHeader('Set-Cookie',['ain_test_session=new_fixture; HttpOnly; SameSite=Strict','ain_session=do_not_forward','ain_release_session=do_not_forward']);res.end('{}');});
 const config=runtimeConfig({AIN_ENV:'test',AIN_SESSION_COOKIE:'ain_test_session'});
 const gateway=await server((req,res)=>proxyResearchRequest(req,res,new URL(req.url,'http://localhost').pathname,backend,config));
 const response=await fetch(`http://127.0.0.1:${gateway}/api/v1/auth/session`,{headers:{Cookie:'ain_session=native_fixture; ain_release_session=release_fixture; ain_test_session=preview_fixture'}});
 assert.equal(response.status,200);assert.equal(response.headers.getSetCookie().length,1);assert.ok(response.headers.getSetCookie()[0].startsWith('ain_test_session='));
});
test('local defaults and isolated container routing remain available',()=>{
  const c=runtimeConfig({});assert.equal(c.bindHost,'127.0.0.1');assert.equal(c.webPort,8080);assert.equal(c.apiPort,8002);
  assert.equal(runtimeConfig({AIN_CONTAINER:'1',AIN_BIND_HOST:'0.0.0.0',AIN_API_HOST:'api'}).apiHost,'api');assert.equal(environmentDiagnostic({}).production_ready,false);
});
test('unsafe flags, malformed ports, public routing and unsupported modes are rejected',()=>{
  for(const env of [{PORT:'1e3'},{PORT:''},{AIN_API_PORT:'65536'},{PORT:'8002'},{AIN_AGENT_JOBS:'true'},{AIN_BIND_HOST:'0.0.0.0'},{AIN_API_HOST:'api'},{AIN_OLLAMA_HOST:'host.docker.internal'},{AIN_ENV:'production'},{AIN_SESSION_COOKIE:'PRIVATE'},{AIN_OBSERVER_MOUNTED:'1'},{AIN_RELEASE_REVISION:'PRIVATE-REVISION'},{AIN_COOKIE_SECURE:'1'}])assert.throws(()=>runtimeConfig(env));
});
test('secret and origin diagnostics contain only fixed codes',()=>{
  const env=Object.fromEntries(['AIN_SECRET_KEY','AIN_API_KEY','AIN_ADMIN_PASSWORD','AIN_SECRETS_FILE','AIN_DATABASE_URL','AIN_PUBLIC_ORIGIN'].map(k=>[k,'PRIVATE-SECRET-VALUE']));
  const report=environmentDiagnostic(env);assert.equal(report.valid,false);assert.doesNotMatch(JSON.stringify(report),/PRIVATE-SECRET-VALUE/);assert.ok(report.errors.includes('secret_provider_not_configured'));
});
test('actual gateway startup refuses an unsupported profile before listening',()=>{
  const r=spawnSync(process.execPath,['scripts/dev.mjs'],{env:childEnv({AIN_ENV:'production',AIN_SECRET_KEY:'PRIVATE-SECRET-VALUE'}),encoding:'utf8',timeout:10000,windowsHide:true});
  assert.equal(r.status,1);assert.doesNotMatch(r.stdout,/AIN dashboard/);assert.doesNotMatch(r.stdout+r.stderr,/PRIVATE-SECRET-VALUE/);assert.match(r.stderr,/runtime_profile_not_supported/);
});
test('gateway preflight CLI reports valid local defaults or safe failure JSON',()=>{
  const valid=spawnSync(process.execPath,['scripts/check-environment.mjs'],{env:childEnv(),encoding:'utf8',timeout:10000,windowsHide:true});assert.equal(valid.status,0);assert.equal(JSON.parse(valid.stdout).valid,true);
  const bad=spawnSync(process.execPath,['scripts/check-environment.mjs'],{env:childEnv({AIN_SECRETS_FILE:'PRIVATE-SECRET-FILE'}),encoding:'utf8',timeout:10000,windowsHide:true});assert.equal(bad.status,2);assert.equal(JSON.parse(bad.stdout).valid,false);assert.doesNotMatch(bad.stdout+bad.stderr,/PRIVATE-SECRET-FILE/);
});
