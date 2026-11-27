const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ratings=['','yes','no','uncertain'];
function require(ok){if(!ok)throw Error('Review bindings or ratings changed');}
export function template(packet,hash){
 require(packet.format==='ain-case-usefulness-packet-v1'&&/^[a-f0-9]{64}$/.test(hash));
 return {format:'ain-case-usefulness-annotations-v1',packet_sha256:hash,reviewer_label:'',source_checked:false,own_assessment:false,question_answered:'',claims:packet.run.claims.map((c,i)=>({claim_index:i,citation:c.citation,supported:'',relevant:''})),notes:''};
}
export function assess(packet,hash,value){
 const initial=template(packet,hash);require(value&&Object.keys(value).sort().join()===Object.keys(initial).sort().join()&&value.format===initial.format&&value.packet_sha256===hash);
 require(typeof value.reviewer_label==='string'&&value.reviewer_label.length<=80&&typeof value.notes==='string'&&value.notes.length<=2000&&typeof value.source_checked==='boolean'&&typeof value.own_assessment==='boolean'&&ratings.includes(value.question_answered));
 require(Array.isArray(value.claims)&&value.claims.length===initial.claims.length);
 const decisions=[value.question_answered];value.claims.forEach((c,i)=>{const expected=initial.claims[i];require(c&&Object.keys(c).sort().join()===Object.keys(expected).sort().join()&&c.claim_index===i&&c.citation===expected.citation&&ratings.includes(c.supported)&&ratings.includes(c.relevant));decisions.push(c.supported,c.relevant);});
 const pending=!value.reviewer_label.trim()||!value.source_checked||!value.own_assessment||decisions.some(v=>v===''||v==='uncertain');
 return {status:pending?'pending':decisions.includes('no')?'declared_needs_revision':'declared_acceptable',human_identity_verified:false,independent_review:false,operational_approval:false,production_ready:false};
}
const select=(label,name)=>`<label>${label}<select name="${name}"><option value="">Choose your rating</option><option value="yes">Yes</option><option value="no">No</option><option value="uncertain">Uncertain</option></select></label>`;
export function resumeReview(packet,hash,text){
 require(typeof text==='string'&&new TextEncoder().encode(text).length<=65536);
 const value=JSON.parse(text);assess(packet,hash,value);
 // Imported declarations cannot establish that the current reviewer inspected
 // sources or personally made these decisions. Require fresh acknowledgement.
 value.source_checked=false;value.own_assessment=false;
 return value;
}
function resumeControls(){
 return `<details><summary>Resume a saved review</summary><p>Paste the JSON you saved for this exact case packet. It stays in this page; nothing is uploaded. Valid ratings replace the current entries only when you choose Load saved ratings. Imported declarations are unsigned, and both acknowledgements must be confirmed again.</p><label>Saved review JSON<textarea data-resume rows="6" maxlength="65536" spellcheck="false" placeholder="Paste your saved review JSON here"></textarea></label><button type="button" data-load>Load saved ratings</button><p data-load-message role="status" aria-live="polite">No saved review loaded.</p></details>`;
}
export function executionRows(receipt={}){
 const fields=[
  ['Historical prediction','prediction_inference_executed','prediction_fixture','Historical US scenario; no actual-flight confirmation.'],
  ['Document retrieval','retrieval_executed','qa_fixture','Retrieval from the fixed public project-document corpus.'],
  ['Document answer generation','qa_generation_executed','qa_fixture','Grounding checks do not establish answer usefulness.'],
  ['Background worker','worker_loop_executed','deterministic_checkpoint_fixture','One local worker; no external failover qualification.'],
  ['Agent planning','planner_executed','deterministic_checkpoint_fixture','Bounded local model calls; no airline action authority.'],
  ['Agent answer generation','generator_executed','deterministic_checkpoint_fixture','Findings still require your assessment.'],
  ['Recorded distribution evidence','recorded_distribution_reader_executed','deterministic_checkpoint_fixture','Recorded historical measurements, not a live airline feed.'],
  ['Gate optimization','synthetic_milp_executed',null,'Synthetic gate scenario; no dispatch or resource-allocation authority.']
 ];
 return fields.map(([label,key,fixture,note])=>{
  const executed=receipt?.passed===true&&receipt[key]===true&&(!fixture||receipt[fixture]!==true);
  const simulated=receipt?.passed===true&&fixture&&receipt[key]===false&&receipt[fixture]===true;
  return {label,note,status:executed?(key==='synthetic_milp_executed'?'Executed · synthetic':'Executed in rehearsal'):simulated?'Fixture only':'Not confirmed',kind:executed?'executed':simulated?'fixture':'unconfirmed'};
 });
}
export function renderExecution(receipt){
 const r=receipt??{};
 const revision=typeof r.source_revision==='string'&&/^[a-f0-9]{40}$/.test(r.source_revision)?r.source_revision:'Not recorded';
 const checks=r.checks&&typeof r.checks==='object'&&!Array.isArray(r.checks)?Object.values(r.checks):[];
 const counts=checks.length?`${checks.filter(v=>v===true).length} of ${checks.length} recorded checks passed`:'Check inventory not recorded';
 return `<section aria-labelledby="execution-heading"><h2 id="execution-heading">What actually ran?</h2><p>Execution evidence describes this recorded rehearsal. It does not measure accuracy, usefulness or production readiness.</p><dl><dt>Source revision</dt><dd><code>${escape(revision)}</code></dd><dt>Transport</dt><dd>${r.transport==='in_process_asgi_testclient'?'In-process API rehearsal · not a deployed browser journey':'Transport not confirmed'}</dd><dt>Recorded checks</dt><dd>${escape(counts)}</dd></dl><ul class="execution-grid">${executionRows(r).map(row=>`<li><h3>${escape(row.label)}</h3><span class="execution-status ${row.kind}">${escape(row.status)}</span><p>${escape(row.note)}</p></li>`).join('')}</ul><p class="execution-limit">Accounts, saved review decisions and gate scenarios are synthetic. Your assessment below covers agent findings; it does not rate the prediction, document Q&A or gate proposal.</p></section>`;
}
export function renderPacket(packet){
 const r=packet.run;
 return `<header><p class="eyebrow">AVIATION INTELLIGENCE NEXUS · PRIVATE REVIEW</p><h1>Was this investigation useful?</h1><p>Inspect the findings against their evidence, then record your own assessment.</p><span class="badge">Ratings pending · research only</span></header><main><section class="notice"><strong>Review scope</strong><p>This is a synthetic research case. The frozen execution receipt identifies which components actually ran and which used fixtures. Your new ratings are unsigned declarations; they do not change the saved case, verify your identity or approve airline operations.</p></section>${renderExecution(packet.receipt)}<section><h2>The investigation</h2><p>${escape(r.request.objective)}</p><dl><dt>Case</dt><dd>${escape(packet.case.title)} · v${packet.case.version} · ${escape(packet.case.status)}</dd><dt>Model</dt><dd>${escape(r.model.name)}</dd><dt>Report fingerprint</dt><dd><code>${escape(r.report_sha256)}</code></dd></dl><p>Earlier saved review: <strong>${escape(r.state)}</strong>. Closing the fixture case did not accept its findings.</p></section><section><h2>Findings and evidence</h2>${r.claims.map((c,i)=>`<article><h3>Finding ${i+1}</h3><blockquote>${escape(c.text)}</blockquote><p>Citation: <code>${escape(c.citation)}</code></p><details><summary>Inspect full supporting evidence</summary><pre>${escape(packet.evidence.find(e=>e.id===c.citation)?.text??'Evidence unavailable')}</pre></details></article>`).join('')}</section><form>${resumeControls()}<h2>Your assessment</h2><p>Leave a rating blank or choose Uncertain when you cannot assess it. Automated quote checks do not establish usefulness.</p><label>Reviewer label<input name="reviewer" maxlength="80" autocomplete="off" placeholder="Your name or private label"></label>${select('Does the report answer the investigation objective?','answered')}${r.claims.map((c,i)=>`<fieldset><legend>Finding ${i+1} · ${escape(c.citation)}</legend>${select('Is it supported by the quoted evidence?','supported-'+i)}${select('Is it relevant and useful for this research objective?','relevant-'+i)}</fieldset>`).join('')}<label class="check"><input type="checkbox" name="sources"> I inspected the supporting evidence and its limitations.</label><label class="check"><input type="checkbox" name="own"> These are my own assessment decisions.</label><label>Review notes<textarea name="notes" maxlength="2000" rows="4" placeholder="What is useful, missing or misleading?"></textarea></label><p data-status role="status" aria-live="polite">Pending — no ratings supplied.</p><button type="button" data-show>Show review JSON</button> <button type="button" data-download>Download my review JSON</button><label data-export-label hidden>Review JSON to save<textarea data-export readonly rows="10"></textarea></label><p>Download saves a local file. It does not submit a review to the dashboard or change any account, case or model.</p></form><details><summary>Inspect the frozen case and report</summary><pre>${escape(JSON.stringify(packet,null,2))}</pre></details><footer>Local self-review · no network calls · no operational authority</footer></main>`;
}
export function mount(parent,packet,hash){
 parent.innerHTML=renderPacket(packet);const form=parent.querySelector('form');
 function snapshot(){const value=template(packet,hash);Object.assign(value,{reviewer_label:form.elements.reviewer.value,question_answered:form.elements.answered.value,source_checked:form.elements.sources.checked,own_assessment:form.elements.own.checked,notes:form.elements.notes.value});value.claims.forEach((c,i)=>{c.supported=form.elements['supported-'+i].value;c.relevant=form.elements['relevant-'+i].value;});return value;}
 function invalidateExport(){parent.querySelector('[data-export]').value='';parent.querySelector('[data-export-label]').hidden=true;}
 function updateStatus(){parent.querySelector('[data-status]').textContent=assess(packet,hash,snapshot()).status.replaceAll('_',' ')+' · unsigned self-declaration';}
 form.addEventListener('input',()=>{invalidateExport();updateStatus();});
 parent.querySelector('[data-load]').addEventListener('click',()=>{
  try{
   const value=resumeReview(packet,hash,parent.querySelector('[data-resume]').value);
   form.elements.reviewer.value=value.reviewer_label;form.elements.answered.value=value.question_answered;
   form.elements.sources.checked=false;form.elements.own.checked=false;form.elements.notes.value=value.notes;
   value.claims.forEach((c,i)=>{form.elements['supported-'+i].value=c.supported;form.elements['relevant-'+i].value=c.relevant;});
   invalidateExport();updateStatus();parent.querySelector('[data-resume]').value='';
   parent.querySelector('[data-load-message]').textContent='Saved ratings loaded. Confirm both acknowledgements yourself; the declaration remains pending.';
  }catch{
   parent.querySelector('[data-load-message]').textContent='Review not loaded. Use valid JSON up to 64 KiB for this exact packet and citations. Current entries were kept.';
  }
 });
 parent.querySelector('[data-show]').addEventListener('click',()=>{const value=snapshot();assess(packet,hash,value);parent.querySelector('[data-export]').value=JSON.stringify(value,null,2);parent.querySelector('[data-export-label]').hidden=false;});
 parent.querySelector('[data-download]').addEventListener('click',()=>{const value=snapshot();assess(packet,hash,value);const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_Case_Usefulness_Review.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
}
