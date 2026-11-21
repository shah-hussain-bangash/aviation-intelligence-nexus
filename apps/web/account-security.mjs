import {apiFetch} from './research-auth.mjs';
export function validateSecurity(data,now=Date.now(),requireReceipt=false){
 const checked=Date.parse(data.checked_at),expires=Date.parse(data.current_expires_at);
 if(data.scope!=='current_account_local_sessions'||data.production_ready!==false||!Number.isSafeInteger(data.active_sessions)||data.active_sessions<1||data.other_active_sessions!==data.active_sessions-1||!Number.isFinite(checked)||!Number.isFinite(expires)||expires<=checked||expires<=now||now-checked>90000||checked-now>5000)throw new Error('Account security observation unavailable or stale');
 if('revoked_other_sessions' in data&&(!Number.isSafeInteger(data.revoked_other_sessions)||data.revoked_other_sessions<0||data.current_session_preserved!==true||data.active_sessions!==1))throw new Error('Invalid revocation receipt');
 if(requireReceipt&&!Object.hasOwn(data,'revoked_other_sessions'))throw new Error('Revocation receipt missing');
 return data;
}
export function renderSecurity(data,now=Date.now()){
 validateSecurity(data,now);
 const expiry=new Date(data.current_expires_at).toLocaleString('en-GB',{timeZone:'UTC',hour12:false});
 return `<div class="research-kpis"><article><span>Active sessions for your account</span><strong>${data.active_sessions}</strong></article><article><span>Other active sessions</span><strong>${data.other_active_sessions}</strong></article></div><p>This session expires ${expiry} UTC. Counts reflect the latest check, not a list of devices.</p>${'revoked_other_sessions' in data?`<p class="security-receipt">${data.revoked_other_sessions} other active session${data.revoked_other_sessions===1?'':'s'} signed out. This session was preserved.</p>`:''}`;
}
export function mountSecurity(parent){
 const section=document.createElement('section');section.id='account-security';section.className='research-card account-security';section.hidden=true;
 section.innerHTML='<span class="research-badge">Account security</span><h3>Your signed-in sessions</h3><p>Review active sessions for your own account. Signing out other sessions leaves this session and your password unchanged.</p><button class="btn sm" type="button" data-security-refresh>Refresh security status</button><p data-security-status role="status"></p><div data-security-result></div><form><label class="knowledge-generation"><input type="checkbox" name="acknowledged"> I want to sign out other active sessions for my account.</label><button class="btn" type="submit" disabled>Sign out other sessions</button></form><p class="research-caution">Local account controls only. Device identification, managed identity, MFA and protected auditing are not provided. A person with your password can sign in again.</p>';
 parent.append(section);const result=section.querySelector('[data-security-result]'),status=section.querySelector('[data-security-status]'),refresh=section.querySelector('[data-security-refresh]'),form=section.querySelector('form'),submit=form.querySelector('button');
 let user=null,epoch=0,controller=null,timer=null,snapshot=null,busy=false;
 function controls(){form.elements.acknowledged.disabled=busy||!snapshot||!user;submit.disabled=busy||!user||!snapshot||snapshot.other_active_sessions===0||!form.elements.acknowledged.checked;refresh.disabled=busy||!user;}
 function clear(){clearTimeout(timer);result.replaceChildren();snapshot=null;form.reset();controls();}
 function show(data){snapshot=validateSecurity(data);result.innerHTML=renderSecurity(data);form.reset();clearTimeout(timer);const current=epoch;timer=setTimeout(()=>{if(current!==epoch)return;clear();status.textContent='Security status is stale. Refresh before taking action.';},Math.max(0,Math.min(90000,Date.parse(data.checked_at)+90000-Date.now(),Date.parse(data.current_expires_at)-Date.now())));}
 async function request(revoke=false){
  if(!user||busy)return;if(revoke){try{validateSecurity(snapshot);}catch{clear();status.textContent='Refresh security status before taking action.';return;}if(!form.elements.acknowledged.checked||!snapshot.other_active_sessions)return;}
  const current=++epoch;controller?.abort();controller=new AbortController();const active=controller,timeout=setTimeout(()=>active.abort(),8000);busy=true;controls();status.textContent=revoke?'Signing out other sessions…':'Checking active sessions…';
  try{
   const response=await apiFetch(revoke?'/api/v1/auth/revoke-other-sessions':'/api/v1/auth/security',{...(revoke?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({acknowledged:true})}:{}),signal:active.signal});if(!response.ok)throw new Error();const data=await response.json();if(current!==epoch)return;validateSecurity(data,Date.now(),revoke);show(data);status.textContent=revoke?'Other-session sign-out confirmed at the recorded check. New sign-ins can create new sessions.':'Security status checked. No session was changed.';
  }catch{if(current===epoch){clear();status.textContent=revoke?'Sign-out could not be confirmed. Refresh security status before deciding whether to retry.':'Account security is unavailable. Previous counts have been cleared.';}}
  finally{clearTimeout(timeout);if(current===epoch){busy=false;controls();}}
 }
 form.addEventListener('input',controls);form.addEventListener('submit',event=>{event.preventDefault();request(true);});refresh.addEventListener('click',()=>request());
 return {setSession(value){epoch++;controller?.abort();user=value;busy=false;section.hidden=!user;clear();status.textContent='';if(user)request();}};
}
