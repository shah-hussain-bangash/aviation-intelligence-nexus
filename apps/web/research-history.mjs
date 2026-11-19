const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function renderHistory(runs) {
  if (!Array.isArray(runs)) throw new Error('Invalid history');
  if (!runs.length) return '<p>No saved research runs yet. Successful calculations will appear here.</p>';
  return `<div class="research-table"><table><caption>Latest ${runs.length} saved research runs · local anonymous session</caption>
    <thead><tr><th scope="col">Saved (UTC)</th><th scope="col">Scenario</th><th scope="col">Probability</th><th scope="col">Model</th><th scope="col">Review</th></tr></thead><tbody>
    ${runs.map(run => {
      const p = run.arrival_delay_15_probability;
      if (typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1 || !Number.isFinite(Date.parse(run.saved_at))) throw new Error('Invalid run');
      return `<tr><th scope="row">${escape(new Date(run.saved_at).toLocaleString('en-GB',{timeZone:'UTC',hour12:false}))}</th>
        <td>${escape(run.scenario.carrier)} · ${escape(run.scenario.origin)} to ${escape(run.scenario.destination)}<br>${escape(run.scenario.flight_date)} · ${escape(run.scenario.scheduled_departure)}</td>
        <td>${(p*100).toFixed(1)}%</td><td>${escape(run.model_version)}</td>
        <td><button class="btn sm" type="button" data-saved-run="${escape(run.run_id)}">View saved result</button></td></tr>`;
    }).join('')}</tbody></table></div>`;
}

export function mountHistory(parent,onView) {
  const section=document.createElement('section');
  section.className='research-history research-card';
  section.setAttribute('aria-labelledby','historyHeading');
  section.innerHTML=`<h3 id="historyHeading">Saved research history</h3>
    <p>Successful calculations are saved in your local project database with inputs, model identity and time. User accounts and tamper-proof auditing are not enabled.</p>
    <div class="research-toolbar"><button class="btn sm" type="button" data-history-refresh>Refresh history</button><button class="btn sm" type="button" data-history-export disabled>Export latest runs (JSON)</button></div>
    <div class="history-body" aria-live="polite">Loading saved runs…</div>`;
  parent.append(section);
  const body=section.querySelector('.history-body'),button=section.querySelector('[data-history-refresh]'),exportButton=section.querySelector('[data-history-export]');
  let runs=[],generation=0;
  async function refresh() {
    const current=++generation; button.disabled=true; exportButton.disabled=true; body.textContent='Loading saved runs…';
    try {
      const response=await fetch('/api/v1/research/history',{cache:'no-store',signal:AbortSignal.timeout(8000)});
      if(!response.ok) throw new Error('Unavailable');
      const payload=await response.json();
      if(current!==generation)return;
      const html=renderHistory(payload.runs); runs=payload.runs; body.innerHTML=html; exportButton.disabled=!runs.length;
    } catch {
      if(current===generation){runs=[];body.textContent='Saved history is unavailable. Check the backend and refresh. Previously displayed records are hidden until the connection succeeds.';}
    } finally {if(current===generation)button.disabled=false;}
  }
  button.addEventListener('click',refresh);
  section.addEventListener('click',event=>{
    const id=event.target.closest('[data-saved-run]')?.dataset.savedRun;
    if(id){const run=runs.find(item=>item.run_id===id);if(run)onView(run);}
  });
  exportButton.addEventListener('click',()=>{
    if(!runs.length)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify({scope:'Latest 10 local research runs; not tamper-proof',runs},null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='AIN_latest_research_runs.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  refresh();return {refresh};
}
