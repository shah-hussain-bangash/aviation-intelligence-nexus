import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function renderPlatform(status){
  if(status.production_ready!==false||status.recovery.production_qualified!==false)throw new Error('Unexpected production claim');
  if(status.recovery.recorded&&(!Number.isSafeInteger(status.recovery.flight_records)||status.recovery.flight_records<0))throw new Error('Invalid restored record count');
  const drill=status.encrypted_backup_drill;
  if(drill?.recorded&&(!Number.isSafeInteger(drill.flight_records)||drill.flight_records<0||drill.independent_recovery_qualified!==false||drill.production_qualified!==false))throw new Error('Invalid encrypted drill receipt');
  return `<div class="research-kpis"><article><span>Runtime</span><strong>${status.runtime==='local-container'?'Local containers':'Local development'}</strong></article><article><span>Database</span><strong>${status.database_ready?'Reachable':'Unavailable'}</strong></article><article><span>Active v2 model</span><strong>${status.active_model_verified?'Artifact verified':'Unavailable'}</strong></article><article><span>Local AI models</span><strong>${status.ai_models_present?'Present':'Unavailable'}</strong></article></div>
    <p>Release: ${escape(status.release_revision)} · Schema: ${escape(status.schema_version??'unverified')}</p>
    ${status.recovery.recorded?`<div class="agent-quality passed"><strong>Recorded restore checks passed for this instance</strong><p>Restored ${escape(status.recovery.restored_at)} · ${Number(status.recovery.flight_records).toLocaleString('en-US')} flight records.</p><p>File checksums, database integrity and row counts were verified. Existing account credentials were preserved; restored sessions were revoked.</p><p class="research-meta">Snapshot ${escape(status.recovery.snapshot_id)} · Local restore receipt, not a protected audit or continuous recovery guarantee.</p></div>`:'<p class="research-caution">No verified restore receipt is recorded for this instance. Recovery work on another instance does not qualify this one.</p>'}
    ${drill?.recorded?`<div class="agent-quality passed"><strong>Separate encrypted local recovery drill passed</strong><p>${Number(drill.flight_records).toLocaleString('en-US')} flight records restored from authenticated Cobblestone-128 ciphertext · Checked ${escape(drill.checked_at)}.</p><p>Recovery key protected separately with Windows DPAPI for the signed-in Windows account. This records a separate local drill; it does not change the current instance's restore history.</p><p class="research-meta">No independent key escrow, off-site storage or recovery after computer loss is qualified. This receipt is a local record, not a protected audit.</p></div>`:'<p>No verified encrypted-backup drill is recorded here.</p>'}
    <p class="research-caution">Local deployment only. Production qualification, managed TLS, cloud monitoring and protected off-site backup storage remain incomplete.</p>`;
}

export function mountPlatformStatus(parent){
  const section=document.createElement('section');section.className='research-card platform-status';section.setAttribute('aria-labelledby','platformStatusHeading');
  section.innerHTML='<span class="research-badge">Release & recovery</span><h3 id="platformStatusHeading">Know what is running</h3><p>Verified service state and the restore receipt for this specific instance.</p><button class="btn sm" type="button">Refresh service status</button><div class="platform-result" aria-live="polite"></div>';
  parent.append(section);const button=section.querySelector('button'),output=section.querySelector('.platform-result');let generation=0,signedIn=false;
  async function refresh(){if(!signedIn)return;const current=++generation;button.disabled=true;output.textContent='Checking this instance…';try{const response=await apiFetch('/api/v1/research/platform-status',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const status=await response.json();if(current===generation)output.innerHTML=renderPlatform(status);}catch{if(current===generation)output.textContent='Service state could not be verified. Check the backend and your session.';}finally{if(current===generation)button.disabled=false;}}
  button.addEventListener('click',refresh);
  return {setSession(user){generation++;signedIn=!!user;output.replaceChildren();button.disabled=!signedIn;if(signedIn)refresh();}};
}
