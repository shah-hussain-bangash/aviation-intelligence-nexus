const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const hash=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const require=ok=>{if(!ok)throw Error('Unverified case agent response');};
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validateAgentReference(r){
 require(r&&uuid(r.run_id)&&hash(r.sha256)&&hash(r.report_sha256)&&typeof r.objective==='string'&&r.objective.length>0&&r.objective.length<=600&&['reviewed','needs_changes'].includes(r.review_state)&&['standard','second_account'].includes(r.review_kind)&&Number.isInteger(r.step_count)&&r.step_count>=0&&r.step_count<=3);
 return r;
}
export function validateAgentSources(r){
 require(r&&r.production_ready===false&&Array.isArray(r.sources)&&r.sources.length<=20);const seen=new Set();for(const s of r.sources){validateAgentReference(s);require(!seen.has(s.run_id));seen.add(s.run_id);}return r.sources;
}
export function validateAgentLinks(record){
 require(Array.isArray(record.agent_links)&&record.agent_links.length<=5);const ids=new Set(),versions=new Set();
 for(const a of record.agent_links){validateAgentReference(a);require(!ids.has(a.run_id)&&Number.isInteger(a.attached_version)&&a.attached_version>1&&a.attached_version<=record.version&&!versions.has(a.attached_version));ids.add(a.run_id);versions.add(a.attached_version);const e=record.events[a.attached_version-1];require(e.action==='agent'&&e.note==='Attached saved agent report '+a.run_id);}
 require(record.events.filter(e=>e.action==='agent').every(e=>versions.has(e.version)));return record.agent_links;
}
export function renderAgentLinks(record){
 validateAgentLinks(record);return `<section class="case-attachments"><h4>Attached agent findings</h4><p>Review state is captured from the saved record. It does not certify correctness, independent reviewers or airline authority.</p>${record.agent_links.length?record.agent_links.map(a=>`<article><strong>${escape(a.objective)}</strong><p>Recorded state: <strong>${escape(a.review_state)}</strong> · ${a.review_kind==='second_account'?'Second-account review record':'Standard review · second account not required'} · ${a.step_count} saved steps · attached at case v${a.attached_version}</p><p>Run <code>${a.run_id}</code><br>Captured snapshot SHA-256 <code>${a.sha256}</code><br>Report content SHA-256 <code>${a.report_sha256}</code></p><button class="btn sm" type="button" data-agent-run="${a.run_id}">Inspect retained agent report</button></article>`).join(''):'<p>No agent report attached yet.</p>'}<div data-agent-detail></div></section>`;
}
export function renderAgentSnapshot(r,record,reference){
 validateAgentReference(r);require(r.case_id===record.id&&r.case_version===record.version&&r.run_id===reference.run_id&&r.sha256===reference.sha256&&r.report_sha256===reference.report_sha256&&r.attached_version===reference.attached_version&&r.objective===reference.objective&&r.review_state===reference.review_state&&r.review_kind===reference.review_kind&&r.step_count===reference.step_count&&r.research_only===true&&r.operational_approval===false&&r.production_ready===false);
 const s=r.snapshot;require(s&&s.run_id===reference.run_id&&s.state===r.review_state&&s.report_sha256===r.report_sha256&&s.runtime==='bounded-ollama-tools-v2'&&s.request?.objective===r.objective&&s.research_only===true&&s.operational_approval===false&&Array.isArray(s.steps)&&s.steps.length===r.step_count&&Array.isArray(s.reviews)&&s.reviews.length>0&&s.reviews.length<=10&&s.reviews.at(-1).decision===s.state&&s.reviews.every(v=>v.report_sha256===s.report_sha256));
 require(r.review_kind==='second_account'?s.request.require_peer_review===true&&s.reviews.every(v=>v.second_account_review===true&&typeof v.reviewer_id==='string'&&v.reviewer_id.length>0):s.request.require_peer_review!==true);
 return `<h4>Retained agent report snapshot</h4><p class="research-caution">Historical saved record only. Tools and models do not run here. Review status is captured, not a fresh approval; findings and reviewer identity require independent assessment. This record grants no shared-report access or operational authority.</p><pre>${escape(JSON.stringify(s,null,2))}</pre>`;
}
