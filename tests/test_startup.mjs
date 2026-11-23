import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import { inspectPort, portNumber } from '../scripts/start-local.mjs';
import {ready,startRelease,validateContainers} from '../scripts/start-release.mjs';
import {reviewedBinary,reviewFile} from '../scripts/repository-guards.mjs';
import fs from 'node:fs';

test('portfolio media exception is restricted to exact path and unchanged committed bytes',()=>{
 const path='docs/case-study/assets/aviation-intelligence-nexus-walkthrough.mp4';
 assert.equal(reviewedBinary(path,Buffer.from('changed clip')),false);
 assert.equal(reviewedBinary('docs/case-study/assets/another.mp4',Buffer.from('clip')),false);
 assert.ok(reviewFile('docs/case-study/assets/another.mp4').includes('File type needs manual review'));
 // Hosted CI has the published clip; the older local checkout may still await its Git fetch.
 const file=new URL('../'+path,import.meta.url);
 if(fs.existsSync(file)){
  const bytes=fs.readFileSync(file);assert.equal(reviewedBinary(path,bytes),true);
  const changed=Buffer.from(bytes);changed[changed.length-1]^=1;assert.equal(reviewedBinary(path,changed),false);
  assert.deepEqual(reviewFile(path),[]);
 }
});

function savedContainers(){return ['api','web'].map(service=>({Name:`/ain-local-release-${service}-1`,Config:{Labels:{'com.docker.compose.project':'ain-local-release','com.docker.compose.service':service},Env:['AIN_STATE_ROOT=/app/.local/active']},HostConfig:{PortBindings:service==='web'?{'8080/tcp':[{HostIp:'127.0.0.1',HostPort:'8090'}]}:{}},Mounts:service==='api'?[{Destination:'/app/.local',Type:'volume',Name:'ain-local-release_state'}]:[]}));}

test('saved dashboard startup reuses ready service without touching Docker',async()=>{
 const result=await startRelease({probe:async()=>true,portState:async()=>assert.fail('Port mutation'),command:async()=>assert.fail('Docker mutation'),log:()=>{}});
 assert.deepEqual(result,{started:false,ready:true});
});

test('saved dashboard startup refuses unknown occupied ports before Docker',async()=>{
 await assert.rejects(startRelease({probe:async()=>false,portState:async()=>{throw new Error('Unrelated occupied port');},command:async()=>assert.fail('Docker mutation'),log:()=>{}}),/Unrelated occupied port/);
});

test('saved dashboard startup validates volume, project, state path and loopback binding',()=>{
 assert.equal(validateContainers(savedContainers()),true);
 for(const change of [c=>c[0].Config.Labels['com.docker.compose.project']='ain-rollback-drill',c=>c[0].Mounts[0].Name='another_state',c=>c[0].Mounts[0].Type='bind',c=>c[0].Config.Env=[],c=>c[1].HostConfig.PortBindings['8080/tcp'][0].HostIp='0.0.0.0',c=>c[1].HostConfig.PortBindings['8080/tcp'][0].HostPort='8091',c=>c.pop(),c=>c.push(c[0])]){
  const containers=savedContainers();change(containers);assert.throws(()=>validateContainers(containers));
 }
});

test('saved dashboard startup only starts the validated existing pair and verifies readiness',async()=>{
 let probes=0;const calls=[];
 const result=await startRelease({probe:async()=>++probes===2,portState:async()=> 'free',command:async(args,timeout)=>{calls.push({args,timeout});return calls.length===1?JSON.stringify(savedContainers()):'';},log:()=>{}});
 assert.deepEqual(result,{started:true,ready:true});assert.equal(calls.length,2);
 assert.deepEqual(calls[0].args,['inspect','ain-local-release-api-1','ain-local-release-web-1']);
 assert.deepEqual(calls[1].args.slice(-6),['start','--wait','--wait-timeout','90','api','web']);
 assert.equal(calls[1].timeout,110000);assert.ok(!calls.flatMap(c=>c.args).some(arg=>['up','build','down','rm','pull'].includes(arg)));
});

test('saved dashboard startup withholds success for failed readiness or Docker errors',async()=>{
 await assert.rejects(startRelease({probe:async()=>false,portState:async()=> 'free',command:async(args)=>args[0]==='inspect'?JSON.stringify(savedContainers()):'',log:()=>{}}),/readiness could not be verified/);
 let calls=0;
 await assert.rejects(startRelease({probe:async()=>false,portState:async()=> 'free',command:async()=>{calls++;throw new Error('Engine unavailable');},log:()=>{}}),/Engine unavailable/);assert.equal(calls,1);
});

test('saved dashboard readiness rejects outages, unrelated services and production claims',async()=>{
 for(const value of [{service:'other',backend_ready:true,production_ready:false},{service:'ain-dashboard',backend_ready:false,production_ready:false},{service:'ain-dashboard',backend_ready:true,production_ready:true}])assert.equal(await ready(async()=>new Response(JSON.stringify(value))),false);
 assert.equal(await ready(async()=>new Response(JSON.stringify({service:'ain-dashboard',backend_ready:true,production_ready:false}))),true);
 assert.equal(await ready(async()=>{throw new Error('Unavailable');}),false);
});

test('startup rejects invalid and out-of-range port values', () => {
  assert.equal(portNumber('8002'), 8002);
  for (const value of [0, -1, 65536, 'invalid', '2.5']) assert.throws(() => portNumber(value));
});

test('startup recognizes an existing AIN service without taking ownership', async () => {
  const server = http.createServer((req, res) => { res.end('{"service":"ain-api"}'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try { assert.equal(await inspectPort(server.address().port, 'ain-api'), 'existing'); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});

test('startup preserves unknown occupied ports and recognizes released ports', async () => {
  const server = http.createServer((req, res) => { res.end('{"service":"unrelated"}'); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  try { await assert.rejects(inspectPort(port, 'ain-dashboard'), /occupied by another or older service/); }
  finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  assert.equal(await inspectPort(port, 'ain-dashboard'), 'free');
});
