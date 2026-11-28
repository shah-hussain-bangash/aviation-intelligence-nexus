// Trusted process configuration only. Browser requests cannot select a backend or cookie namespace.
import {privateTlsDirectory} from './local-https.mjs';
export function routing(config={}) {
  const apiHost=config.apiHost||'127.0.0.1',sessionCookie=config.sessionCookie||'ain_session';
  if(!['127.0.0.1','api'].includes(apiHost))throw new Error('Unapproved API host.');
  if(!['ain_session','ain_release_session'].includes(sessionCookie)&&!(sessionCookie==='ain_test_session'&&config.profile==='test'&&config.container!==true&&apiHost==='127.0.0.1'))throw new Error('Unapproved session namespace.');
  return {apiHost,sessionCookie};
}

export function runtimeConfig(env=process.env){
  const codes=[],profile=env.AIN_ENV??'local';
  if(!['local','test'].includes(profile))codes.push('runtime_profile_not_supported');
  for(const name of ['AIN_CONTAINER','AIN_AGENT_JOBS','AIN_MONITOR_ENABLED','AIN_OBSERVER_MOUNTED','AIN_INTAKE_OVERVIEW_MOUNTED'])if(!['0','1'].includes(env[name]??'0'))codes.push('invalid_'+name.toLowerCase());
  const container=env.AIN_CONTAINER==='1',ports={};
  for(const [name,fallback] of [['PORT','8080'],['AIN_API_PORT','8002']]){
    const value=env[name]??fallback;
    const valid=typeof value==='string'&&/^[0-9]{1,5}$/.test(value)&&Number(value)>=1&&Number(value)<=65535;
    if(!valid)codes.push('invalid_'+name.toLowerCase());ports[name]=valid?Number(value):0;
  }
  if(ports.PORT&&ports.PORT===ports.AIN_API_PORT)codes.push('ports_must_differ');
  const bindHost=env.AIN_BIND_HOST??'127.0.0.1',apiHost=env.AIN_API_HOST??'127.0.0.1',sessionCookie=env.AIN_SESSION_COOKIE??'ain_session';
  if(!['127.0.0.1','0.0.0.0'].includes(bindHost)||bindHost==='0.0.0.0'&&!container)codes.push('bind_host_not_allowed');
  if(!['127.0.0.1','api'].includes(apiHost)||apiHost==='api'&&!container)codes.push('api_host_not_allowed');
  if(!['ain_session','ain_release_session'].includes(sessionCookie)&&!(sessionCookie==='ain_test_session'&&profile==='test'&&!container))codes.push('cookie_namespace_not_allowed');
  const modelHost=env.AIN_OLLAMA_HOST??'127.0.0.1';
  const localHttps=env.AIN_LOCAL_HTTPS==='1';
  if(!['0','1'].includes(env.AIN_LOCAL_HTTPS??'0'))codes.push('invalid_ain_local_https');
  if(localHttps){
    if(profile!=='test'||container||bindHost!=='127.0.0.1'||apiHost!=='127.0.0.1'||sessionCookie!=='ain_test_session')codes.push('local_https_requires_native_test');
    try{privateTlsDirectory(env.AIN_LOCAL_TLS_DIRECTORY);}catch{codes.push('local_tls_directory_invalid');}
    if(!/^[a-f0-9]{64}$/.test(env.AIN_LOCAL_TLS_SHA256??''))codes.push('local_tls_pin_invalid');
  }else if(['AIN_LOCAL_TLS_DIRECTORY','AIN_LOCAL_TLS_SHA256'].some(k=>Object.hasOwn(env,k)))codes.push('local_tls_requires_https');
  if(!['127.0.0.1','ollama','host.docker.internal'].includes(modelHost)||modelHost!=='127.0.0.1'&&!container)codes.push('model_host_not_allowed');
  if(!container&&(env.AIN_OBSERVER_MOUNTED==='1'||env.AIN_INTAKE_OVERVIEW_MOUNTED==='1'))codes.push('container_mounts_require_container_mode');
  if((env.AIN_AUTH_PROVIDER??'local')!=='local')codes.push('identity_provider_not_configured');
  if(Object.hasOwn(env,'AIN_PUBLIC_ORIGIN'))codes.push('public_origin_not_configured');
  if(['AIN_COOKIE_SECURE','AIN_TLS_ENABLED','AIN_TRUST_PROXY','AIN_CORS_ORIGINS'].some(k=>Object.hasOwn(env,k)))codes.push('external_security_not_configured');
  if(['AIN_SECRET_KEY','AIN_API_KEY','AIN_ADMIN_PASSWORD','AIN_JWT_SECRET'].some(k=>Object.hasOwn(env,k)))codes.push('inline_secret_not_supported');
  if(Object.hasOwn(env,'AIN_SECRETS_FILE'))codes.push('secret_provider_not_configured');
  if(Object.hasOwn(env,'AIN_DATABASE_URL'))codes.push('managed_database_not_configured');
  if(Object.hasOwn(env,'AIN_RELEASE_REVISION')&&!(/^[0-9a-f]{40}$/.test(env.AIN_RELEASE_REVISION)||['working-tree','development-working-tree'].includes(env.AIN_RELEASE_REVISION)))codes.push('invalid_release_revision');
  if(codes.length){const error=new Error('Invalid local configuration: '+codes.join(','));error.codes=[...new Set(codes)];throw error;}
  return {...routing({apiHost,sessionCookie,profile,container}),bindHost,profile,container,localHttps,tlsDirectory:env.AIN_LOCAL_TLS_DIRECTORY,tlsPin:env.AIN_LOCAL_TLS_SHA256,webPort:ports.PORT,apiPort:ports.AIN_API_PORT};
}

export function environmentDiagnostic(env=process.env){
  try{const c=runtimeConfig(env);return {format:'ain-environment-check-v1',component:'gateway',valid:true,errors:[],profile:c.profile,container:c.container,web_port:c.webPort,api_port:c.apiPort,production_ready:false};}
  catch(error){return {format:'ain-environment-check-v1',component:'gateway',valid:false,errors:error.codes||['gateway_configuration_invalid'],production_ready:false};}
}
