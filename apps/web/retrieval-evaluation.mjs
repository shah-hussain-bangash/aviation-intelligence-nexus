import {apiFetch} from './research-auth.mjs';
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sources=['DELAY_V2','DELAY_BASELINE','DATA_INGESTION','MODEL_DATASET','GATE_OPTIMIZATION','LOCAL_IDENTITY'].map(n=>'docs/'+n+'.md');
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const finite=v=>{if(typeof v!=='number'||!Number.isFinite(v)||v<0)throw new Error('Invalid evaluation value');return v;};
const near=(a,b)=>{if(Math.abs(finite(a)-finite(b))>1e-9+1e-9*Math.max(a,b))throw new Error('Inconsistent retrieval arithmetic');};
const filters=['issues','all','answerable','outside','unavailable'];
const methods=['hybrid','lexical'];

export function validateRetrieval(r){
 if(r?.format!=='ain-retrieval-diagnostics-v1'||r.integrity_verified!==true||r.report_sha256!=='eb8a40b32b0d30af8d1f2e7a8815fd220808f28bf53a019ef6d12258b6e0c57f'||r.suite_sha256!=='2c1ecd454f8011d18613a6d41690cb4ef9a3413eb2dfaa5cc2ad3a14c28b7eba'||r.generated_answers!==0||r.production_ready!==false||r.operational_approval!==false||r.semantic_answer_accuracy_measured!==false||r.ranking_or_threshold_changes!==false||typeof r.complete!=='boolean')throw new Error('Invalid retrieval scope');
 if(!hash(r.index_sha256)||!hash(r.embedding_digest)||!/^[a-f0-9]{40}$/.test(r.corpus_revision)||!Number.isFinite(Date.parse(r.checked_at))||r.passages!==31||JSON.stringify(r.sources.map(s=>s.path))!==JSON.stringify(sources)||r.sources.some(s=>!hash(s.sha256))||!Array.isArray(r.cases)||r.cases.length!==24||new Set(r.cases.map(c=>c.id)).size!==24)throw new Error('Invalid recorded corpus');
 finite(r.elapsed_ms);
 for(const value of [r.scope,r.metric_denominators,r.methods?.hybrid,r.methods?.lexical,r.embedding_model])if(typeof value!=='string'||!value)throw new Error('Missing retrieval context');
 for(const row of r.cases){
  if(typeof row.id!=='string'||!row.id||typeof row.question!=='string'||row.question.length>600||!Array.isArray(row.targets)||row.targets.length>3)throw new Error('Invalid case');
  finite(row.case_elapsed_ms);
  for(const t of row.targets)if(!sources.includes(t.source)||typeof t.quote!=='string'||t.quote.length<12)throw new Error('Invalid target label');
  for(const method of methods){
   const x=row[method];if(typeof x.available!=='boolean'||!Array.isArray(x.retrieved)||x.retrieved.length>3)throw new Error('Invalid availability');
   if(!x.available){if(x.abstained!==null||x.retrieved.length)throw new Error('Unavailable is not abstention');continue;}
   if(!Array.isArray(x.target_ranks)||x.target_ranks.length!==row.targets.length)throw new Error('Invalid ranks');
   for(const e of x.retrieved)if(!/^[a-f0-9]{20}$/.test(e.id)||!sources.includes(e.source)||!Number.isSafeInteger(e.start_line)||!Number.isSafeInteger(e.end_line)||e.start_line<1||e.start_line>e.end_line||e.end_line>100000)throw new Error('Invalid passage');
   x.target_ranks.forEach((rank,i)=>{if(rank!==null&&(!Number.isSafeInteger(rank)||rank<1||rank>x.retrieved.length||x.retrieved[rank-1].source!==row.targets[i].source))throw new Error('Invalid labeled rank');});
   const hits=x.target_ranks.filter(rank=>rank!==null).length;
   if(x.target_hits!==hits||!Number.isSafeInteger(x.target_hits)||x.all_targets_found!==(row.targets.length>0&&hits===row.targets.length)||x.abstained!==(x.retrieved.length===0))throw new Error('Contradictory case');
   near(x.reciprocal_rank_sum,x.target_ranks.reduce((sum,rank)=>sum+(rank===null?0:1/rank),0));
  }
 }
 if(r.complete!==r.cases.every(row=>row.hybrid.available))throw new Error('Contradictory completion');
 for(const method of methods){
  const positive=r.cases.filter(c=>c.targets.length&&c[method].available),negative=r.cases.filter(c=>!c.targets.length&&c[method].available),targets=positive.reduce((s,c)=>s+c.targets.length,0),hits=positive.reduce((s,c)=>s+c[method].target_hits,0),m=r.metrics[method];
  const expected={total_cases:24,unavailable_cases:r.cases.filter(c=>!c[method].available).length,evaluated_answerable_cases:positive.length,evaluated_gold_targets:targets,target_hits_at_3:hits,all_targets_found_cases:positive.filter(c=>c[method].all_targets_found).length,evaluated_out_of_corpus_cases:negative.length,out_of_corpus_abstentions:negative.filter(c=>c[method].abstained).length,out_of_corpus_false_retrievals:negative.filter(c=>!c[method].abstained).length};
  for(const [k,v] of Object.entries(expected))if(!Number.isSafeInteger(m[k])||m[k]!==v)throw new Error('Inconsistent metric count');
  if(targets){near(m.target_recall_at_3,hits/targets);near(m.mean_target_reciprocal_rank_at_3,positive.reduce((s,c)=>s+c[method].reciprocal_rank_sum,0)/targets);}
  else if(m.target_recall_at_3!==null||m.mean_target_reciprocal_rank_at_3!==null)throw new Error('Unavailable metric must be null');
 }
 return r;
}

export function retrievalCases(r,method='hybrid',filter='issues',query=''){
 validateRetrieval(r);if(!methods.includes(method)||!filters.includes(filter)||typeof query!=='string'||query.length>200)throw new Error('Unsupported comparison');
 const search=query.trim().toLowerCase();return r.cases.filter(c=>{
  const x=c[method],issue=!x.available||(c.targets.length?!x.all_targets_found:!x.abstained);
  return (filter==='all'||filter==='issues'&&issue||filter==='answerable'&&c.targets.length||filter==='outside'&&!c.targets.length||filter==='unavailable'&&!x.available)&&[c.id,c.question,...c.targets.map(t=>t.source)].join(' ').toLowerCase().includes(search);
 });
}

export function renderRetrieval(r,method='hybrid',filter='issues',query=''){
 const rows=retrievalCases(r,method,filter,query),label=method==='hybrid'?'Hybrid search':'Keyword search',fmt=n=>n===null?'Not available':finite(n).toFixed(4),m=r.metrics;
 const outcome=c=>!c[method].available?'Unavailable · not an abstention':c.targets.length?(c[method].all_targets_found?'Required passage found':'Required passage missed'):(c[method].abstained?'Correct abstention':'Out-of-corpus question returned evidence');
 const metricRow=(name,key,denominator)=>`<tr><th scope="row">${name}</th>${methods.map(k=>`<td>${denominator?m[k][key]+'/'+m[k][denominator]:fmt(m[k][key])}</td>`).join('')}</tr>`;
 const comparison=m.hybrid.mean_target_reciprocal_rank_at_3===null||m.lexical.mean_target_reciprocal_rank_at_3===null?'A ranking comparison is unavailable.':m.hybrid.mean_target_reciprocal_rank_at_3<m.lexical.mean_target_reciprocal_rank_at_3?'Keyword search ranked relevant passages higher overall.':m.hybrid.mean_target_reciprocal_rank_at_3>m.lexical.mean_target_reciprocal_rank_at_3?'Hybrid search ranked relevant passages higher overall.':'The mean reciprocal ranks are equal.';
 const bars=methods.map(k=>`<div class="retrieval-bar"><span>${k==='hybrid'?'Hybrid':'Keyword'}</span><div class="duration-track"><i class="${k==='hybrid'?'duration-model':'duration-baseline'}" style="width:${100*(m[k].mean_target_reciprocal_rank_at_3??0)}%"></i></div><strong>${fmt(m[k].mean_target_reciprocal_rank_at_3)}</strong></div>`).join('');
 return `<p class="research-caution"><strong>Recorded development diagnostics · not answer accuracy.</strong> These 24 questions were curated from six public project documents. They are not independent held-out airline questions or prompt-injection tests. No answers were generated and no search settings were changed.</p>
 <div class="diagnostic-metrics"><div><span>Answerable questions</span><strong>${r.cases.filter(c=>c.targets.length).length}</strong></div><div><span>Out-of-corpus questions</span><strong>${r.cases.filter(c=>!c.targets.length).length}</strong></div><div><span>Indexed passages</span><strong>${r.passages}</strong></div><div><span>Available hybrid cases</span><strong>${24-m.hybrid.unavailable_cases}/24</strong></div></div>
 <p>Recorded ${escape(r.checked_at)} · ${escape(r.embedding_model)} · ${r.complete?'Completed snapshot':'Incomplete snapshot; inspect unavailable cases'}. This is not current service health.</p>
 <div class="retrieval-grid"><article class="duration-plot"><h4>Relevant passage ranking</h4><p>Mean target reciprocal rank at three. Higher means the labeled passage appeared earlier; a miss contributes zero. It is not answer accuracy.</p>${bars}</article><article class="duration-plot"><h4>Where interpretation stops</h4><p>Hybrid found ${m.hybrid.target_hits_at_3}/${m.hybrid.evaluated_gold_targets} required passages; keyword search found ${m.lexical.target_hits_at_3}/${m.lexical.evaluated_gold_targets}. Hybrid search returned evidence for ${m.hybrid.out_of_corpus_false_retrievals} unsupported questions. ${comparison}</p><p>Abstention gates differ, so this is a diagnostic comparison. An earlier attempt timed out; unavailable queries are counted separately from correct abstentions.</p></article></div>
 <div class="research-table"><table><caption>Available-case metrics · recorded comparison</caption><thead><tr><th>Observation</th><th>Hybrid</th><th>Keyword</th></tr></thead><tbody>${metricRow('Required passages found at three','target_hits_at_3','evaluated_gold_targets')}${metricRow('Target recall at three','target_recall_at_3')}${metricRow('Mean target reciprocal rank','mean_target_reciprocal_rank_at_3')}${metricRow('Correct out-of-corpus abstentions','out_of_corpus_abstentions','evaluated_out_of_corpus_cases')}${metricRow('Out-of-corpus false retrievals','out_of_corpus_false_retrievals','evaluated_out_of_corpus_cases')}<tr><th>Unavailable cases</th><td>${m.hybrid.unavailable_cases}</td><td>${m.lexical.unavailable_cases}</td></tr></tbody></table></div>
 <h4>${escape(label)} · ${rows.length} of 24 questions shown</h4><p>Expand a question to inspect its label and recorded passage locations. A returned related passage does not establish that the question is answered.</p>
 <div class="retrieval-cases">${rows.map(c=>`<details><summary><span>${escape(c.question)}</span><strong>${escape(outcome(c))}</strong></summary><p>Case ${escape(c.id)} · Recorded question and labels</p>${c.targets.length?c.targets.map(t=>`<p><strong>Required source: ${escape(t.source)}</strong><br>Quote label: ${escape(t.quote)}</p>`).join(''):'<p>The fixed document collection does not contain the requested answer.</p>'}${c[method].available?`<h5>Returned passages</h5>${c[method].retrieved.length?`<ol>${c[method].retrieved.map(e=>`<li><a href="https://github.com/shah-hussain-bangash/aviation-intelligence-nexus/blob/${r.corpus_revision}/${e.source}#L${e.start_line}" target="_blank" rel="noopener noreferrer">${escape(e.source)} · lines ${e.start_line}–${e.end_line}</a></li>`).join('')}</ol>`:'<p>No passages were returned.</p>'}`:'<p>The retrieval service was unavailable. No abstention or relevance success is inferred.</p>'}</details>`).join('')||'<p>No questions match these filters.</p>'}</div>
 <details><summary>Evaluation identity and limitations</summary><p>${escape(r.scope)}</p><p>${escape(r.metric_denominators)}</p><p>Corpus revision: ${escape(r.corpus_revision)}. Recorded total runtime: ${r.elapsed_ms.toFixed(2)} ms, including service calls, baseline comparison and scoring; this is not a load-test latency result.</p><p>Report: ${r.report_sha256}<br>Suite: ${r.suite_sha256}<br>Index: ${r.index_sha256}</p><p>No operational approval, production qualification, security robustness or generated-answer entailment is established.</p></details>`;
}

export function retrievalExport(r,method='hybrid',filter='issues',query=''){
 const rows=retrievalCases(r,method,filter,query);
 const keys=['format','checked_at','scope','metric_denominators','suite_sha256','index_sha256','corpus_revision','embedding_model','embedding_digest','passages','methods','metrics','elapsed_ms','complete','generated_answers','ranking_or_threshold_changes','semantic_answer_accuracy_measured','operational_approval','production_ready','integrity_verified','report_sha256'];
 const evidence=Object.fromEntries(keys.map(k=>[k,r[k]]));
 evidence.methods=Object.fromEntries(methods.map(k=>[k,r.methods[k]]));
 evidence.metrics=Object.fromEntries(methods.map(k=>[k,Object.fromEntries(['total_cases','unavailable_cases','evaluated_answerable_cases','evaluated_gold_targets','target_hits_at_3','target_recall_at_3','mean_target_reciprocal_rank_at_3','all_targets_found_cases','evaluated_out_of_corpus_cases','out_of_corpus_abstentions','out_of_corpus_false_retrievals'].map(name=>[name,r.metrics[k][name]]))]));
 evidence.sources=r.sources.map(s=>({path:s.path,sha256:s.sha256}));
 evidence.cases=r.cases.map(c=>({id:c.id,question:c.question,targets:c.targets.map(t=>({source:t.source,quote:t.quote})),case_elapsed_ms:c.case_elapsed_ms,...Object.fromEntries(methods.map(k=>{const x=c[k];return [k,{available:x.available,abstained:x.abstained,...(x.available?{target_ranks:x.target_ranks,target_hits:x.target_hits,reciprocal_rank_sum:x.reciprocal_rank_sum,all_targets_found:x.all_targets_found}:{}),retrieved:x.retrieved.map(e=>({id:e.id,source:e.source,start_line:e.start_line,end_line:e.end_line}))}];}))}));
 return {format:'ain-retrieval-display-export-v1',evidence,selected_method:method,selected_filter:filter,search:query,displayed_case_ids:rows.map(c=>c.id),recorded_evaluation_only:true,production_ready:false};
}

export function mountRetrieval(parent){
 const section=document.createElement('section');section.id='retrieval-evaluation';section.className='research-card retrieval-evaluation';section.setAttribute('aria-labelledby','retrieval-heading');
 section.innerHTML='<div class="pattern-heading"><div><span class="research-badge">Generative AI · Recorded retrieval evaluation</span><h3 id="retrieval-heading">Does the evidence answer the question?</h3><p>Compare hybrid search with keyword search and inspect the misses before interpreting a RAG answer.</p></div></div><div class="pattern-controls"><label>Search method<select data-method disabled><option value="hybrid">Hybrid search</option><option value="lexical">Keyword search</option></select></label><label>Show questions<select data-filter disabled><option value="issues">Misses and false retrievals</option><option value="all">All questions</option><option value="answerable">Answerable questions</option><option value="outside">Out-of-corpus questions</option><option value="unavailable">Unavailable queries</option></select></label><label>Find a question<input type="search" maxlength="200" data-search disabled></label><div><button class="btn sm" type="button" data-refresh>Refresh retrieval evidence</button><button class="btn sm" type="button" data-export disabled>Export retrieval evaluation</button></div></div><p role="status" data-status></p><div class="retrieval-result"></div>';
 parent.append(section);const method=section.querySelector('[data-method]'),filter=section.querySelector('[data-filter]'),search=section.querySelector('[data-search]'),refresh=section.querySelector('[data-refresh]'),download=section.querySelector('[data-export]'),status=section.querySelector('[data-status]'),output=section.querySelector('.retrieval-result');let active=false,epoch=0,data=null,controller=null;
 function clear(){data=null;output.replaceChildren();for(const e of [method,filter,search,download])e.disabled=true;}
 function draw(){if(!data)return;try{output.innerHTML=renderRetrieval(data,method.value,filter.value,search.value);download.disabled=false;}catch{clear();status.textContent='Retrieval evidence could not be verified. Previous results have been cleared.';}}
 async function load(){if(!active)return;const current=++epoch;controller?.abort();controller=new AbortController();const pending=controller,timer=setTimeout(()=>pending.abort(),10000);clear();refresh.disabled=true;status.textContent='Verifying the recorded retrieval evaluation…';try{const response=await apiFetch('/api/v1/research/retrieval-diagnostics',{signal:pending.signal});if(!response.ok)throw new Error();const r=validateRetrieval(await response.json());if(current!==epoch)return;data=r;for(const e of [method,filter,search])e.disabled=false;status.textContent='Verified recorded evaluation · research only, not current service health.';draw();}catch{if(current===epoch){clear();status.textContent='Retrieval evidence could not be verified. Previous results have been cleared.';}}finally{clearTimeout(timer);if(current===epoch)refresh.disabled=!active;}}
 method.addEventListener('change',draw);filter.addEventListener('change',draw);search.addEventListener('input',draw);refresh.addEventListener('click',load);
 download.addEventListener('click',()=>{if(!data||!active)return;const url=URL.createObjectURL(new Blob([JSON.stringify(retrievalExport(data,method.value,filter.value,search.value),null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_Retrieval_Evaluation.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 return {setSession(user){epoch++;controller?.abort();active=!!user;clear();method.value='hybrid';filter.value='issues';search.value='';status.textContent='';refresh.disabled=!active;if(active)load();}};
}
