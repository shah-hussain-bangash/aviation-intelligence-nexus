import {mountGateReview} from './gate-review.mjs';
import {apiFetch} from './research-auth.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clock=minute=>`${String(Math.floor(minute/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;

export function sampleGateScenario(buffer=10,extra=false) {
  const gates=[{id:'N1',capacity:'narrow'},{id:'W1',capacity:'wide'}];
  if(extra)gates.push({id:'N2',capacity:'narrow'});
  const flights=[
    {id:'SIM-101',aircraft:'narrow',arrival:480,departure:600,costs:{N1:6,W1:1}},
    {id:'SIM-202',aircraft:'wide',arrival:500,departure:590,costs:{N1:20,W1:3}},
    {id:'SIM-303',aircraft:'narrow',arrival:605,departure:680,costs:{N1:2,W1:2}},
    {id:'SIM-404',aircraft:'narrow',arrival:700,departure:760,costs:{N1:1,W1:4}},
    {id:'SIM-505',aircraft:'wide',arrival:780,departure:840,costs:{N1:20,W1:2}}
  ];
  if(extra)for(const flight of flights)flight.costs.N2=5;
  return {data_kind:'synthetic',buffer_minutes:buffer,gates,flights};
}

export function renderGatePlan(result) {
  if(result.review_status?.state==='invalid')throw new Error('Saved proposal integrity failed');
  if(result.research_only!==true||result.operational_approval!==false||result.candidate.verification.feasible!==true)throw new Error('Unverified proposal');
  const candidate=result.candidate,baseline=result.baseline;
  const flights=new Map(result.scenario.flights.map(f=>[f.id,f]));
  return `<div class="gate-proposal"><span class="research-badge">${result.solver_status==='optimal'?'Optimal for this scenario':'Feasible candidate · optimality not proven'} · independently checked</span>
    <div class="research-kpis"><article><span>Optimized coverage</span><strong>${candidate.verification.assigned} / ${flights.size}</strong></article><article><span>Greedy baseline coverage</span><strong>${baseline.verification.assigned} / ${flights.size}</strong></article><article><span>Unassigned flights</span><strong>${candidate.verification.unassigned}</strong></article><article><span>Verified assignment cost</span><strong>${candidate.verification.assignment_cost}</strong></article></div>
    <p>Result scenario: ${result.scenario.gates.length} gates · ${result.scenario.buffer_minutes}-minute buffer after departure. Costs are synthetic units, not money. Coverage is prioritized before assignment cost. Baseline cost: ${baseline.verification.assignment_cost}; compare cost only alongside assigned-flight coverage.</p>
    <div class="research-table"><table><caption>Computed gate proposal · synthetic day · buffer after departure</caption><thead><tr><th>Flight</th><th>Aircraft</th><th>Arrival</th><th>Departure</th><th>Gate</th></tr></thead><tbody>
      ${result.scenario.flights.map(f=>`<tr><th scope="row">${escape(f.id)}</th><td>${escape(f.aircraft)}</td><td>${clock(f.arrival)}</td><td>${clock(f.departure)}</td><td>${escape(candidate.assignments.find(a=>a.flight===f.id)?.gate||'Unassigned')}</td></tr>`).join('')}
    </tbody></table></div><p class="research-caution">Research proposal only. No live airline allocation, safety approval or operational write is performed.</p>
    <p class="research-meta">Saved ${escape(result.saved_at)} · ${escape(result.actor)} · Run ${escape(result.run_id)} · Solver ${escape(result.engine)}</p></div>`;
}

export function mountGateLab(parent) {
  const section=document.createElement('section');section.className='research-card gate-lab';section.id='gate-lab';section.setAttribute('aria-labelledby','gateLabHeading');
  section.innerHTML=`<h3 id="gateLabHeading">Gate Allocation Lab</h3><p>Explore a real mathematical optimizer using five synthetic flights. It respects aircraft size, occupied time and turnaround buffer, then compares its plan with a simple greedy allocation.</p>
    <form class="gate-form"><label>Buffer after departure (minutes)<input name="buffer" type="number" min="0" max="60" value="10" required></label><label>Gate capacity<select name="capacity"><option value="standard">One narrow + one wide gate</option><option value="extra">Two narrow + one wide gate</option></select></label><button class="btn" type="submit" disabled>Compute gate proposal</button></form>
    <p class="gate-access">Sign in with researcher or admin access to compute a proposal.</p><div class="gate-result" role="status" aria-live="polite"></div>
    <div class="research-toolbar"><button class="btn sm" type="button" data-gate-history>Refresh saved proposals</button><button class="btn sm" type="button" data-gate-export disabled>Export proposal (JSON)</button></div><div class="gate-history" aria-live="polite"></div>`;
  parent.append(section);
  const form=section.querySelector('form'),button=form.querySelector('button'),output=section.querySelector('.gate-result'),history=section.querySelector('.gate-history'),exportButton=section.querySelector('[data-gate-export]');
  let available=false,shown=null,runs=[],generation=0,controller=null,user=null;
  const reviewUI=mountGateReview(section,result=>{generation++;show(result);refreshHistory();});
  async function refreshHistory(){
    const current=generation;
    try{const response=await apiFetch('/api/v1/research/gate-history',{signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error();const payload=await response.json();if(current!==generation)return;runs=payload.runs;
      history.innerHTML=runs.length?`<p>Latest saved proposals</p><div class="gate-history-buttons">${runs.map((run,i)=>`<button type="button" class="btn sm" data-gate-run="${i}">${escape(run.saved_at.slice(0,19).replace('T',' '))} UTC · ${run.candidate.verification.assigned}/${run.scenario.flights.length} assigned</button>`).join('')}</div>`:'<p>No saved gate proposals yet.</p>';
    }catch{if(current===generation){runs=[];history.textContent='Saved proposals are unavailable. Check your session and backend.';}}
  }
  function show(result){shown=null;exportButton.disabled=true;reviewUI.setProposal(null,user);try{output.innerHTML=renderGatePlan(result);shown=result;exportButton.disabled=false;reviewUI.setProposal(result,user);}catch{shown=null;exportButton.disabled=true;reviewUI.setProposal(null,user);output.textContent='Saved proposal integrity could not be verified. Results and review controls have been withheld.';}}
  form.addEventListener('input',()=>{generation++;controller?.abort();shown=null;reviewUI.setProposal(null,user);output.replaceChildren();exportButton.disabled=true;button.disabled=!available;});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!available||button.disabled)return;const current=++generation;controller?.abort();controller=new AbortController();const active=controller;const timer=setTimeout(()=>active.abort(),12000);button.disabled=true;shown=null;reviewUI.setProposal(null,user);exportButton.disabled=true;output.textContent='Solving constraints and independently checking the proposal…';
    try{const scenario=sampleGateScenario(Number(form.elements.buffer.value),form.elements.capacity.value==='extra');const response=await apiFetch('/api/v1/research/optimize-gates',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify(scenario),signal:active.signal});const result=await response.json();if(current!==generation)return;if(!response.ok)throw new Error();show(result);refreshHistory();}
    catch{if(current===generation)output.textContent='No verified proposal returned. Check your access, inputs and backend; no allocation was applied.';}
    finally{clearTimeout(timer);if(current===generation)button.disabled=!available;}
  });
  section.querySelector('[data-gate-history]').addEventListener('click',refreshHistory);
  section.addEventListener('click',event=>{const index=event.target.closest('[data-gate-run]')?.dataset.gateRun;if(index!==undefined&&runs[Number(index)]){generation++;controller?.abort();show(runs[Number(index)]);button.disabled=!available;}});
  exportButton.addEventListener('click',()=>{if(!shown)return;const url=URL.createObjectURL(new Blob([JSON.stringify(shown,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='AIN_synthetic_gate_proposal.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  return {setSession(value){user=value;generation++;reviewUI.setProposal(null,user);controller?.abort();available=['admin','researcher'].includes(user?.role);button.disabled=!available;shown=null;runs=[];output.replaceChildren();history.replaceChildren();exportButton.disabled=true;section.querySelector('.gate-access').textContent=available?'Synthetic research only. Every result is saved under your account.':'Viewer access: review your saved proposals; calculations require researcher or admin.';if(user)refreshHistory();}};
}
