import { mountScenario } from './research-scenario.mjs';
import { apiFetch, canCalculate, mountAuth } from './research-auth.mjs';
const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const number = value => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error('Invalid numeric response');
  return value;
};
const count = value => number(value).toLocaleString('en-US');
const metric = value => number(value).toFixed(3);
const percentage = value => `${(number(value) * 100).toFixed(1)}%`;

export function renderResearchSummary(data) {
  if (!data || !data.dataset || !Array.isArray(data.dataset.monthly) || !Number.isFinite(Date.parse(data.generated_at))) {
    throw new Error('Invalid research response');
  }
  const dataset = data.dataset;
  const model = data.model;
  const timestamp = new Date(data.generated_at).toLocaleString('en-GB', { timeZone: 'UTC', hour12: false });
  let html = `<p class="research-scope">${escape(data.source_scope)}. This section reads your local database and verified experiment report. Other dashboard workspaces retain their prototype data.</p>
    <div class="research-kpis">
      <article><span>Imported flights</span><strong>${count(dataset.records)}</strong></article>
      <article><span>Reporting carriers</span><strong>${count(dataset.carriers)}</strong></article>
      <article><span>Historical months</span><strong>${count(dataset.monthly.length)}</strong></article>
      <article><span>Operational prediction serving</span><strong class="research-disabled">Disabled</strong></article>
    </div>
    <p class="research-meta">Coverage: ${escape(dataset.first_date ?? 'No records')} to ${escape(dataset.last_date ?? 'No records')} · Checked ${escape(timestamp)} UTC</p>
    <div class="research-columns"><article class="research-card"><h3>Source coverage</h3>
    <div class="research-table"><table><caption>Imported historical flight records by month</caption><thead><tr><th scope="col">Month</th><th scope="col">Flights</th><th scope="col">Cancelled</th><th scope="col">Diverted</th></tr></thead><tbody>
    ${dataset.monthly.map(row => `<tr><th scope="row">${escape(row.period)}</th><td>${count(row.records)}</td><td>${count(row.cancelled)}</td><td>${count(row.diverted)}</td></tr>`).join('')}
    </tbody></table></div><p><a href="https://transtats.bts.gov/PREZIP/" target="_blank" rel="noopener noreferrer">Official BTS archives</a> · Raw flight data stays outside GitHub.</p></article>`;
  if (model) {
    const rows = [['ROC-AUC ↑', 'roc_auc'], ['Average precision ↑', 'average_precision'], ['Log loss ↓', 'log_loss'], ['Brier score ↓', 'brier_score']];
    const falseAlerts = model.model_metrics.confusion_matrix_labels_0_1[0][1];
    html += `<article class="research-card"><h3>Measured model evaluation</h3>
      <p><strong>${escape(model.version)}</strong> · ${escape(model.algorithm)}</p>
      <span class="research-badge">${model.research_gate_passed === true ? 'Research checks passed' : 'Research checks not passed'} · research only</span>
      <p>Trained on ${count(model.training_records)} flights. Tested on ${count(model.test_records)} flights in ${escape(model.test_periods.join(', '))}.</p>
      <div class="research-table"><table><caption>Same-period model and constant training-prior comparison</caption><thead><tr><th scope="col">Metric</th><th scope="col">Model</th><th scope="col">Baseline</th></tr></thead><tbody>
      ${rows.map(([label, key]) => `<tr><th scope="row">${label}</th><td>${metric(model.model_metrics[key])}</td><td>${metric(model.baseline_metrics[key])}</td></tr>`).join('')}
      </tbody></table></div>
      <p>At demonstration threshold ${metric(model.threshold)}: precision ${percentage(model.model_metrics.precision)}, recall ${percentage(model.model_metrics.recall)}.</p>
      <p class="research-caution"><strong>${count(falseAlerts)} false alerts in the test month.</strong> This model is not approved for airline decisions. Further calibration and operational validation are required.</p></article>`;
  } else {
    html += '<article class="research-card"><h3>Model report unavailable</h3><p>The data connection works, but no verified v2 report is available. Model scores are withheld.</p></article>';
  }
  return html + '</div><p class="research-boundary">Historical research data · no live airline feed · no operational predictions served · production qualification incomplete.</p>';
}

if (typeof document !== 'undefined') {
  const section = document.createElement('section');
  section.className = 'live-research';
  section.setAttribute('aria-label', 'Connected historical research data');
  section.innerHTML = `<details open><summary><span>Connected research data</span><span id="researchConnection" role="status" aria-live="polite">Connecting…</span></summary>
    <div class="research-inner"><div class="research-toolbar"><p>Real database counts and measured model evidence</p><button type="button" class="btn sm" id="refreshResearch">Refresh data</button></div>
    <div id="researchBody"><p>Checking the local backend…</p></div></div></details>`;
  document.getElementById('content').before(section);
  const scenarioUI = mountScenario(section.querySelector('.research-inner'));
  const body = document.getElementById('researchBody');
  const status = document.getElementById('researchConnection');
  const refresh = document.getElementById('refreshResearch');
  async function update() {
    scenarioUI.setAvailable(false);
    refresh.disabled = true;
    status.textContent = 'Connecting…';
    section.dataset.state = 'loading';
    body.innerHTML = '<p>Checking the local backend…</p>';
    try {
      if (location.protocol === 'file:') throw new Error('Use the local dashboard server');
      const response = await apiFetch('/api/v1/research/summary', { signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error('Backend unavailable');
      const payload = await response.json();
      body.innerHTML = renderResearchSummary(payload);
      status.textContent = 'Backend connected · historical data';
      section.dataset.state = 'connected';
      scenarioUI.setAvailable(payload.model?.research_gate_passed === true && canCalculate(),
        canCalculate() ? undefined : 'Viewer access: data and reports are available; calculations require a researcher or administrator.');
    } catch {
      status.textContent = 'Backend unavailable';
      section.dataset.state = 'unavailable';
      body.innerHTML = '<div class="research-caution"><strong>Historical data could not be verified.</strong><p>Start the Python backend on port 8002 and the dashboard server, then select Refresh data. Previously displayed counts and model scores are hidden until the connection succeeds. You can continue exploring the prototype workspaces below.</p></div>';
    } finally {
      refresh.disabled = false;
    }
  }
  refresh.addEventListener('click', update);
  section.querySelector('details').hidden=true;
  mountAuth(section,user=>{
    section.querySelector('details').hidden=!user;
    scenarioUI.setAvailable(false);
    scenarioUI.clearHistory();
    body.replaceChildren();
    if(user){scenarioUI.refreshHistory();update();}
  });
}
