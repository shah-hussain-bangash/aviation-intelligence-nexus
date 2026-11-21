import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {inspectPort} from './start-local.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const execute=promisify(execFile);
export const dashboardURL='http://127.0.0.1:8090';
const names=['ain-local-release-api-1','ain-local-release-web-1'];

export function validateContainers(containers){
  if(!Array.isArray(containers)||containers.length!==2)throw new Error('The saved Aviation deployment is missing. Follow docs/LOCAL_DEPLOYMENT_RECOVERY.md; startup will not create an empty replacement.');
  for(const service of ['api','web']){
    const matches=containers.filter(c=>c?.Config?.Labels?.['com.docker.compose.service']===service);
    if(matches.length!==1)throw new Error('The saved deployment does not contain exactly one API and dashboard.');
    const c=matches[0],bindings=c.HostConfig?.PortBindings??{};
    if(c.Config.Labels['com.docker.compose.project']!=='ain-local-release'||c.Name!==`/ain-local-release-${service}-1`)throw new Error('The saved containers belong to another deployment.');
    if(service==='api'){
      const mounts=(c.Mounts??[]).filter(m=>m.Destination==='/app/.local');
      if(mounts.length!==1||mounts[0].Type!=='volume'||mounts[0].Name!=='ain-local-release_state')throw new Error('The API does not use the expected saved Aviation data volume.');
      if(Object.keys(bindings).length)throw new Error('The saved API exposes an unexpected host port.');
      if(!c.Config.Env?.includes('AIN_STATE_ROOT=/app/.local/active'))throw new Error('The saved API uses an unexpected state location.');
    }else{
      const ports=bindings['8080/tcp'];
      if(Object.keys(bindings).length!==1||!Array.isArray(ports)||ports.length!==1||ports[0].HostIp!=='127.0.0.1'||ports[0].HostPort!=='8090')throw new Error('The saved dashboard does not use the expected private port 8090.');
    }
  }
  return true;
}

export async function ready(fetcher=fetch){
  try{
    const response=await fetcher(dashboardURL+'/__ain/ready',{signal:AbortSignal.timeout(3000),redirect:'error'});
    if(!response.ok)return false;
    const value=await response.json();
    return value?.service==='ain-dashboard'&&value.backend_ready===true&&value.production_ready===false;
  }catch{return false;}
}

async function docker(args,timeout=15000){
  try{
    const result=await execute('docker',args,{cwd:root,timeout,windowsHide:true,maxBuffer:1024*1024});
    return result.stdout;
  }catch(error){
    if(error.code==='ENOENT')throw new Error('Docker Desktop is not installed or available in this terminal. Open Docker Desktop, then try again.');
    if(error.killed||error.code==='ETIMEDOUT')throw new Error('Docker did not respond in time. Check that Docker Desktop says Engine running, then try again.');
    throw new Error('Docker could not access the saved Aviation deployment. Open Docker Desktop and use your normal Windows terminal. Existing containers and volumes were not replaced.');
  }
}

export async function startRelease({probe=ready,portState=()=>inspectPort(8090,'ain-dashboard'),command=docker,log=console.log}={}){
  if(await probe()){
    log(`Aviation dashboard is already running: ${dashboardURL}`);
    return {started:false,ready:true};
  }
  // Refuse unrelated occupied ports before issuing any Docker operation.
  await portState();
  let containers;
  try{containers=JSON.parse(await command(['inspect',...names]));}
  catch(error){if(error instanceof SyntaxError)throw new Error('Docker returned an unreadable saved-deployment record. Nothing was started.');throw error;}
  validateContainers(containers);
  log('Starting your saved Aviation dashboard and API…');
  await command(['compose','-p','ain-local-release','-f',path.join(root,'compose.yaml'),'start','--wait','--wait-timeout','90','api','web'],110000);
  if(!await probe())throw new Error('The services started, but dashboard/backend readiness could not be verified. Check Docker Desktop for ain-local-release. Your saved data is retained.');
  log(`Aviation dashboard is ready: ${dashboardURL}`);
  log('Sign in with your existing account. Startup does not rebuild images, create accounts or qualify production readiness.');
  return {started:true,ready:true};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  startRelease().catch(error=>{console.error(`Startup stopped: ${error.message}`);process.exitCode=1;});
}
