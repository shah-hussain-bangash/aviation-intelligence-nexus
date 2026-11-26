const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const hash=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const require=ok=>{if(!ok)throw Error('Unverified synthetic gate attachment');};
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validateGateReference(r){
 require(r&&uuid(r.run_id)&&hash(r.sha256)&&hash(r.proposal_sha256)&&hash(r.scenario_sha256)&&r.data_kind==='synthetic'&&['reviewed','needs_changes'].includes(r.review_state)&&Number.isInteger(r.flight_count)&&r.flight_count>=1&&r.flight_count<=16);
 for(const k of ['candidate_assigned','candidate_unassigned','baseline_assigned','baseline_unassigned'])require(Number.isInteger(r[k])&&r[k]>=0&&r[k]<=r.flight_count);
 require(r.candidate_assigned+r.candidate_unassigned===r.flight_count&&r.baseline_assigned+r.baseline_unassigned===r.flight_count);return r;
}
export function validateGateSources(r){
 require(r&&r.production_ready===false&&Array.isArray(r.sources)&&r.sources.length<=20);const seen=new Set();for(const s of r.sources){validateGateReference(s);require(!seen.has(s.run_id));seen.add(s.run_id);}return r.sources;
}
export function validateGateLinks(record){
 require(Array.isArray(record.gate_links)&&record.gate_links.length<=5);const ids=new Set(),versions=new Set();
 for(const a of record.gate_links){validateGateReference(a);require(!ids.has(a.run_id)&&Number.isInteger(a.attached_version)&&a.attached_version>1&&a.attached_version<=record.version&&!versions.has(a.attached_version));ids.add(a.run_id);versions.add(a.attached_version);const e=record.events[a.attached_version-1];require(e.action==='gate'&&e.note==='Attached synthetic gate proposal '+a.run_id);}
 require(record.events.filter(e=>e.action==='gate').every(e=>versions.has(e.version)));return record.gate_links;
}
export function renderGateLinks(record){
 validateGateLinks(record);return `<section class="case-attachments"><h4>Attached synthetic gate proposals</h4><p>Research simulations only. Recorded reviews do not authorize airport operations; no allocation is applied.</p>${record.gate_links.length?record.gate_links.map(a=>`<article><strong>Synthetic proposal · ${a.flight_count} flights</strong><p>Recorded state: <strong>${escape(a.review_state)}</strong> · attached at case v${a.attached_version}</p><table><caption>Captured synthetic plan comparison</caption><thead><tr><th>Plan</th><th>Assigned</th><th>Unassigned</th></tr></thead><tbody><tr><th>Candidate</th><td>${a.candidate_assigned}</td><td>${a.candidate_unassigned}</td></tr><tr><th>Greedy baseline</th><td>${a.baseline_assigned}</td><td>${a.baseline_unassigned}</td></tr></tbody></table><p>Run <code>${a.run_id}</code><br>Captured snapshot SHA-256 <code>${a.sha256}</code><br>Proposal SHA-256 <code>${a.proposal_sha256}</code><br>Scenario SHA-256 <code>${a.scenario_sha256}</code></p><button class="btn sm" type="button" data-gate-run="${a.run_id}">Inspect retained gate proposal</button></article>`).join(''):'<p>No gate proposal attached yet.</p>'}<div data-gate-detail></div></section>`;
}
export function renderGateSnapshot(r,record,reference){
 validateGateReference(r);require(r.case_id===record.id&&r.case_version===record.version&&r.attached_version===reference.attached_version&&r.research_only===true&&r.operational_approval===false&&r.production_ready===false);
 for(const k of ['run_id','sha256','proposal_sha256','scenario_sha256','data_kind','review_state','flight_count','candidate_assigned','candidate_unassigned','baseline_assigned','baseline_unassigned'])require(r[k]===reference[k]);
 const s=r.snapshot;require(s&&s.run_id===r.run_id&&s.proposal_sha256===r.proposal_sha256&&s.scenario_sha256===r.scenario_sha256&&s.engine==='scipy-highs-milp'&&s.formulation_version==='gate-v1'&&s.scenario?.data_kind==='synthetic'&&Array.isArray(s.scenario.flights)&&s.scenario.flights.length===r.flight_count&&s.review?.decision===r.review_state&&s.review.proposal_sha256===r.proposal_sha256&&s.research_only===true&&s.operational_approval===false);
 for(const plan of ['candidate','baseline'])require(s[plan]?.verification?.feasible===true&&s[plan].verification.assigned===r[plan+'_assigned']&&s[plan].verification.unassigned===r[plan+'_unassigned']);
 return `<h4>Retained synthetic gate proposal</h4><p class="research-caution">Saved research simulation only. The server checks the captured plans and review receipt without running the solver again. This is not a fresh review, live airport plan or proof of source authenticity. No gate allocation is applied.</p><pre>${escape(JSON.stringify(s,null,2))}</pre>`;
}
