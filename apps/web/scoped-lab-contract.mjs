const sources={'delay-v1':'docs/DELAY_BASELINE.md','delay-v2':'docs/DELAY_V2.md'};
const sorted=a=>Array.isArray(a)&&a.length<=75&&a.every(x=>typeof x==='string'&&/^[a-z]{8,600}$/.test(x))&&JSON.stringify(a)===JSON.stringify([...new Set(a)].sort());

export function validateScopedResult(r,q){
 if(!r||r.format!=='ain-scoped-lab-v1'||r.question!==q.question.trim()||r.experiment!==q.experiment||r.source!==sources[q.experiment]||[r.saved_to_history,r.human_review_complete,r.operational_approval,r.production_ready].some(x=>x!==false)||!Array.isArray(r.claims)||r.claims.length>3)throw Error('Invalid scoped identity');
 const g=r.scope_guard,c=r.coverage,status=r.generation_status;
 if(!g||!Array.isArray(g.mentioned_experiments)||g.mentioned_experiments.length>75||g.mentioned_experiments.some(x=>!/^delay-v\d{1,3}$/.test(x))||!['no_explicit_conflict','conflicting_explicit_version','unsupported_explicit_version'].includes(g.reason)||!c||![c.required_terms,c.missing_terms,c.matched_terms].every(sorted))throw Error('Invalid scope/coverage');
 if(r.mode==='clarification_required'){
  if(g.decision!=='clarification_required'||g.reason==='no_explicit_conflict'||c.decision!=='not_checked_scope_conflict'||c.required_terms.length||c.missing_terms.length||c.matched_terms.length||r.claims.length||r.corpus_revision!==null||status!=='not_requested_scope_conflict')throw Error('Invalid clarification');
 }else{
  if(g.decision!=='allow'||g.reason!=='no_explicit_conflict'||!/^[a-f0-9]{40}$/.test(r.corpus_revision)||new Set([...c.missing_terms,...c.matched_terms]).size!==c.required_terms.length||JSON.stringify([...c.missing_terms,...c.matched_terms].sort())!==JSON.stringify(c.required_terms)||c.decision!==(c.missing_terms.length?'decline':'allow'))throw Error('Invalid coverage arithmetic');
  if(c.decision==='decline'){if(r.mode!=='source_coverage_declined'||status!=='not_requested_source_coverage'||r.claims.length)throw Error('Invalid source refusal');}
  else if(r.mode==='excerpts'){if(status!=='completed'||!r.claims.length)throw Error('Invalid excerpts');}
  else if(r.mode==='abstained'){if(!['completed','skipped_no_evidence'].includes(status)||r.claims.length)throw Error('Invalid abstention');}
  else if(r.mode==='evidence_only'){if(status!=='unavailable_or_rejected'||r.claims.length)throw Error('Unavailable is not abstention');}
  else throw Error('Unknown result');
 }
 for(const x of r.claims)if(x.text!==x.quote||typeof x.quote!=='string'||x.quote.length<20||x.quote.length>400||x.source!==r.source||!/^[a-f0-9]{20}$/.test(x.citation)||!Number.isSafeInteger(x.start_line)||!Number.isSafeInteger(x.end_line)||x.start_line<1||x.start_line>x.end_line||x.end_line>100000)throw Error('Invalid source excerpt');
 if(!Number.isSafeInteger(r.context_added_count)||r.context_added_count<0||r.context_added_count>r.claims.length)throw Error('Invalid context count');
 return r;
}

export function scopedExport(r,q){
 validateScopedResult(r,q);
 return {format:'ain-scoped-lab-export-v1',question:r.question,experiment:r.experiment,source:r.source,mode:r.mode,generation_status:r.generation_status,
  scope_guard:{decision:r.scope_guard.decision,reason:r.scope_guard.reason,mentioned_experiments:[...r.scope_guard.mentioned_experiments]},
  coverage:{decision:r.coverage.decision,required_terms:[...r.coverage.required_terms],missing_terms:[...r.coverage.missing_terms],matched_terms:[...r.coverage.matched_terms]},
  corpus_revision:r.corpus_revision,claims:r.claims.map(c=>Object.fromEntries(['text','quote','citation','source','start_line','end_line'].map(k=>[k,c[k]]))),
  context_added_count:r.context_added_count,saved_to_history:false,human_review_complete:false,operational_approval:false,production_ready:false};
}

