import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const validCount=value=>{if(!Number.isSafeInteger(value)||value<0)throw new Error('Invalid count');return value;};
const finite=(value,min,max)=>{if(!Number.isFinite(value)||value<min||value>max)throw new Error('Invalid metric');return value;};
const count=value=>validCount(value).toLocaleString('en-US');
const percent=value=>(finite(value,0,1)*100).toFixed(1)+'%';

export function validateRouteHistory(data){
  if(data?.format!=='ain-route-history-v1'||data.source!=='BTS_REPORTING_CARRIER'||data.research_only!==true||data.production_ready!==false||data.group_assignment!==null||!Number.isFinite(Date.parse(data.checked_at))||!['origin','destination'].every(key=>/^[A-Z]{3}$/.test(data.route?.[key]??''))||data.route.origin===data.route.destination)throw new Error('Invalid historical route response');
  if(!Array.isArray(data.periods)||data.periods.length!==2)throw new Error('Invalid periods');
  for(const [index,row] of data.periods.entries()){
    if(row.id!==['train','evaluation'][index]||row.support_threshold!==[200,50][index])throw new Error('Invalid period scope');
    for(const key of ['flights','completed','delayed_15','delayed_60','cancelled','diverted','missing_arrival'])validCount(row[key]);
    if(row.available!==(row.flights>0)||row.meets_support!==(row.completed>=row.support_threshold)||['completed','cancelled','diverted','missing_arrival'].some(key=>row[key]>row.flights)||row.delayed_60>row.delayed_15||row.delayed_15>row.completed)throw new Error('Inconsistent cohort counts');
    for(const [name,eventKey,denominator] of [['delay_15','delayed_15',row.completed],['delay_60','delayed_60',row.completed],['cancellation','cancelled',row.flights]]){
      const p=row[name];if(p.events!==row[eventKey]||p.observations!==denominator)throw new Error('Inconsistent rate denominator');
      if(!denominator){if(p.rate!==null||p.wilson_95!==null)throw new Error('Missing cohort shown as zero risk');continue;}
      finite(p.rate,0,1);if(Math.abs(p.rate-p.events/denominator)>1e-10||!Array.isArray(p.wilson_95)||p.wilson_95.length!==2)throw new Error('Invalid rate');
      const [low,high]=p.wilson_95;finite(low,0,1);finite(high,0,1);if(low>p.rate+1e-12||high<p.rate-1e-12)throw new Error('Invalid interval');
    }
    if(row.completed){finite(row.mean_positive_delay_capped_180,0,180);}else if(row.mean_positive_delay_capped_180!==null)throw new Error('Missing mean');
  }
  const supported=data.periods.every(row=>row.meets_support);
  if(data.comparison_support_met!==supported)throw new Error('Unsupported comparison claim');
  if(supported){const expected=(data.periods[1].delay_15.rate-data.periods[0].delay_15.rate)*100;finite(data.delay_15_change_percentage_points,-100,100);if(Math.abs(data.delay_15_change_percentage_points-expected)>1e-9)throw new Error('Invalid rate change');}else if(data.delay_15_change_percentage_points!==null)throw new Error('Sparse comparison claim');
  return data;
}

function rateRow(title,p){
  if(p.rate===null)return `<div class="route-rate"><span>${title}</span><strong>Not available</strong><p>No eligible observations; a zero rate is not assumed.</p></div>`;
  const [low,high]=p.wilson_95;
  return `<div class="route-rate"><div><span>${title}</span><strong>${percent(p.rate)}</strong></div><div class="route-interval" aria-hidden="true"><span style="left:${(low*100).toFixed(3)}%;width:${((high-low)*100).toFixed(3)}%"></span><i style="left:${(p.rate*100).toFixed(3)}%"></i></div><p>95% Wilson interval ${percent(low)}–${percent(high)} · ${count(p.events)} / ${count(p.observations)} observations</p></div>`;
}

export function renderRouteHistory(data){
  validateRouteHistory(data);
  const change=data.delay_15_change_percentage_points;
  return `<div class="route-summary"><div><span class="route-eyebrow">DIRECTIONAL ROUTE · CARRIERS COMBINED</span><h4>${escape(data.route.origin)} to ${escape(data.route.destination)}</h4><p>Actual imported historical observations. January–March is compared with May; April is excluded.</p></div><div><span>Delay ≥15 rate change</span><strong>${change===null?'Insufficient support':`${change>=0?'+':''}${change.toFixed(1)} pp`}</strong><p>${change===null?'At least 200 completed observations in training and 50 in May are needed for this comparison.':'May minus January–March · descriptive percentage-point difference, not a significance or causal finding.'}</p></div></div>
    <div class="route-cohorts">${data.periods.map(row=>`<article class="route-cohort"><div class="route-cohort-heading"><h4>${row.id==='train'?'January–March 2025':'May 2025'}</h4><span>${row.meets_support?'Support met':'Limited support'}</span></div>${!row.available?'<p class="research-caution">No official observations for this period. Rates are unavailable.</p>':`<p class="route-count"><strong>${count(row.flights)}</strong> source flights · ${count(row.completed)} completed observed arrivals</p>${rateRow('Arrival delay ≥15 minutes',row.delay_15)}${rateRow('Arrival delay ≥60 minutes',row.delay_60)}${rateRow('Cancellation',row.cancellation)}<p class="route-average">Mean capped positive arrival delay: <strong>${row.mean_positive_delay_capped_180===null?'Not available':row.mean_positive_delay_capped_180.toFixed(2)+' minutes'}</strong></p><p class="route-exclusions">${count(row.cancelled)} cancelled · ${count(row.diverted)} diverted · ${count(row.missing_arrival)} otherwise-completed flights missing arrival delay.</p>`}</article>`).join('')}</div>
    <details class="route-history-method"><summary>How to interpret these numbers</summary><p>Delay rates use completed, non-diverted flights with an observed arrival delay. Cancellation uses all source flights. Mean positive arrival delay clips each eligible observation to 0–180 minutes. The intervals use a nominal 95% Wilson score under an independent-binomial model; shared weather and operations can violate independence. They do not predict the next flight or establish a significant trend.</p><p>Training/May support thresholds match the segmentation experiment, but this lookup does not assign a cluster. Its query reads currently imported official rows; these are not frozen experiment assignments.</p><p>Checked ${escape(new Date(data.checked_at).toLocaleString('en-GB',{timeZone:'UTC',hour12:false}))} UTC · No raw flight or account records are included in this view/export.</p></details><p class="research-caution">Historical US domestic research only. No live flight feed, UAE validation or operational recommendation. Production qualification remains incomplete.</p>`;
}

export function mountRouteHistory(parent){
  const section=document.createElement('section');section.id='route-history';section.className='research-card route-history';section.setAttribute('aria-labelledby','routeHistoryHeading');
  section.innerHTML='<span class="research-badge">Data science · Historical route lookup</span><h3 id="routeHistoryHeading">Look beyond the route average</h3><p>Choose a directional route to compare observed delays, cancellations and uncertainty.</p><form class="route-history-form"><label>Origin airport<input name="origin" value="JFK" required pattern="[A-Za-z]{3}" minlength="3" maxlength="3" autocomplete="off" aria-label="Historical route origin airport"></label><label>Destination airport<input name="destination" value="LAX" required pattern="[A-Za-z]{3}" minlength="3" maxlength="3" autocomplete="off" aria-label="Historical route destination airport"></label><button class="btn primary" type="submit" disabled>Compare history</button><button class="btn" type="button" data-route-export disabled>Export route evidence</button></form><div class="route-history-result" aria-live="polite" aria-atomic="true"></div>';
  parent.append(section);const form=section.querySelector('form'),submit=form.querySelector('[type=submit]'),download=form.querySelector('[data-route-export]'),output=section.querySelector('.route-history-result');let active=false,generation=0,controller,data=null;
  function clear(message=''){generation++;controller?.abort();data=null;download.disabled=true;submit.disabled=!active;output.textContent=message;}
  form.addEventListener('input',()=>clear(active?'Inputs changed. Select Compare history to load this route.':''));
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!active)return;
    const origin=form.elements.origin.value.trim().toUpperCase(),destination=form.elements.destination.value.trim().toUpperCase();
    clear();if(!/^[A-Z]{3}$/.test(origin)||!/^[A-Z]{3}$/.test(destination)||origin===destination){output.textContent='Enter two different three-letter airport codes.';return;}
    form.elements.origin.value=origin;form.elements.destination.value=destination;const current=generation;controller=new AbortController();submit.disabled=true;output.textContent='Comparing historical observations… This can take several seconds.';
    try{const query=new URLSearchParams({origin,destination});const response=await apiFetch('/api/v1/research/route-profile?'+query,{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(10000)])});if(!response.ok){const errors={404:'No official observations were found for this route in the defined periods.',429:'Another route comparison is running. Try again shortly.',503:'Historical observations could not be read within the local limits. Try again shortly.'};throw new Error(errors[response.status]??'Historical route evidence could not be verified. Check your session and connection.');}const payload=validateRouteHistory(await response.json());if(payload.route.origin!==origin||payload.route.destination!==destination)throw new Error('The response did not match the requested route.');if(current===generation){data=payload;output.innerHTML=renderRouteHistory(data);download.disabled=false;}}
    catch(error){if(current===generation){data=null;download.disabled=true;output.textContent=error.name==='AbortError'?'The comparison was cancelled. Select Compare history to try again.':error.message;}}
    finally{if(current===generation)submit.disabled=!active;}
  });
  download.addEventListener('click',()=>{if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`AIN_Route_History_${data.route.origin}_${data.route.destination}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(user){active=!!user;form.reset();clear();form.querySelectorAll('input').forEach(input=>input.disabled=!active);}};
}
