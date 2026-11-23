import {apiFetch} from './research-auth.mjs';
const sources={'delay-v1':'docs/DELAY_BASELINE.md','delay-v2':'docs/DELAY_V2.md'};
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roles=['admin','researcher'];
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

export function renderScopedResult(r,q){
 validateScopedResult(r,q);
 const outcomes={excerpts:['Excerpts for human review','These are exact source excerpts. Check relevance and completeness before using them.'],source_coverage_declined:['Source vocabulary mismatch','The source lacks required long content terms. A valid paraphrase can also trigger this refusal. Try wording used by the source, or obtain an authorized source.'],clarification_required:['Clarify the experiment','The question names another or unsupported experiment. Select one version and ask about that version only.'],abstained:['No answer returned','The selected source did not produce an answer. This is not proof the question is unanswerable.'],evidence_only:['Generation unavailable or rejected','No validated answer was returned. This is not a successful abstention. Check the local model service before retrying.']};
 const [title,description]=outcomes[r.mode];
 return `<article class="scoped-outcome"><span class="research-badge">${escape(r.experiment)} · unsaved research result</span><h4>${title}</h4><p>${description}</p><p><strong>Question</strong> ${escape(r.question)}</p>${r.coverage.missing_terms.length?`<p><strong>Missing terms</strong> <span class="scoped-terms">${r.coverage.missing_terms.map(x=>`<span>${escape(x)}</span>`).join('')}</span></p>`:''}
 ${r.claims.map(c=>`<blockquote><p>${escape(c.quote)}</p><footer><a href="https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/${r.corpus_revision}/${c.source}#L${c.start_line}-L${c.end_line}" target="_blank" rel="noopener noreferrer">${escape(c.source)} · lines ${c.start_line}–${c.end_line}</a></footer></blockquote>`).join('')}
 <details><summary>Source-check details</summary><p>Required terms: ${escape(r.coverage.required_terms.join(', ')||'None checked')}. Matched terms: ${escape(r.coverage.matched_terms.join(', ')||'None')}.</p><p>Context added to ${r.context_added_count} excerpt(s). No result saved to research history.</p></details><p class="research-caution">Human semantic review pending · no operational approval · production qualification incomplete.</p></article>`;
}

export function mountScopedLab(parent){
 const section=document.createElement('section');section.id='scoped-answer-lab';section.className='research-card scoped-answer-lab';section.setAttribute('aria-labelledby','scoped-lab-heading');
 section.innerHTML=`<div class="scoped-heading"><div><span class="research-badge">Opt-in research lab</span><h3 id="scoped-lab-heading">Ask one experiment at a time</h3><p>Choose a model experiment, check source coverage, then inspect exact cited excerpts.</p></div><span class="scoped-private">Not saved to history</span></div><p class="research-caution">This experimental workflow can refuse valid paraphrases and miss unsupported topics. Exact quotations do not establish that a question is answered. Existing Q&A remains available below.</p>
 <div class="scoped-examples" aria-label="Example questions"><button type="button" class="btn sm" data-example="counts">V2 split counts</button><button type="button" class="btn sm" data-example="reason">V1 rejection reason</button><button type="button" class="btn sm" data-example="missing">Unsupported coefficient question</button></div>
 <form><label>Experiment<select name="experiment"><option value="delay-v2">Delay v2 · April validation / May test</option><option value="delay-v1">Delay v1 · February selection / March test</option></select></label><label>Question<textarea name="question" minlength="8" maxlength="600" rows="3" required placeholder="Ask about this experiment's documented research evidence"></textarea></label><label class="scoped-ack"><input type="checkbox" name="acknowledged">I understand that excerpts and refusals require review and do not authorize airline decisions.</label><div class="scoped-actions"><button class="btn" type="submit" disabled>Check source and ask</button><button class="btn sm" type="button" data-clear>Clear query</button><button class="btn sm" type="button" data-export disabled>Export result (JSON)</button></div></form><p role="status" aria-live="polite" data-status></p><div data-result></div>`;
 parent.append(section);
 const form=section.querySelector('form'),experiment=form.elements.experiment,question=form.elements.question,ack=form.elements.acknowledged,submit=form.querySelector('[type=submit]'),download=section.querySelector('[data-export]'),status=section.querySelector('[data-status]'),output=section.querySelector('[data-result]');let allowed=false,epoch=0,controller=null,data=null,submitted=null,busy=false;
 function clear(){epoch++;controller?.abort();controller=null;data=null;submitted=null;busy=false;output.replaceChildren();download.disabled=true;}
 function sync(){submit.disabled=!allowed||busy||!ack.checked||question.value.trim().length<8||question.value.trim().length>600;}
 function changed(resetAck=true){clear();if(resetAck)ack.checked=false;status.textContent=allowed?'Inputs changed. Review the research acknowledgment before submitting.':'Researcher or administrator access is required to run this lab.';sync();}
 experiment.addEventListener('change',()=>changed());question.addEventListener('input',()=>changed());ack.addEventListener('change',()=>changed(false));
 section.querySelector('[data-clear]').addEventListener('click',()=>{clear();question.value='';ack.checked=false;status.textContent='Query and result cleared.';sync();});
 const examples={counts:['delay-v2','How many eligible training validation and testing flights were used in the second delay experiment?'],reason:['delay-v1','Why was the first logistic model rejected for actionable serving?'],missing:['delay-v1','Why did the optimizer choose each individual logistic coefficient for the first model?']};
 for(const button of section.querySelectorAll('[data-example]'))button.addEventListener('click',()=>{[experiment.value,question.value]=examples[button.dataset.example];changed();question.focus();});
 form.addEventListener('submit',async event=>{event.preventDefault();if(submit.disabled)return;clear();const current=epoch,q={experiment:experiment.value,question:question.value.trim(),acknowledged:true};controller=new AbortController();const pending=controller,timer=setTimeout(()=>pending.abort(),105000);busy=true;sync();status.textContent='Checking the selected source and running the bounded local candidate…';try{
  const response=await apiFetch('/api/v1/research/scoped-query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q),signal:pending.signal});if(!response.ok)throw Error('Unavailable');const r=validateScopedResult(await response.json(),q);if(current!==epoch)return;data=r;submitted=q;output.innerHTML=renderScopedResult(r,q);download.disabled=false;status.textContent=r.mode==='evidence_only'?'No validated answer. The recorded outcome can be exported.':'Result returned · research only · semantic review pending.';
 }catch{if(current===epoch){data=null;submitted=null;output.replaceChildren();download.disabled=true;status.textContent='No verified result returned. Previous results have been cleared. Check access, the trusted index and the local model service.';}}finally{clearTimeout(timer);if(current===epoch){busy=false;controller=null;sync();}}});
 download.addEventListener('click',()=>{if(!allowed||!data||!submitted)return;const blob=new Blob([JSON.stringify(scopedExport(data,submitted),null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='AIN_Scoped_Research_Result.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 return {setSession(user){clear();allowed=roles.includes(user?.role);question.value='';experiment.value='delay-v2';ack.checked=false;for(const e of [question,experiment,ack,...section.querySelectorAll('[data-example]')])e.disabled=!allowed;status.textContent=allowed?'Choose an experiment and question. Nothing runs until you acknowledge and submit.':'Researcher or administrator access is required to run this lab.';sync();}};
}
