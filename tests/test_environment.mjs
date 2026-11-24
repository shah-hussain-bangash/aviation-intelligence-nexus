import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import {runtimeConfig,environmentDiagnostic} from '../scripts/runtime-config.mjs';
function childEnv(values={}){return {...Object.fromEntries(Object.entries(process.env).filter(([k])=>!k.startsWith('AIN_')&&k!=='PORT')),...values};}
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
