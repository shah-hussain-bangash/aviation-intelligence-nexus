import {apiFetch} from './research-auth.mjs';
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const integer=v=>{if(!Number.isSafeInteger(v)||v<0)throw new Error('Invalid intake count');return v;};
const count=v=>integer(v).toLocaleString('en-US');
export function validateIntake(data){
  if(data?.format!=='ain-intake-overview-v1'||!Number.isFinite(Date.parse(data.checked_at))||!/(Z|[+-]\d\d:\d\d)$/.test(data.checked_at))throw new Error('Invalid snapshot');
  for(const k of ['receipt_authenticated','rows_rescanned','import_authorized','import_performed','production_ready'])if(data[k]!==false)throw new Error('Invalid snapshot scope');
  for(const k of ['runs_checked','accepted_runs','quarantined_runs','unverifiable_runs','unique_archives','repeated_accepted_runs','declared_rows'])integer(data[k]);
  if(data.runs_checked>1000||data.runs_checked!==data.accepted_runs+data.quarantined_runs+data.unverifiable_runs||!Array.isArray(data.archives)||data.archives.length>100||data.unique_archives!==data.archives.length||data.repeated_accepted_runs!==data.accepted_runs-data.unique_archives)throw new Error('Invalid snapshot accounting');
  let rows=0,runs=0;const hashes=new Set();
  for(const r of data.archives){if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(r.period)||!/^[a-f0-9]{64}$/.test(r.sha256)||hashes.has(r.sha256)||!integer(r.bytes)||r.bytes>512*1024*1024||!integer(r.declared_rows)||r.declared_rows>5000000||!integer(r.runs)||r.runs>1000)throw new Error('Invalid archive summary');hashes.add(r.sha256);rows+=r.declared_rows;runs+=r.runs;}
  if(rows!==data.declared_rows||runs!==data.accepted_runs||!data.quarantine_reasons||Array.isArray(data.quarantine_reasons)||Object.keys(data.quarantine_reasons).length>30||Object.entries(data.quarantine_reasons).some(([k,v])=>!(/^[a-z_]{1,40}$/).test(k)||!integer(v)||v>1000)||Object.values(data.quarantine_reasons).reduce((n,v)=>n+v,0)!==data.quarantined_runs)throw new Error('Invalid totals');
  return data;
}

export function renderIntake(data){
  validateIntake(data);
  return `<div class="intake-notice"><strong>Historical intake snapshot</strong><span>Checked ${escape(new Date(data.checked_at).toLocaleString('en-GB',{timeZone:'UTC',hour12:false}))} UTC</span><p>Accepted means local structural preflight only. Counts below are unsigned receipt claims. This view does not import records or establish source rights.</p></div>
  <div class="diagnostic-metrics"><div><span>Unique accepted archives</span><strong>${count(data.unique_archives)}</strong></div><div><span>Declared rows · Deduplicated</span><strong>${count(data.declared_rows)}</strong></div><div><span>Quarantined runs</span><strong>${count(data.quarantined_runs)}</strong></div><div><span>Unverifiable runs</span><strong>${count(data.unverifiable_runs)}</strong></div></div>
  <p>${count(data.runs_checked)} runs checked · ${count(data.accepted_runs)} accepted runs · ${count(data.repeated_accepted_runs)} repeated accepted checks excluded from row totals.</p>
  <div class="research-table"><table><caption>One row per accepted archive SHA-256 · Not imported flight counts</caption><thead><tr><th>Declared month</th><th>Archive fingerprint</th><th>Declared rows</th><th>Archive size</th><th>Checks</th></tr></thead><tbody>${data.archives.map(r=>`<tr><th>${escape(r.period)}</th><td><details><summary>${r.sha256.slice(0,12)}…</summary><code class="intake-hash">${r.sha256}</code></details></td><td>${count(r.declared_rows)}</td><td>${(r.bytes/1048576).toFixed(1)} MiB</td><td>${count(r.runs)}</td></tr>`).join('')||'<tr><td colspan="5">No accepted archives in this snapshot.</td></tr>'}</tbody></table></div>
  ${data.quarantined_runs?`<details><summary>Quarantine reasons</summary><ul>${Object.entries(data.quarantine_reasons).map(([k,v])=>`<li>${escape(k.replaceAll('_',' '))}: ${count(v)}</li>`).join('')}</ul></details>`:''}
  <p class="research-caution">Archive bytes were matched to receipts when exported. Rows were not rescanned. The snapshot is editable local metadata, not an authenticated audit or live inventory.</p>`;
}

export function mountIntakeOverview(parent){
  const section=document.createElement('section');section.className='research-card intake-overview';section.hidden=true;section.setAttribute('aria-labelledby','intakeHeading');
  section.innerHTML='<div class="pattern-heading"><div><span class="research-badge">Data platform · Administrator</span><h3 id="intakeHeading">Intake overview</h3><p>Review retained preflight evidence before considering a separate import.</p></div><div class="pattern-controls"><button class="btn sm" type="button" data-refresh>Refresh snapshot</button><button class="btn sm" type="button" data-export disabled>Export snapshot JSON</button></div></div><div data-output aria-live="polite"></div>';
  parent.append(section);const output=section.querySelector('[data-output]'),refresh=section.querySelector('[data-refresh]'),download=section.querySelector('[data-export]');let active=false,generation=0,data=null;
  async function load(){if(!active)return;const token=++generation;data=null;download.disabled=true;refresh.disabled=true;output.textContent='Loading recorded intake snapshot…';try{const response=await apiFetch('/api/v1/research/intake-overview',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const payload=validateIntake(await response.json());if(token!==generation)return;data=payload;output.innerHTML=renderIntake(payload);download.disabled=false;}catch{if(token===generation)output.textContent='Intake snapshot unavailable. Previous results cleared. Run the local intake overview exporter to prepare valid metadata.';}finally{if(token===generation)refresh.disabled=!active;}}
  refresh.addEventListener('click',load);download.addEventListener('click',()=>{if(!active||!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_Intake_Overview.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(user){generation++;active=user?.role==='admin';data=null;output.replaceChildren();section.hidden=!active;download.disabled=true;refresh.disabled=!active;if(active)load();}};
}
