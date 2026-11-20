import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const integer=value=>{if(!Number.isSafeInteger(value)||value<0)throw new Error('Invalid route count');return value;};
const number=(value,min,max)=>{if(!Number.isFinite(value)||value<min||value>max)throw new Error('Invalid metric');return value;};
const count=value=>integer(value).toLocaleString('en-US');
const percent=value=>(number(value,0,1)*100).toFixed(1)+'%';

export function validatePatterns(data){
  if(data?.format!=='ain-route-patterns-v1'||data.integrity_verified!==true||data.research_only!==true||data.production_ready!==false||data.selected_k!==2||!Number.isFinite(Date.parse(data.recorded_at))||!/^[a-f0-9]{64}$/.test(data.report_sha256))throw new Error('Unverified experiment');
  integer(data.overlapping_routes);integer(data.changed_routes);
  if(!data.overlapping_routes||data.changed_routes>data.overlapping_routes)throw new Error('Invalid shared routes');
  number(data.training_silhouette,-1,1);number(data.minimum_training_seed_ari,-1,1);
  for(const period of ['train','evaluation']){
    const coverage=data.coverage[period],groups=data.profiles[period];
    for(const key of ['routes_supported','routes_observed','flights_observed','flights_on_supported_routes'])integer(coverage[key]);
    if(coverage.routes_supported>coverage.routes_observed||coverage.flights_on_supported_routes>coverage.flights_observed||groups.length!==2)throw new Error('Invalid coverage');
    if(groups.reduce((total,row)=>total+integer(row.routes),0)!==coverage.routes_supported||groups.reduce((total,row)=>total+integer(row.flights),0)!==coverage.flights_on_supported_routes)throw new Error('Inconsistent group totals');
    groups.forEach((row,index)=>{if(row.cluster!==index)throw new Error('Invalid group identity');const f=row.unweighted_mean_route_features;for(const key of ['delay_15_rate','delay_60_rate','cancellation_rate'])number(f[key],0,1);number(f.mean_positive_delay_capped_180,0,180);});
  }
  const matrix=data.transition_counts;
  if(!Array.isArray(matrix)||matrix.length!==2||matrix.some(row=>!Array.isArray(row)||row.length!==2))throw new Error('Invalid matrix');
  matrix.flat().forEach(integer);
  if(matrix.flat().reduce((a,b)=>a+b,0)!==data.overlapping_routes||matrix[0][1]+matrix[1][0]!==data.changed_routes)throw new Error('Inconsistent transitions');
  if(integer(data.evaluation_routes_outside_training_support)+data.overlapping_routes!==data.coverage.evaluation.routes_supported)throw new Error('Inconsistent comparison cohort');
  return data;
}

export function renderPatterns(data,period='train'){
  validatePatterns(data);if(!['train','evaluation'].includes(period))throw new Error('Invalid period');
  const coverage=data.coverage[period],title=period==='train'?'January–March 2025 · training':'May 2025 · frozen-model comparison';
  const bars=[['Arrival delay ≥15 minutes','delay_15_rate'],['Arrival delay ≥60 minutes','delay_60_rate'],['Cancellation','cancellation_rate']];
  return `<div class="pattern-insight"><div><span class="pattern-eyebrow">TEMPORAL COMPARISON</span><strong>${percent(data.changed_routes/data.overlapping_routes)} changed groups</strong><p>${count(data.changed_routes)} of ${count(data.overlapping_routes)} shared supported routes moved between groups in May. These are observed outcome patterns, not permanent route labels.</p></div><div class="pattern-stat"><span>Training separation</span><strong>${data.training_silhouette.toFixed(3)}</strong><span>Silhouette · not accuracy</span><p>Minimum training seed agreement: ${data.minimum_training_seed_ari.toFixed(3)} ARI. This does not establish seasonal stability.</p></div></div>
    <div class="pattern-period-heading"><h4>${title}</h4><span>${count(coverage.routes_supported)} supported routes · ${count(coverage.flights_on_supported_routes)} flights</span></div>
    <div class="pattern-groups">${data.profiles[period].map(row=>{const f=row.unweighted_mean_route_features;return `<article class="pattern-group pattern-group-${row.cluster}"><div class="pattern-group-heading"><h4>Group ${row.cluster}</h4><span>${count(row.routes)} routes</span></div><p class="pattern-group-description">${row.cluster===0?'Lower':'Higher'} mean delay-15 rate in the training fit. Group identity remains fixed in May.</p>${bars.map(([label,key])=>`<div class="pattern-bar-label"><span>${label}</span><strong>${percent(f[key])}</strong></div><div class="pattern-bar" aria-hidden="true"><span style="width:${(f[key]*100).toFixed(2)}%"></span></div>`).join('')}<div class="pattern-minutes"><span>Mean capped positive arrival delay</span><strong>${f.mean_positive_delay_capped_180.toFixed(2)} <small>minutes</small></strong></div><p class="pattern-weight">Unweighted mean route features · ${count(row.flights)} source flights in this group.</p></article>`;}).join('')}</div>
    <div class="pattern-bottom"><div class="research-table"><table><caption>Shared routes: training group to May group</caption><thead><tr><th scope="col">Training</th><th scope="col">May group 0</th><th scope="col">May group 1</th></tr></thead><tbody>${data.transition_counts.map((row,index)=>`<tr><th scope="row">Group ${index}</th>${row.map((value,column)=>`<td class="${index!==column?'pattern-moved':''}">${count(value)}${index!==column?' · moved':''}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="pattern-support"><h4>Keep the coverage in view</h4><p>${count(coverage.routes_observed-coverage.routes_supported)} observed routes in this period were below the completed-flight support threshold.</p><p>${count(data.evaluation_routes_outside_training_support)} supported May routes were outside the supported training cohort. They are excluded from the shared-route transition rate.</p></div></div>
    <details class="pattern-method"><summary>Method, provenance and limits</summary><p>Training: January–March, at least 200 completed observations per route. Comparison: May, at least 50. Routes combine carriers and remain directional. Delay rates use completed non-diverted flights with observed arrival delay; cancellation uses all route flights. Arrival minutes are clipped to 0–180 before averaging.</p><p>Training-only StandardScaler and KMeans selected two groups from k=2–6 using sampled silhouette and minimum support. May did not refit or select the model. Its outcomes had already been available for earlier experiments; this is not a newly untouched holdout.</p><p>Recorded ${escape(new Date(data.recorded_at).toLocaleString('en-GB',{timeZone:'UTC',hour12:false}))} UTC. Report file integrity verified; this is not live recalculation, independent acceptance or protected auditing.</p><p class="pattern-fingerprint">Report SHA-256: ${escape(data.report_sha256)}</p></details>
    <p class="research-caution">Historical US domestic research. No UAE validation, live feed, future-risk forecast or operational action. Production qualification remains incomplete.</p>`;
}

export function mountPatterns(parent){
  const section=document.createElement('section');section.className='research-card route-patterns';section.id='route-patterns';section.setAttribute('aria-labelledby','routePatternsHeading');
  section.innerHTML='<div class="pattern-heading"><div><span class="research-badge">Data science · Recorded experiment</span><h3 id="routePatternsHeading">Route patterns</h3><p>Compare historical delay groups and see how their assignments changed in May.</p></div><div class="pattern-controls"><label>Show period<select aria-label="Route pattern period"><option value="train">January–March · Training</option><option value="evaluation">May · Comparison</option></select></label><div><button type="button" class="btn sm">Refresh evidence</button><button type="button" class="btn sm" disabled>Export evidence JSON</button></div></div></div><div class="pattern-result" aria-live="polite" aria-atomic="true"></div>';
  parent.append(section);const select=section.querySelector('select'),[refresh,download]=section.querySelectorAll('button'),output=section.querySelector('.pattern-result');let active=false,generation=0,data=null;
  function draw(){output.innerHTML=renderPatterns(data,select.value);}
  async function load(){if(!active)return;const current=++generation;data=null;refresh.disabled=true;download.disabled=true;select.disabled=true;output.textContent='Verifying the recorded route experiment…';try{const response=await apiFetch('/api/v1/research/route-segments',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error();const payload=validatePatterns(await response.json());if(current===generation){data=payload;draw();download.disabled=false;}}catch{if(current===generation){data=null;output.textContent='Recorded segmentation evidence could not be verified. Previously displayed groups have been cleared.';}}finally{if(current===generation){refresh.disabled=false;select.disabled=!data;}}}
  select.addEventListener('change',()=>{if(data)draw();});refresh.addEventListener('click',load);
  download.addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_Route_Patterns_Evidence.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(user){generation++;active=!!user;data=null;select.value='train';output.replaceChildren();refresh.disabled=!active;select.disabled=true;download.disabled=true;if(active)load();}};
}
