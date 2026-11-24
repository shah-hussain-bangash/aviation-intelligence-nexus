import {apiFetch} from './research-auth.mjs';
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validateLineage(data){
  if(data?.format!=='ain-batch-lineage-view-v1'||data.relation!=='archive_identity_recheck'||data.dataset?.period!=='2025-01'||!Number.isSafeInteger(data.dataset.recorded_rows)||data.dataset.recorded_rows<=0)throw new Error('Invalid lineage');
  for(const k of ['receipt_authenticated','original_import_receipt','live_database_checked','import_performed','production_ready'])if(data[k]!==false)throw new Error('Invalid lineage scope');
  for(const sha of [data.dataset.archive_sha256,data.dataset.audit_report_sha256,data.intake?.receipt_sha256])if(!/^[a-f0-9]{64}$/.test(sha))throw new Error('Invalid evidence digest');
  const r=data.intake;if(!/^[a-f0-9]{32}$/.test(r.run_id)||r.record!=='accepted/'+r.run_id||r.disposition!=='accepted'||!Number.isFinite(Date.parse(r.checked_at))||r.declared_source_url!=='https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2025_1.zip')throw new Error('Invalid intake reference');
  if(data.admin_receipt&&(data.admin_receipt.run_id!==r.run_id||data.admin_receipt.archive_sha256!==data.dataset.archive_sha256))throw new Error('Mismatched admin receipt');
  return data;
}
export function renderLineage(data,admin=false){
  validateLineage(data);const d=data.dataset,r=data.intake;
  return `<p><strong>January 2025 · ${d.recorded_rows.toLocaleString('en-US')} recorded flight rows</strong></p><p>Historical US research data. The archive hash in the recorded data-quality result matches this retained intake archive.</p>
  <dl><dt>Source declared by the receipt</dt><dd><a href="${escape(r.declared_source_url)}" target="_blank" rel="noopener noreferrer">BTS January 2025 reporting-carrier archive</a></dd><dt>Archive SHA-256 · Exact join key</dt><dd class="pattern-fingerprint">${escape(d.archive_sha256)}</dd><dt>Local intake record</dt><dd class="pattern-fingerprint">${escape(r.record)}</dd><dt>Exact receipt bytes · SHA-256</dt><dd class="pattern-fingerprint">${escape(r.receipt_sha256)}</dd><dt>Preflight recorded at</dt><dd>${escape(r.checked_at)}</dd><dt>Pinned data-quality report SHA-256</dt><dd class="pattern-fingerprint">${escape(d.audit_report_sha256)}</dd></dl>
  <p class="research-caution">Archive identity recheck, performed after the original import. This is not the original import receipt, source authentication, a live database check or operational approval. No records were imported by this trace.</p>
  ${admin&&data.admin_receipt?`<details><summary>Administrator · Inspect full intake receipt</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${escape(JSON.stringify(data.admin_receipt,null,2))}</pre></details>`:'<p>Analyst access: recorded dataset, source and receipt reference only. Full intake receipt is restricted to administrators.</p>'}`;
}
export function mountBatchLineage(parent){
  const section=document.createElement('section');section.id='batch-lineage';section.className='research-card';section.hidden=true;section.innerHTML='<h3>January batch lineage</h3><button class="btn sm" type="button">Refresh recorded trace</button><div data-lineage aria-live="polite"></div>';parent.append(section);
  const output=section.querySelector('[data-lineage]'),button=section.querySelector('button');let generation=0,user=null;
  async function load(){if(!user)return;const token=++generation;output.textContent='Loading recorded batch evidence…';button.disabled=true;try{const response=await apiFetch('/api/v1/research/batch-lineage',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const data=validateLineage(await response.json());if(token!==generation)return;output.innerHTML=renderLineage(data,user.role==='admin');}catch{if(token===generation)output.textContent='Batch trace unavailable. No receipt linkage is asserted; previous evidence has been cleared.';}finally{if(token===generation)button.disabled=!user;}}
  button.addEventListener('click',load);return {setSession(value){generation++;user=value;section.hidden=!user;output.replaceChildren();button.disabled=!user;if(user)load();}};
}
