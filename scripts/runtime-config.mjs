// Trusted process configuration only. Browser requests cannot select a backend or cookie namespace.
export function routing(config={}) {
  const apiHost=config.apiHost||'127.0.0.1',sessionCookie=config.sessionCookie||'ain_session';
  if(!['127.0.0.1','api'].includes(apiHost))throw new Error('Unapproved API host.');
  if(!['ain_session','ain_release_session'].includes(sessionCookie))throw new Error('Unapproved session namespace.');
  return {apiHost,sessionCookie};
}

export function runtimeConfig(env=process.env){
  const bindHost=env.AIN_BIND_HOST||'127.0.0.1';
  if(!['127.0.0.1','0.0.0.0'].includes(bindHost)||bindHost==='0.0.0.0'&&env.AIN_CONTAINER!=='1')throw new Error('Non-loopback binding is reserved for the isolated container.');
  return {...routing({apiHost:env.AIN_API_HOST,sessionCookie:env.AIN_SESSION_COOKIE}),bindHost};
}
