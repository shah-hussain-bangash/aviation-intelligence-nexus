import { mountHistory } from './research-history.mjs';
import { apiFetch } from './research-auth.mjs';
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export function renderPrediction(result) {
  const p = result.arrival_delay_15_probability;
  if (typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1 || result.research_only !== true ||
      result.operational_serving_approved !== false || !Array.isArray(result.warnings)) throw new Error('Invalid result');
  return `<div class="scenario-answer"><span class="research-badge">Historical scenario · research only</span>
    <p class="scenario-probability">${(p * 100).toFixed(1)}%</p>
    <p>Estimated probability of arrival delay of at least 15 minutes, conditional on a completed, non-diverted flight.</p>
    <p><strong>${escape(result.scenario.carrier)} · ${escape(result.scenario.origin)} to ${escape(result.scenario.destination)}</strong> · ${escape(result.scenario.flight_date)} · ${escape(result.scenario.scheduled_departure)} local departure time · Model ${escape(result.model_version)}</p>
    ${result.run_id ? `<p class="research-meta">Saved locally: ${escape(result.saved_at)} · Run ${escape(result.run_id)}${result.replayed ? ' · previously saved result' : ''}</p>` : ''}
    <ul>${result.warnings.map(w => `<li>${escape(w)}</li>`).join('')}</ul></div>`;
}

export function mountScenario(parent) {
  const section = document.createElement('section');
  section.className = 'research-scenario research-card';
  section.setAttribute('aria-labelledby', 'scenarioHeading');
  section.innerHTML = `<h3 id="scenarioHeading">Try a historical flight scenario</h3>
    <p>Explore US schedule examples from January–May 2025. This does not confirm an actual flight. Dates outside this window and unfamiliar carrier or airport codes are rejected.</p>
    <form id="researchScenario"><div class="scenario-fields">
      <label>US reporting carrier code<input name="carrier" value="AA" pattern="[A-Z0-9]{2,3}" maxlength="3" required autocomplete="off"></label>
      <label>Origin airport<input name="origin" value="JFK" pattern="[A-Z]{3}" maxlength="3" required autocomplete="off"></label>
      <label>Destination airport<input name="destination" value="LAX" pattern="[A-Z]{3}" maxlength="3" required autocomplete="off"></label>
      <label>Historical flight date<input type="date" name="flight_date" value="2025-05-15" min="2025-01-01" max="2025-05-31" required></label>
      <label>Scheduled departure (local)<input type="time" name="scheduled_departure" value="09:00" required></label>
    </div><p class="research-caution">No live flight feed, cancellation prediction or operational recommendation. Probability calibration remains limited. Successful calculations are saved locally in research history.</p>
    <button class="btn" type="submit" disabled>Calculate research probability</button>
    <p class="scenario-availability">Connect to the verified research model to use this form.</p></form>
    <div class="scenario-result" role="status" aria-live="polite"></div>`;
  parent.append(section);
  const form = section.querySelector('form'), button = section.querySelector('button');
  const output = section.querySelector('.scenario-result'), availability = section.querySelector('.scenario-availability');
  let available = false, request = null, generation = 0;
  const historyUI = mountHistory(parent, run => {
    generation++; request?.abort();
    for (const [name,value] of Object.entries(run.scenario)) {
      if(form.elements.namedItem(name)) form.elements.namedItem(name).value=value;
    }
    output.innerHTML=renderPrediction({...run,replayed:true});
    button.disabled=!available;
  });
  form.addEventListener('input', event => {
    if (['carrier', 'origin', 'destination'].includes(event.target.name)) event.target.value = event.target.value.toUpperCase();
    generation++; request?.abort(); output.replaceChildren(); button.disabled = !available;
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!available || button.disabled) return;
    const current = ++generation;
    request?.abort(); request = new AbortController();
    const controller = request;
    const timeout = setTimeout(() => controller.abort(), 12000);
    button.disabled = true; output.textContent = 'Calculating a research probability…';
    try {
      const response = await apiFetch('/api/v1/research/predict', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify(Object.fromEntries(new FormData(form))), signal: controller.signal, cache: 'no-store' });
      const result = await response.json();
      if (current !== generation) return;
      if (!response.ok) {
        output.textContent = response.status === 422
          ? 'No probability produced. Check the date, schedule and airport/carrier codes. Inputs must be in the historical US training vocabulary.'
          : 'No probability produced. The verified research model is unavailable. Refresh the connection and try again.';
        return;
      }
      output.innerHTML = renderPrediction(result);
      historyUI.refresh();
    } catch {
      if (current === generation) output.textContent = 'No probability produced. Check the backend connection and try again.';
    } finally {
      clearTimeout(timeout);
      if (current === generation) button.disabled = !available;
    }
  });
  return { clearHistory:()=>historyUI.clear(), refreshHistory:()=>historyUI.refresh(), setAvailable(value,reason) {
    available = value; generation++; request?.abort(); output.replaceChildren(); button.disabled = !value;
    availability.textContent = value ? 'Verified v2 model connected. Results are illustrative research outputs.'
      : reason || 'Connect to the verified research model to use this form.';
  } };
}
