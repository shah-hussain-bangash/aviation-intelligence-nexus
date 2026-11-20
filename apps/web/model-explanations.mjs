import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={carrier:'Reporting carrier',origin:'Origin airport',destination:'Destination airport',departure_time:'Scheduled departure time',weekday:'Day of week'};
const measures={log_loss_increase:'Log loss increase',roc_auc_decrease:'ROC-AUC decrease',brier_increase:'Brier score increase'};
const signed=value=>(value>=0?'+':'')+value.toFixed(5);

export function validateExplanations(data){
  if(data?.format!=='ain-permutation-v1'||data.integrity_verified!==true||data.research_only!==true||data.production_ready!==false||data.source_hashes_unchanged!==true||data.sample_records!==10000||data.validation_population!==577730||data.protocol?.period!=='2025-04'||data.protocol?.split!=='validation'||data.protocol?.repeats!==3||!/^[a-f0-9]{64}$/.test(data.report_sha256))throw new Error('Unverified explanation');
  if(data.groups?.length!==5||new Set(data.groups.map(r=>r.group)).size!==5||data.groups.some(r=>!Object.hasOwn(labels,r.group)))throw new Error('Invalid groups');
  for(const k of ['log_loss','roc_auc','brier_score'])if(!Number.isFinite(data.baseline[k])||data.baseline[k]<0)throw new Error('Invalid baseline');
  for(const row of data.groups){
    if(row.repeats?.length!==3)throw new Error('Invalid repeats');
    for(const key of Object.keys(measures)){
      const values=row.repeats.map(r=>r[key]);if(values.some(v=>!Number.isFinite(v)))throw new Error('Invalid measurement');
      const mean=values.reduce((a,b)=>a+b,0)/3,std=Math.sqrt(values.reduce((a,b)=>a+(b-mean)**2,0)/2);
      if(!Number.isFinite(row.mean[key])||!Number.isFinite(row.repeat_std[key])||Math.abs(row.mean[key]-mean)>1e-10||Math.abs(row.repeat_std[key]-std)>1e-10)throw new Error('Inconsistent summary');
    }
  }
  return data;
}

export function renderExplanations(data,measure='log_loss_increase'){
  validateExplanations(data);if(!Object.hasOwn(measures,measure))throw new Error('Unknown measure');
  const sorted=[...data.groups].sort((a,b)=>b.mean[measure]-a.mean[measure]),scale=Math.max(...sorted.map(r=>Math.abs(r.mean[measure])),1e-9);
  return `<div class="explanation-scope"><strong>April 2025 · Validation subset · Frozen delay-v2</strong><p>10,000 sampled flights from 577,730 eligible observations · 3 shuffles per input group · No May outcomes analyzed.</p></div>
    <div class="explanation-intro"><div><h4>What changes when an input is shuffled?</h4><p>Each group is shuffled while the model and other inputs stay fixed. Larger positive changes mean greater performance reliance in this sample. Negative changes mean shuffling improved the measured score.</p></div><div class="explanation-baseline"><span>Unshuffled sample baseline</span><p>Log loss <strong>${data.baseline.log_loss.toFixed(5)}</strong><br>ROC-AUC <strong>${data.baseline.roc_auc.toFixed(5)}</strong><br>Brier <strong>${data.baseline.brier_score.toFixed(5)}</strong></p></div></div>
    <h4>${measures[measure]} after shuffling · Mean of three repeats</h4><p class="explanation-axis-note">Negative ← zero → positive · Bars share a symmetric scale within the selected measure.</p>
    <div class="explanation-bars">${sorted.map(row=>{const value=row.mean[measure],width=(Math.abs(value)/scale*100).toFixed(2);return `<div class="explanation-bar-row"><div class="explanation-label"><strong>${labels[row.group]}</strong><span>${signed(value)}</span></div><div class="explanation-track" aria-hidden="true"><div class="explanation-negative">${value<0?`<span style="width:${width}%"></span>`:''}</div><div class="explanation-positive">${value>=0?`<span style="width:${width}%"></span>`:''}</div></div><p>Repeat SD ${row.repeat_std[measure].toFixed(5)} · shuffle variation, not a confidence interval</p></div>`;}).join('')}</div>
    <details class="explanation-repeats"><summary>Inspect all three shuffle measurements</summary><div class="research-table"><table><caption>${measures[measure]} · Same sample and frozen model for every shuffle</caption><thead><tr><th>Input group</th><th>Repeat 1</th><th>Repeat 2</th><th>Repeat 3</th><th>Mean</th><th>Sample SD</th></tr></thead><tbody>${sorted.map(r=>`<tr><th>${labels[r.group]}</th>${r.repeats.map(v=>`<td>${signed(v[measure])}</td>`).join('')}<td>${signed(r.mean[measure])}</td><td>${r.repeat_std[measure].toFixed(5)}</td></tr>`).join('')}</tbody></table></div></details>
    <details><summary>Method, provenance and limits</summary><p>Uniform sample without replacement, seed ${Number(data.protocol.seed)}, in original row order. The same three row permutations are used across groups. Departure hour and minute move together; the frozen pipeline recomputes their cyclic features. No refitting or feature selection occurs.</p><ul>${data.limitations.map(v=>`<li>${escape(v)}</li>`).join('')}</ul><p>Report SHA-256: <span class="pattern-fingerprint">${escape(data.report_sha256)}</span>. Recorded evidence only; file integrity does not establish independent acceptance or current model health.</p></details><p class="research-caution">Model reliance is not causality or an explanation for an individual flight. Historical US research · production qualification incomplete.</p>`;
}

export function mountExplanations(parent){
  const section=document.createElement('section');section.className='research-card model-explanations';section.id='model-explanations';section.setAttribute('aria-labelledby','explanations-heading');
  section.innerHTML='<div class="pattern-heading"><div><span class="research-badge">Explainable ML · Recorded experiment</span><h3 id="explanations-heading">Model input reliance</h3><p>Inspect how shuffling an input changes the frozen model’s performance.</p></div><div class="pattern-controls"><label>Performance measure<select><option value="log_loss_increase">Log loss increase · Primary</option><option value="roc_auc_decrease">ROC-AUC decrease</option><option value="brier_increase">Brier score increase</option></select></label><div><button type="button" class="btn sm" data-refresh>Refresh evidence</button><button type="button" class="btn sm" data-export disabled>Export experiment JSON</button></div></div></div><div class="explanation-result" aria-live="polite"></div>';
  parent.append(section);const select=section.querySelector('select'),refresh=section.querySelector('[data-refresh]'),download=section.querySelector('[data-export]'),output=section.querySelector('.explanation-result');let active=false,generation=0,data=null;
  function clear(){data=null;download.disabled=true;select.disabled=true;output.replaceChildren();}
  async function load(){if(!active)return;const current=++generation;clear();refresh.disabled=true;output.textContent='Verifying the recorded input-reliance experiment…';try{const response=await apiFetch('/api/v1/research/model-explanations',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const payload=validateExplanations(await response.json());if(current!==generation)return;data=payload;output.innerHTML=renderExplanations(data,select.value);select.disabled=false;download.disabled=false;}catch{if(current===generation){clear();output.textContent='Input-reliance evidence could not be verified. Previous results have been cleared.';}}finally{if(current===generation)refresh.disabled=!active;}}
  select.addEventListener('change',()=>{if(data)output.innerHTML=renderExplanations(data,select.value);});refresh.addEventListener('click',load);
  download.addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify({...data,displayed_measure:select.value},null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_Model_Input_Reliance.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(user){generation++;active=!!user;clear();select.value='log_loss_increase';refresh.disabled=!active;if(active)load();}};
}
