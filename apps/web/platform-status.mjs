import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function rollbackBinding(status){
  const evidence=status.rollback_drill,b=evidence?.binding;
  if(!b)return 'Historical receipt: this record has no binding to the running build.';
  const messages={legacy_unbound:'Historical receipt: this record has no binding to the running build.',unverified_build:'Running build identity is unverified; this receipt cannot establish a match.',unavailable_contracts:'Selected state contracts could not be checked; a build match is unverified.',schema_mismatch:'Schema differs from the recorded drill. This receipt does not cover the running build.',contract_mismatch:'Selected state contracts differ from the recorded drill. This receipt does not cover the running build.',different_release:'Historical drill for another release. The running candidate has not been covered by this receipt.',matches_current_candidate:'Recorded drill matches this source build, schema and selected state contracts.'};
  if(!Object.hasOwn(messages,b.relation)||typeof b.candidate_matches_current_build!=='boolean')throw new Error('Invalid receipt binding');
  const match=b.relation==='matches_current_candidate';
  if(match!==b.candidate_matches_current_build||match&&(!/^[0-9a-f]{40}$/.test(b.current_revision)||b.current_revision!==status.release_revision||b.current_revision!==evidence.candidate_revision||b.schema_matches!==true||b.state_contracts_match!==true))throw new Error('Contradictory receipt binding');
  return messages[b.relation];
}

export function rollbackExport(status){
  renderPlatform(status);
  if(!status.rollback_drill?.recorded)throw new Error('No recorded rollback evidence');
  const r=status.rollback_drill,b=r.binding;
  return {format:'ain-rollback-display-export-v1',release_revision:status.release_revision,schema_version:status.schema_version,
    rollback_drill:{recorded:true,checked_at:r.checked_at,candidate_revision:r.candidate_revision,rollback_revision:r.rollback_revision,flight_records:r.flight_records,
      binding:b?{relation:b.relation,candidate_matches_current_build:b.candidate_matches_current_build,current_revision:b.current_revision,schema_matches:b.schema_matches,state_contracts_match:b.state_contracts_match}:null},
    scope:'Local isolated application drill receipt; selected checks only; not a protected audit or production failover qualification.',production_qualified:false};
}

export function renderPlatform(status){
  if(status.production_ready!==false||status.recovery.production_qualified!==false)throw new Error('Unexpected production claim');
  if(status.recovery.recorded&&(!Number.isSafeInteger(status.recovery.flight_records)||status.recovery.flight_records<0))throw new Error('Invalid restored record count');
  const drill=status.encrypted_backup_drill;
  const rollback=status.rollback_drill;
  if(rollback?.recorded&&(rollback.production_qualified!==false||!Number.isSafeInteger(rollback.flight_records)||rollback.flight_records<0))throw new Error('Invalid rollback receipt');
  if(drill?.recorded&&(!Number.isSafeInteger(drill.flight_records)||drill.flight_records<0||drill.independent_recovery_qualified!==false||drill.production_qualified!==false))throw new Error('Invalid encrypted drill receipt');
  const bindingMessage=rollback?.recorded?rollbackBinding(status):'';
  return `<div class="research-kpis"><article><span>Runtime</span><strong>${status.runtime==='local-container'?'Local containers':'Local development'}</strong></article><article><span>Database</span><strong>${status.database_ready?'Reachable':'Unavailable'}</strong></article><article><span>Active v2 model</span><strong>${status.active_model_verified?'Artifact verified':'Unavailable'}</strong></article><article><span>Local AI models</span><strong>${status.ai_models_present?'Present':'Unavailable'}</strong></article></div>
    <p>Release: ${escape(status.release_revision)} · Schema: ${escape(status.schema_version??'unverified')}</p>
    ${status.recovery.recorded?`<div class="agent-quality passed"><strong>Recorded restore checks passed for this instance</strong><p>Restored ${escape(status.recovery.restored_at)} · ${Number(status.recovery.flight_records).toLocaleString('en-US')} flight records.</p><p>File checksums, database integrity and row counts were verified. Existing account credentials were preserved; restored sessions were revoked.</p><p class="research-meta">Snapshot ${escape(status.recovery.snapshot_id)} · Local restore receipt, not a protected audit or continuous recovery guarantee.</p></div>`:'<p class="research-caution">No verified restore receipt is recorded for this instance. Recovery work on another instance does not qualify this one.</p>'}
    ${drill?.recorded?`<div class="agent-quality passed"><strong>Separate encrypted local recovery drill passed</strong><p>${Number(drill.flight_records).toLocaleString('en-US')} flight records restored from authenticated Cobblestone-128 ciphertext · Checked ${escape(drill.checked_at)}.</p><p>Recovery key protected separately with Windows DPAPI for the signed-in Windows account. This records a separate local drill; it does not change the current instance's restore history.</p><p class="research-meta">No independent key escrow, off-site storage or recovery after computer loss is qualified. This receipt is a local record, not a protected audit.</p></div>`:'<p>No verified encrypted-backup drill is recorded here.</p>'}
    ${rollback?.recorded?`<div class="agent-quality ${rollback.binding?.candidate_matches_current_build?'passed':''}"><strong>Isolated application rollback drill recorded</strong><p class="research-caution">${escape(bindingMessage)}</p><p>Recorded ${escape(rollback.checked_at)} · ${Number(rollback.flight_records).toLocaleString('en-US')} flight records preserved.</p><p>Candidate ${escape(rollback.candidate_revision)} → previous ${escape(rollback.rollback_revision.slice(0,12))} → candidate healthy again. The same isolated data volume, accounts, model, index and research prediction were checked across the switches.</p><p class="research-meta">Separate restored local copy; your main deployment was not rolled back. No database downgrade, model/prompt rollback, zero-downtime release or production failover is qualified. This is a local receipt, not a protected audit.</p></div>`:'<p>No verified isolated application rollback drill is recorded here.</p>'}
    <p class="research-caution">Local deployment only. Production qualification, managed TLS, cloud monitoring and protected off-site backup storage remain incomplete.</p>`;
}

export function mountPlatformStatus(parent){
  const section=document.createElement('section');section.className='research-card platform-status';section.setAttribute('aria-labelledby','platformStatusHeading');
  section.innerHTML='<span class="research-badge">Release & recovery</span><h3 id="platformStatusHeading">Know what is running</h3><p>Verified service state and the restore receipt for this specific instance.</p><button class="btn sm" type="button">Refresh service status</button> <button class="btn sm rollback-export" type="button" disabled>Export rollback evidence</button><div class="platform-result" aria-live="polite"></div>';
  parent.append(section);const button=section.querySelector('button'),exportButton=section.querySelector('.rollback-export'),output=section.querySelector('.platform-result');let generation=0,signedIn=false,latest=null,controller=null;
  async function refresh(){if(!signedIn)return;const current=++generation;controller?.abort();controller=new AbortController();const activeController=controller;const timer=setTimeout(()=>activeController.abort(),10000);button.disabled=true;exportButton.disabled=true;latest=null;output.textContent='Checking this instance…';try{const response=await apiFetch('/api/v1/research/platform-status',{signal:controller.signal});if(!response.ok)throw new Error();const status=await response.json();if(current===generation){output.innerHTML=renderPlatform(status);latest=status;exportButton.disabled=!status.rollback_drill?.recorded;}}catch{if(current===generation)output.textContent='Service state could not be verified. Check the backend and your session.';}finally{clearTimeout(timer);if(current===generation)button.disabled=false;}}
  button.addEventListener('click',refresh);
  exportButton.addEventListener('click',()=>{if(!signedIn||!latest)return;const url=URL.createObjectURL(new Blob([JSON.stringify(rollbackExport(latest),null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='ain-rollback-evidence.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(user){generation++;controller?.abort();signedIn=!!user;latest=null;output.replaceChildren();button.disabled=!signedIn;exportButton.disabled=true;if(signedIn)refresh();}};
}
