import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function renderKnowledge(result){
  if(result.research_only!==true||result.operational_approval!==false||!['generated','evidence_only','abstained'].includes(result.mode))throw new Error('Unexpected knowledge result');
  const known=new Map(result.evidence.map(e=>[e.id,e]));
  for(const claim of result.claims){if(!known.has(claim.citation)||!known.get(claim.citation).text.includes(claim.quote))throw new Error('Invalid citation');}
  return `<div class="research-badge">${result.mode==='generated'?'Local AI answer · review against evidence':result.mode==='abstained'?'Insufficient evidence · no answer':'Retrieved evidence · no generated answer'}</div>
    <p><strong>Question:</strong> ${escape(result.question)}</p>
    ${result.generation.status==='unavailable_or_rejected'?'<p class="research-caution">Generation was unavailable or its output failed validation. Evidence below is retrieval only.</p>':''}
    ${result.claims.map(claim=>`<article class="knowledge-claim"><p>${escape(claim.text)}</p><blockquote>${escape(claim.quote)}</blockquote><small>Source ${escape(claim.citation)} · exact quotation checked</small></article>`).join('')}
    ${!result.evidence.length?'<p>The indexed documents did not provide sufficient matching evidence. Try a question about this project’s delay models, dataset or gate-allocation lab.</p>':''}
    ${result.evidence.map(e=>`<details class="knowledge-source"><summary>${escape(e.source)} · lines ${e.start_line}–${e.end_line} · ${escape(e.heading)}</summary><p>Passage ID ${escape(e.id)} · source SHA-256 ${escape(e.source_sha256)}</p><pre>${escape(e.text)}</pre>${/^https:\/\/github\.com\/zenithdevelopers7-source\/aviation-intelligence-nexus\/blob\/[a-f0-9]{40}\/docs\/[A-Z0-9_]+\.md#L\d+$/.test(e.source_url)?`<a href="${escape(e.source_url)}" target="_blank" rel="noopener noreferrer">Open versioned source on GitHub ↗</a>`:''}</details>`).join('')}
    <p class="research-caution">Project research only. Citations and quotations are checked mechanically; generated interpretations still require human review. No flight, safety or live airline decision is made.</p>
    <p class="research-meta">Saved ${escape(result.saved_at)} · ${escape(result.actor)} · Run ${escape(result.run_id)} · ${escape(result.generation.model||'No generation model used')}</p>`;
}

export function mountKnowledge(parent){
  const section=document.createElement('section');section.className='research-card knowledge-lab';section.setAttribute('aria-labelledby','knowledgeHeading');
  section.innerHTML=`<div class="knowledge-heading"><span class="research-badge">Evidence studio · local AI</span><h3 id="knowledgeHeading">Ask your aviation research</h3><p>Search six public project documents with local embeddings and keyword retrieval. Optionally ask Ollama to summarize the retrieved evidence with source citations.</p></div>
    <p class="knowledge-status" role="status">Checking local knowledge services…</p>
    <form class="knowledge-form"><label for="knowledgeQuestion">Your research question</label><textarea id="knowledgeQuestion" name="question" minlength="8" maxlength="600" rows="3" required placeholder="What were the May results and limitations of the second delay model?"></textarea><label class="knowledge-generation"><input type="checkbox" name="generate"> Generate a cited answer using local Qwen3</label><button type="submit" class="btn" disabled>Search evidence</button></form>
    <p class="knowledge-access"></p><div class="knowledge-result" aria-live="polite"></div><div class="research-toolbar"><button class="btn sm" type="button" data-knowledge-refresh>Refresh knowledge services</button><button class="btn sm" type="button" data-knowledge-export disabled>Export evidence result (JSON)</button></div><div class="knowledge-history" aria-live="polite"></div>`;
  parent.append(section);
  const form=section.querySelector('form'),submit=form.querySelector('button'),status=section.querySelector('.knowledge-status'),output=section.querySelector('.knowledge-result'),history=section.querySelector('.knowledge-history'),exportButton=section.querySelector('[data-knowledge-export]');
  let user=null,ready=false,generationReady=false,epoch=0,active=null,shown=null,runs=[];
  const allowed=()=>['admin','researcher'].includes(user?.role);
  function clear(){epoch++;active?.abort();shown=null;output.replaceChildren();exportButton.disabled=true;submit.disabled=!ready||!allowed();}
  function show(result){output.innerHTML=renderKnowledge(result);shown=result;exportButton.disabled=false;}
  async function refresh(){
    const current=epoch;
    try{const [stateResponse,historyResponse]=await Promise.all([apiFetch('/api/v1/research/knowledge-status',{signal:AbortSignal.timeout(10000)}),apiFetch('/api/v1/research/knowledge-history',{signal:AbortSignal.timeout(10000)})]);if(!stateResponse.ok||!historyResponse.ok)throw new Error();const state=await stateResponse.json(),saved=await historyResponse.json();if(current!==epoch)return;ready=state.index_ready&&state.embedding_ready;generationReady=ready&&state.generation_available;
      status.textContent=ready?`${state.sources} documents · ${state.chunks} passages · local ${state.embedding_model} embeddings · ${generationReady?'Qwen3 available':'generation unavailable'}`:'Knowledge unavailable. Restore Ollama and rebuild the document index.';
      form.elements.generate.disabled=!generationReady;if(!generationReady)form.elements.generate.checked=false;submit.disabled=!ready||!allowed();runs=saved.runs;
      history.innerHTML=runs.length?`<h4>Saved evidence queries</h4><div class="gate-history-buttons">${runs.map((r,i)=>`<button type="button" class="btn sm" data-knowledge-run="${i}">${escape(r.question.slice(0,80))} · ${escape(r.mode)}</button>`).join('')}</div>`:'<p>No saved evidence queries yet.</p>';
    }catch{if(current===epoch){ready=false;submit.disabled=true;status.textContent='Knowledge services unavailable. Check the backend and your session.';history.replaceChildren();runs=[];}}
  }
  form.addEventListener('input',()=>{clear();submit.textContent=form.elements.generate.checked?'Generate cited answer':'Search evidence';});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!allowed()||!ready||submit.disabled)return;clear();const current=epoch;active=new AbortController();const controller=active,timer=setTimeout(()=>controller.abort(),105000);submit.disabled=true;output.textContent='Retrieving evidence'+(form.elements.generate.checked?' and generating a local answer…':'…');
    try{const response=await apiFetch('/api/v1/research/knowledge-query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:form.elements.question.value,generate:form.elements.generate.checked}),signal:controller.signal});const result=await response.json();if(current!==epoch)return;if(!response.ok)throw new Error();show(result);refresh();}
    catch{if(current===epoch)output.textContent='No saved result could be confirmed. Check the local model service and backend. A timed-out request may still finish; refresh saved queries before retrying.';}
    finally{clearTimeout(timer);if(current===epoch)submit.disabled=!ready||!allowed();}
  });
  section.querySelector('[data-knowledge-refresh]').addEventListener('click',refresh);
  section.addEventListener('click',event=>{const key=event.target.closest('[data-knowledge-run]')?.dataset.knowledgeRun;if(key!==undefined&&runs[Number(key)]){clear();show(runs[Number(key)]);}});
  exportButton.addEventListener('click',()=>{if(!shown)return;const url=URL.createObjectURL(new Blob([JSON.stringify(shown,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='AIN_aviation_evidence.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(value){user=value;ready=false;generationReady=false;clear();runs=[];history.replaceChildren();section.querySelector('.knowledge-access').textContent=allowed()?'Search and generation results are saved under your account. Only public project documents are indexed.':'Viewer access: review your saved results; new queries require researcher or admin access.';if(user)refresh();}};
}
