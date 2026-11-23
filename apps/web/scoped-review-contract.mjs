import {scopedExport} from './scoped-lab-contract.mjs';
const choices=['yes','no','uncertain'];
const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&JSON.stringify(Object.keys(value).sort())===JSON.stringify([...keys].sort());

export function canonical(value){
 if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
 if(typeof value==='number'&&Number.isFinite(value))return JSON.stringify(value);
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(value&&typeof value==='object'&&[Object.prototype,null].includes(Object.getPrototypeOf(value)))return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
 throw Error('Unsupported review value');
}
export async function sha256(value){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value))))].map(v=>v.toString(16).padStart(2,'0')).join('');}
export function reviewResult(value){
 if(value?.format!=='ain-scoped-lab-export-v1'||typeof value.question!=='string'||value.question.length<8||value.question.length>600)throw Error('Use an exported scoped research result');
 return scopedExport({...value,format:'ain-scoped-lab-v1'},{question:value.question,experiment:value.experiment});
}
export function validateAnnotations(result,a){
 if(!exact(a,['source_checked','question_answered','decision_appropriate','claims','notes'])||typeof a.source_checked!=='boolean'||typeof a.notes!=='string'||a.notes.length>2000||!Array.isArray(a.claims)||a.claims.length!==result.claims.length)throw Error('Invalid self-review fields');
 if(result.mode==='excerpts'){
  if(!choices.includes(a.question_answered)||a.decision_appropriate!=='not_applicable')throw Error('Invalid excerpt assessment');
 }else if(a.question_answered!=='not_applicable'||(result.mode==='evidence_only'?a.decision_appropriate!=='not_evaluable':!choices.includes(a.decision_appropriate)))throw Error('Invalid refusal assessment');
 a.claims.forEach((c,i)=>{if(!exact(c,['claim_index','citation','supported','relevant'])||c.claim_index!==i||c.citation!==result.claims[i].citation||!choices.includes(c.supported)||!choices.includes(c.relevant))throw Error('Review belongs to another excerpt');});
 return structuredClone(a);
}
export function assessment(result,annotations){
 const a=validateAnnotations(result,annotations);
 if(result.mode==='evidence_only')return 'not_evaluable';
 if(!a.source_checked)return 'draft';
 if(result.mode==='excerpts'){
  if(a.question_answered==='uncertain'||a.claims.some(c=>c.supported==='uncertain'||c.relevant==='uncertain'))return 'draft';
  return a.question_answered==='yes'&&a.claims.every(c=>c.supported==='yes'&&c.relevant==='yes')?'self_reviewed':'needs_revision';
 }
 if(a.decision_appropriate==='uncertain')return 'draft';
 return a.decision_appropriate==='yes'?'self_reviewed_refusal':'refusal_needs_revision';
}
export async function buildReview(value,annotations,createdAt=new Date().toISOString()){
 const result=reviewResult(value),a=validateAnnotations(result,annotations);
 if(typeof createdAt!=='string'||!Number.isFinite(Date.parse(createdAt))||new Date(createdAt).toISOString()!==createdAt)throw Error('Invalid review timestamp');
 const payload={format:'ain-scoped-self-review-v1',created_at:createdAt,timestamp_source:'unverified_browser_clock',result,
  result_sha256:await sha256(result),annotations:a,assessment:assessment(result,a),
  review_scope:'Browser-local self-assessment; no verified reviewer identity or independent review.',
  saved_to_server:false,independent_review:false,operational_approval:false,production_ready:false};
 return {...payload,review_sha256:await sha256(payload)};
}
export async function verifyReview(value){
 const keys=['format','created_at','timestamp_source','result','result_sha256','annotations','assessment','review_scope','saved_to_server','independent_review','operational_approval','production_ready','review_sha256'];
 if(!exact(value,keys)||value.format!=='ain-scoped-self-review-v1'||value.timestamp_source!=='unverified_browser_clock'||[value.saved_to_server,value.independent_review,value.operational_approval,value.production_ready].some(x=>x!==false)||!/^[a-f0-9]{64}$/.test(value.result_sha256)||!/^[a-f0-9]{64}$/.test(value.review_sha256))throw Error('Invalid self-review scope');
 const expected=await buildReview(value.result,value.annotations,value.created_at);
 if(canonical(expected)!==canonical(value))throw Error('Review digest, result or assessment differs');
 return {verified:true,assessment:expected.assessment,result_sha256:expected.result_sha256,review_sha256:expected.review_sha256,
  scope:'Unsigned consistency check only; hashes do not verify authorship, independence or semantic correctness.',production_ready:false};
}
