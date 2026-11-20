import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function renderPlatform(status){
  if(status.production_ready!==false||status.recovery.production_qualified!==false)throw new Error('Unexpected production claim');
  if(status.recovery.recorded&&(!Number.isSafeInteger(status.recovery.flight_records)||status.recovery.flight_records<0))throw new Error('Invalid restored record count');
  return `<div class="research-kpis"><article><span>Runtime</span><strong>${status.runtime==='local-container'?'Local containers':'Local development'}</strong></article><article><span>Database</span><strong>${status.database_ready?'Reachable':'Unavailable'}</strong></article><article><span>Active v2 model</span><strong>${status.active_model_verified?'Artifact verified':'Unavailable'}</strong></article><article><span>Local AI models</span><strong>${status.ai_models_present?'Present':'Unavailable'}</strong></article></div>
    <p>Release: ${escape(status.release_revision)} · Schema: ${escape(status.schema_version??'unverified')}</p>
    ${status.recovery.recorded?`<div class="agent-quality passed"><strong>Recorded restore checks passed for this instance</strong><p>Restored ${escape(status.recovery.restored_at)} · ${Number(status.recovery.flight_records).toLocaleString('en-US')} flight records.</p><p>File checksums, database integrity and row counts were verified. Existing account credentials were preserved; restored sessions were revoked.</p><p class="research-meta">Snapshot ${escape(status.recovery.snapshot_id)} · Local restore receipt, not a protected audit or continuous recovery guarantee.</p></div>`:'<p class="research-caution">No verified restore receipt is recorded for this instance. Recovery work on another instance does not qualify this one.</p>'}
    <p class="research-caution">Local deployment only. Production qualification, managed TLS, cloud monitoring and protected backup storage remain incomplete.</p>`;
}

export function mountPlatformStatus(parent){
  const section=document.createElement('section');section.className='research-card platform-status';section.setAttribute('aria-labelledby','platformStatusHeading');
  section.innerHTML='<span class="research-badge">Release & recovery</span><h3 id="platformStatusHeading">Know what is running</h3><p>Verified service state and the restore receipt for this specific instance.</p><button class="btn sm" type="button">Refresh service status</button><div class="platform-result" aria-live="polite"></div>';
  parent.append(section);const button=section.querySelector('button'),output=section.querySelector('.platform-result');let generation=0,signedIn=false;
  async function refresh(){if(!signedIn)return;const current=++generation;button.disabled=true;output.textContent='Checking this instance…';try{const response=await apiFetch('/api/v1/research/platform-status',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const status=await response.json();if(current===generation)output.innerHTML=renderPlatform(status);}catch{if(current===generation)output.textContent='Service state could not be verified. Check the backend and your session.';}finally{if(current===generation)button.disabled=false;}}
  button.addEventListener('click',refresh);
  return {setSession(user){generation++;signedIn=!!user;output.replaceChildren();button.disabled=!signedIn;if(signedIn)refresh();}};
}
