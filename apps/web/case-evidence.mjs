const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const hash=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const require=ok=>{if(!ok)throw Error('Unverified case evidence response');};
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function validateEvidenceReference(r){
 require(r&&uuid(r.run_id)&&hash(r.sha256)&&typeof r.question==='string'&&r.question.length>0&&r.question.length<=600&&['generated','evidence_only','abstained'].includes(r.mode)&&Number.isInteger(r.evidence_count)&&r.evidence_count>=0&&r.evidence_count<=8);
 return r;
}
export function validateEvidenceSources(r){
 require(r&&r.production_ready===false&&Array.isArray(r.sources)&&r.sources.length<=20);
 const seen=new Set();for(const s of r.sources){validateEvidenceReference(s);require(!seen.has(s.run_id));seen.add(s.run_id);}
 return r.sources;
}
export function validateAttachments(record){
 require(Array.isArray(record.attachments)&&record.attachments.length<=10);
 const seen=new Set(),versions=new Set();for(const r of record.attachments){validateEvidenceReference(r);require(!seen.has(r.run_id)&&Number.isInteger(r.attached_version)&&r.attached_version>1&&r.attached_version<=record.version&&!versions.has(r.attached_version));seen.add(r.run_id);versions.add(r.attached_version);const e=record.events[r.attached_version-1];require(e.action==='evidence'&&e.note==='Attached saved research evidence '+r.run_id);}
 require(record.events.filter(e=>e.action==='evidence').every(e=>versions.has(e.version)));
 return record.attachments;
}
export function renderAttachmentReferences(record){
 validateAttachments(record);
 return `<section class="case-attachments"><h4>Attached research evidence</h4><p>Linkage records what was saved, not whether it answers the investigation question.</p>${record.attachments.length?record.attachments.map(a=>`<article><strong>${escape(a.question)}</strong><p>${escape(a.mode)} · ${a.evidence_count} passages · attached at case v${a.attached_version}</p><p>Run <code>${a.run_id}</code><br>Snapshot SHA-256 <code>${a.sha256}</code></p><button type="button" class="btn sm" data-evidence-run="${a.run_id}">Inspect retained evidence</button></article>`).join(''):'<p>No evidence attached yet.</p>'}<div data-evidence-detail></div></section>`;
}
export function renderEvidenceSnapshot(r,record,reference){
 validateEvidenceReference(r);
 require(r.case_id===record.id&&r.case_version===record.version&&r.run_id===reference.run_id&&r.sha256===reference.sha256&&r.attached_version===reference.attached_version&&r.question===reference.question&&r.mode===reference.mode&&r.evidence_count===reference.evidence_count&&r.research_only===true&&r.operational_approval===false&&r.production_ready===false);
 const s=r.snapshot;require(s&&s.run_id===reference.run_id&&s.question===r.question&&s.mode===r.mode&&s.research_only===true&&s.operational_approval===false&&Array.isArray(s.evidence)&&s.evidence.length===r.evidence_count&&Array.isArray(s.claims)&&s.claims.length<=3);
 return `<h4>Retained evidence snapshot</h4><p class="research-caution">Saved response only. Source bytes and citations are not revalidated here; answer relevance and correctness require human review. This attachment does not run a model or approve an airline action.</p><pre>${escape(JSON.stringify(s,null,2))}</pre>`;
}
