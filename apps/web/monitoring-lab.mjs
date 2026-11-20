import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={database:'Database schema',active_model:'Active model artifact',local_ai_models:'Local AI models'};

export function renderMonitoring(data){
  if(data.production_ready!==false||data.external_alert_delivery!==false||!['healthy','degraded','unknown','disabled'].includes(data.state))throw new Error('Invalid monitoring state');
  const fresh=['healthy','degraded'].includes(data.state);
  const counts=data.request_counts;
  const total=Object.values(counts).reduce((sum,n)=>{if(!Number.isSafeInteger(n)||n<0)throw new Error();return sum+n;},0);
  return `<div class="research-kpis"><article><span>Local monitor</span><strong>${escape(data.state)}</strong></article><article><span>API responses since restart</span><strong>${total.toLocaleString('en-US')}</strong></article><article><span>Server error responses</span><strong>${escape(counts['5xx']??0)}</strong></article><article><span>Recent latency p95</span><strong>${data.latency.p95_ms===null?'No samples':escape(data.latency.p95_ms)+' ms'}</strong></article></div>
    <p>Last sample: ${escape(data.checked_at??'Not sampled')} · Sample age: ${escape(data.sample_age_seconds??'unknown')} seconds · ${escape(data.latency.sample_size)} of at most 200 recent requests in latency window.</p>
    ${fresh?`<ul>${Object.entries(labels).map(([key,label])=>`<li><strong>${label}:</strong> ${data.components[key]===true?'Check passed':'Unavailable'}</li>`).join('')}</ul>`:'<p class="research-caution">Current component health is unknown. Monitoring may be disabled, starting or stale. No healthy status is inferred.</p>'}
    <p>Local snapshot storage: ${data.persistence_ok===true?'Last write succeeded':data.persistence_ok===false?'Last write failed':'Not yet verified'}.</p>
    <h4>Recent component transitions</h4>${data.transitions.length?`<ul>${data.transitions.map(e=>`<li>${escape(e.at)} · ${escape(labels[e.component]??'Component')} · ${escape(e.state)}</li>`).join('')}</ul>`:'<p>No component transitions observed in this process.</p>'}
    <h4>Recent server failures</h4>${data.recent_server_failures.length?`<ul>${data.recent_server_failures.map(e=>`<li>${escape(e.at)} · HTTP ${escape(e.status)}</li>`).join('')}</ul>`:'<p>No server failure responses recorded in this process.</p>'}
    <p class="research-caution">Local observation only. Checks run every 30 seconds and become stale after 90 seconds. Model presence does not prove successful generation. Counters reset on restart; the latest bounded snapshot is stored locally. No external alerts, protected audit, service-level objective or operational approval.</p>`;
}

export function mountMonitoring(parent){
  const section=document.createElement('section');section.className='research-card';section.hidden=true;
  section.setAttribute('aria-labelledby','monitoringHeading');
  section.innerHTML='<span class="research-badge">Service health · administrator</span><h3 id="monitoringHeading">See what needs attention</h3><p>Component checks and API response signals for this running instance.</p><button class="btn sm" type="button">Refresh monitoring</button><div aria-live="polite"></div>';
  parent.append(section);const button=section.querySelector('button'),output=section.querySelector('div');let generation=0,active=false,timer;
  async function refresh(){if(!active)return;const current=++generation;button.disabled=true;try{const response=await apiFetch('/api/v1/research/monitoring',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const data=await response.json();if(current===generation)output.innerHTML=renderMonitoring(data);}catch{if(current===generation)output.textContent='Monitoring could not be reached. Current health is unknown; previously displayed status has been cleared.';}finally{if(current===generation)button.disabled=false;}}
  button.addEventListener('click',refresh);
  return {setSession(user){generation++;clearInterval(timer);active=user?.role==='admin';section.hidden=!active;output.replaceChildren();button.disabled=!active;if(active){refresh();timer=setInterval(refresh,30000);}}};
}
