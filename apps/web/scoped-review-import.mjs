import {verifyReview} from './scoped-review-contract.mjs';
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const MAX_REVIEW_BYTES=256*1024;
const labels={draft:'Draft self-assessment',self_reviewed:'Positive self-assessment',needs_revision:'Self-assessment: needs revision',self_reviewed_refusal:'Refusal marked appropriate',refusal_needs_revision:'Refusal marked inappropriate',not_evaluable:'Unavailable outcome: not evaluable'};
const judgment=value=>({yes:'Yes',no:'No',uncertain:'Uncertain',not_applicable:'Not applicable',not_evaluable:'Not evaluable'}[value]);

export async function readReviewFile(file){
 if(!file||!Number.isSafeInteger(file.size)||file.size<1||file.size>MAX_REVIEW_BYTES||typeof file.arrayBuffer!=='function')throw Error('Invalid review file size');
 const bytes=await file.arrayBuffer();
 if(!(bytes instanceof ArrayBuffer)||bytes.byteLength!==file.size||bytes.byteLength>MAX_REVIEW_BYTES)throw Error('Review file changed or exceeds its bound');
 const bundle=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
 const verification=await verifyReview(bundle);
 return {bundle,verification};
}

export async function renderImportedReview(bundle){
 const checked=await verifyReview(bundle),r=bundle.result,a=bundle.annotations;
 const source=r.corpus_revision?`<a href="https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/${r.corpus_revision}/${r.source}" target="_blank" rel="noopener noreferrer">${escape(r.source)} · recorded revision</a>`:escape(r.source)+' · no corpus loaded for this clarification';
 return `<article class="imported-review"><span class="research-badge">Imported file · unsigned · local only</span><h4>${labels[checked.assessment]}</h4><p><strong>Content consistency checks passed.</strong> This does not verify the author, an independent reviewer, source truth or semantic correctness. Digests can be recomputed by anyone.</p><p class="research-caution">This is an imported artifact, not a new model response. It does not change the current question, live result or its review.</p>
 <dl><div><dt>Question in file</dt><dd>${escape(r.question)}</dd></div><div><dt>Experiment / recorded outcome</dt><dd>${escape(r.experiment)} / ${escape(r.mode)}</dd></div><div><dt>Selected source</dt><dd>${source}</dd></div><div><dt>Timestamp in file</dt><dd>${escape(bundle.created_at)} · unverified client clock</dd></div><div><dt>Claimed source check</dt><dd>${a.source_checked?'Yes':'No'}</dd></div><div><dt>Analyst marked question answered</dt><dd>${judgment(a.question_answered)}</dd></div><div><dt>Analyst marked refusal appropriate</dt><dd>${judgment(a.decision_appropriate)}</dd></div></dl>
 ${r.claims.map((c,i)=>`<section class="imported-review-claim"><h5>Excerpt ${i+1}</h5><blockquote>${escape(c.quote)}</blockquote><p>Analyst marked support: <strong>${judgment(a.claims[i].supported)}</strong> · relevance: <strong>${judgment(a.claims[i].relevant)}</strong></p><p>${escape(c.source)} · lines ${c.start_line}–${c.end_line}</p></section>`).join('')}
 <h5>Notes in file</h5><pre class="imported-review-notes">${escape(a.notes||'No notes recorded.')}</pre><details><summary>Artifact digests</summary><p>Result SHA-256: <code>${checked.result_sha256}</code></p><p>Review SHA-256: <code>${checked.review_sha256}</code></p></details><p>Original service semantic review remains pending. Independent review and operational approval remain false.</p></article>`;
}

export function mountReviewInspector(parent){
 const section=document.createElement('section');section.className='scoped-review-inspector';section.id='scoped-review-inspector';section.setAttribute('aria-labelledby','review-inspector-heading');
 section.innerHTML='<span class="research-badge">Local artifact inspector</span><h4 id="review-inspector-heading">Reopen an exported self-review</h4><p>Choose one JSON file to verify and inspect in this browser. The file is not uploaded, saved to history or used to run a question. Unsigned hashes check consistency, not reviewer identity or correctness.</p><div class="review-import-controls"><label>Choose exported self-review JSON<input type="file" accept=".json,application/json" data-review-file disabled></label><button class="btn sm" type="button" data-clear-import>Clear imported file</button></div><p role="status" aria-live="polite" data-import-status></p><div data-import-result></div>';
 parent.append(section);const input=section.querySelector('[data-review-file]'),status=section.querySelector('[data-import-status]'),output=section.querySelector('[data-import-result]');let epoch=0,allowed=false;
 function clear(){epoch++;input.value='';output.replaceChildren();status.textContent=allowed?'Imported file and displayed notes cleared.':'Researcher or administrator access is required to use this inspector.';}
 input.addEventListener('change',async()=>{
  const current=++epoch;output.replaceChildren();if(!allowed)return;
  const files=input.files;
  if(!files||files.length!==1){input.value='';status.textContent='Choose one exported self-review JSON file.';return;}
  const file=files[0];status.textContent='Checking the selected review file locally…';
  try{
   const {bundle}=await readReviewFile(file);if(current!==epoch||!allowed)return;
   const html=await renderImportedReview(bundle);if(current!==epoch||!allowed)return;
   output.innerHTML=html;status.textContent='Local consistency checks passed for '+file.name.slice(0,200)+'. No file was uploaded.';
  }catch{
   if(current!==epoch)return;input.value='';output.replaceChildren();status.textContent='File could not be verified. Previous imported content has been cleared. Use an unchanged UTF-8 self-review JSON file no larger than 256 KiB.';
  }
 });
 section.querySelector('[data-clear-import]').addEventListener('click',clear);
 return {clear,setSession(user){allowed=['admin','researcher'].includes(user?.role);clear();input.disabled=!allowed;if(allowed)status.textContent='Choose a file for local consistency checking. No model query will run.';}};
}
