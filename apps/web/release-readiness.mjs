import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const states={local_evidence:'Local evidence recorded · production open',evidence_unavailable:'Evidence unavailable · production open',planned:'Planned · production open'};

export function filterReadiness(data,query='',filter='all'){
  const search=query.trim().toLowerCase();
  return data.requirements.filter(r=>(filter==='all'||r.assessment_state===filter)&&[r.id,r.name,r.owner_role,r.local_progress,r.remaining,r.acceptance].join(' ').toLowerCase().includes(search));
}

export function renderReadiness(data,query='',filter='all'){
  if(data.production_ready!==false||data.production_accepted!==0||data.production_open!==24||data.total!==24||data.requirements.length!==24||new Set(data.requirements.map(r=>r.id)).size!==24)throw new Error('Unsupported readiness claim');
  for(const row of data.requirements){
    if(row.production_accepted!==false||!states[row.assessment_state]||!/^P(?:0[1-9]|1[0-9]|2[0-4])$/.test(row.id))throw new Error('Invalid requirement');
  }
  const rows=filterReadiness(data,query,filter);
  return `<div class="research-kpis"><article><span>Production requirements</span><strong>24</strong></article><article><span>Production acceptance</span><strong>Open</strong></article><article><span>Local evidence recorded</span><strong>${data.requirements.filter(r=>r.assessment_state==='local_evidence').length}</strong></article><article><span>Production requirements open</span><strong>24</strong></article></div>
    <p>Scope assessed ${escape(data.assessed_at)} · File checks ${escape(data.checked_at)} · Source ${escape(data.source_revision)}.</p>
    <p class="research-caution">This is a dated maintainer assessment. File checks confirm recorded evidence is present and unchanged; they do not independently accept production requirements or replace live service monitoring. No completion percentage or airline approval is claimed.</p>
    <p role="status">${rows.length} of 24 requirements shown.</p>
    ${rows.length?rows.map(row=>`<details class="research-card"><summary><strong>${escape(row.id)} · ${escape(row.name)}</strong> — ${escape(states[row.assessment_state])}</summary><p><strong>Implemented scope:</strong> ${escape(row.local_progress)}</p><p><strong>Still required:</strong> ${escape(row.remaining)}</p><p><strong>Production acceptance:</strong> ${escape(row.acceptance)}</p><p>Responsible role: ${escape(row.owner_role)} · Dependencies: ${escape(row.dependencies.join(', ')||'None listed')}. Role labels are proposed responsibilities, not assigned personnel.</p><h4>Recorded public evidence</h4>${row.evidence.length?`<ul>${row.evidence.map(item=>{
      if(!/^https:\/\/github\.com\/zenithdevelopers7-source\/aviation-intelligence-nexus\/blob\/(?:main|[0-9a-f]{40})\/docs\/(?:reports\/)?[A-Za-z0-9_.-]+\.(?:md|json)$/.test(item.url))throw new Error('Unapproved evidence link');
      return `<li><a href="${escape(item.url)}" target="_blank" rel="noopener noreferrer">${escape(item.path)}</a> · ${item.integrity_verified===true?'Recorded file verified':'File missing or changed; reassessment required'}</li>`;
    }).join('')}</ul>`:'<p>No local implementation evidence registered for this requirement.</p>'}</details>`).join(''):'<p>No requirements match. Clear the search or choose all requirements.</p>'}`;
}

export function mountReadiness(parent){
  const section=document.createElement('section');section.className='research-card release-readiness';section.setAttribute('aria-labelledby','releaseReadinessHeading');
  section.innerHTML='<span class="research-badge">Scope & evidence · read only</span><h3 id="releaseReadinessHeading" tabindex="-1">What is ready, and what remains?</h3><p>Review current local progress across the original 24 production requirements.</p><div class="research-toolbar"><button class="btn sm" type="button">Refresh readiness evidence</button><button class="btn sm" type="button" disabled>Export readiness (JSON)</button></div><div class="readiness-controls"><label for="readinessSearch">Search requirements</label><input class="control" id="readinessSearch" type="search" maxlength="200"><label for="readinessFilter">Evidence filter</label><select class="control" id="readinessFilter"><option value="all">All requirements</option><option value="local_evidence">Local evidence recorded</option><option value="evidence_unavailable">Evidence missing or changed</option><option value="planned">Planned</option></select></div><div aria-live="polite"></div>';
  parent.append(section);const [refresh,exportButton]=section.querySelectorAll('button'),search=section.querySelector('input'),select=section.querySelector('select'),output=section.querySelector('[aria-live]');let generation=0,active=false,data;
  function draw(){try{output.innerHTML=renderReadiness(data,search.value,select.value);}catch{data=null;exportButton.disabled=true;output.textContent='Readiness evidence could not be verified. No acceptance claim is returned.';}}
  async function load(){if(!active)return;const current=++generation;refresh.disabled=true;exportButton.disabled=true;data=null;output.textContent='Checking the scope and recorded evidence…';try{const response=await apiFetch('/api/v1/research/readiness',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const result=await response.json();if(current===generation){data=result;draw();exportButton.disabled=!data;}}catch{if(current===generation)output.textContent='Readiness evidence could not be reached. Previously displayed assessments have been cleared.';}finally{if(current===generation)refresh.disabled=false;}}
  refresh.addEventListener('click',load);search.addEventListener('input',()=>{if(data)draw();});select.addEventListener('change',()=>{if(data)draw();});
  exportButton.addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_Release_Readiness.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(user){generation++;active=!!user;data=null;output.replaceChildren();refresh.disabled=!active;exportButton.disabled=true;if(active)load();}};
}
