import {apiFetch} from './research-auth.mjs';

const states=['queued','running','awaiting_review','reviewed','needs_changes','failed','interrupted','cancelled','withdrawn'];
const uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const hash=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const text=(v,max)=>typeof v==='string'&&v.length>0&&v.length<=max;
const date=v=>typeof v==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v));
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function require(ok){if(!ok){const error=Error('Unverified case investigation');error.protocol=true;throw error;}}
const contextFields=['case_id','case_version','case_sha256','source_run_id','source_sha256','title','scope'];
export function validateJobContext(c,record){
 require(record.scope==='historical_us_research'&&record.operational_approval===false&&record.production_ready===false);
 require(c&&Object.keys(c).length===contextFields.length);
 require(c&&c.case_id===record.id&&Number.isInteger(c.case_version)&&c.case_version>=1&&c.case_version<=record.version&&hash(c.case_sha256)&&c.source_run_id===record.source_run_id&&c.source_sha256===record.source_sha256&&c.title===record.title&&c.scope==='historical_us_research');return c;
}
export function validateCaseJobs(r,record){
 require(r&&r.production_ready===false&&Array.isArray(r.jobs)&&r.jobs.length<=10);
 const seen=new Set();for(const row of r.jobs){require(row&&uuid(row.run_id)&&!seen.has(row.run_id)&&states.includes(row.state)&&date(row.updated_at));validateJobContext(row.case_context,record);seen.add(row.run_id);}return r.jobs;
}
export function validateCaseJob(r,record,reference=null){
 require(r&&uuid(r.run_id)&&states.includes(r.state)&&r.research_only===true&&r.operational_approval===false&&r.runtime==='bounded-ollama-tools-v2'&&r.execution==='local-background-queue-v1');
 require(r.request&&text(r.request.objective,600)&&r.request.require_peer_review!==true&&date(r.updated_at));
 const context=validateJobContext(r.request.case_context,record);
 if(reference)require(r.run_id===reference.run_id&&reference.case_context&&contextFields.every(k=>context[k]===reference.case_context[k]));
 require(Array.isArray(r.steps)&&r.steps.length<=3&&Array.isArray(r.claims)&&r.claims.length<=6);
 for(const step of r.steps)require(step&&['flight_metrics','knowledge_search','gate_simulation','route_history','model_evidence','distribution_evidence','duration_evidence'].includes(step.tool)&&['running','completed','failed','interrupted','cancelled_before_execution'].includes(step.state));
 for(const claim of r.claims)require(claim&&text(claim.quote,8000)&&claim.text===claim.quote&&text(claim.citation,80));
 if(['awaiting_review','reviewed','needs_changes'].includes(r.state))require(hash(r.report_sha256));
 if(r.quality)require(typeof r.quality.passed==='boolean');
 if(r.cancel_requested_at)require(date(r.cancel_requested_at));
 require(new TextEncoder().encode(JSON.stringify(r)).length<=800000);return r;
}
export function caseJobRequest(record,objective){
 require(uuid(record.id)&&Number.isInteger(record.version)&&record.version>=1&&record.version<=100&&record.scope==='historical_us_research'&&record.operational_approval===false&&record.production_ready===false);
 objective=objective.trim();require(record.status==='open'&&text(objective,600)&&objective.length>=12);
 return {expected_version:record.version,investigation:{objective,month:'2025-05',include_simulation:false,required_tools:['distribution_evidence'],include_distribution_evidence:true,document_scope:null}};
}
export function renderCaseJob(r,record){
 validateCaseJob(r,record);const c=r.request.case_context,older=c.case_version<record.version;
 const quality=r.quality?`Automated coverage ${r.quality.passed?'passed':'blocked'}`:'Automated coverage not recorded';
 return `<article class="case-job-result"><div class="case-job-heading"><h5>${r.state==='awaiting_review'?'Unreviewed research draft':'Saved investigation'}</h5><span class="research-badge">${escape(r.state.replaceAll('_',' '))}</span></div><p><strong>Captured case v${c.case_version}</strong> · Current case v${record.version}${older?' · Earlier case context':''}</p><p>${escape(r.request.objective)}</p><dl class="case-lineage"><dt>Run ID</dt><dd><code>${r.run_id}</code></dd><dt>Captured case fingerprint</dt><dd><code>${c.case_sha256}</code></dd><dt>Saved update</dt><dd><time>${escape(r.updated_at)}</time></dd></dl><p>${quality}. Automated checks do not establish answer usefulness or human acceptance.</p>${r.state==='running'&&r.cancel_requested_at?'<p class="research-caution">Stop requested. An in-flight call may finish before the next safe boundary.</p>':''}${r.error?`<p class="research-caution">${escape(r.error)}</p>`:''}<ol class="case-job-steps">${r.steps.map(s=>`<li><strong>${escape(s.tool)}</strong> · ${escape(s.state.replaceAll('_',' '))}</li>`).join('')||'<li>No tool checkpoint recorded yet.</li>'}</ol>${r.claims.length?`<h5>Saved quoted findings</h5><ul>${r.claims.map(c=>`<li><p>${escape(c.quote)}</p><small>${escape(c.citation)}</small></li>`).join('')}</ul>`:''}<details><summary>Inspect saved report and case context</summary><pre>${escape(JSON.stringify(r,null,2))}</pre></details><p>Saved research output only. Refresh reads checkpoints; it does not rerun a model. Review and attachment remain separate actions. No airline action is applied.</p></article>`;
}

export class CaseJobClient {
 constructor(fetcher=apiFetch,changed=()=>{},newKey=()=>crypto.randomUUID()){
  Object.assign(this,{fetcher,changed,newKey,key:'',epoch:0,user:null,record:null,available:false,busy:false,controller:null,rows:[],selected:null,pending:null,blocked:false,loaded:false,message:''});
 }
 get writer(){return ['admin','researcher'].includes(this.user?.role);}
 get canStart(){return Boolean(this.writer&&this.record?.status==='open'&&this.available&&!this.blocked);}
 get canCancel(){return Boolean(this.writer&&this.available&&!this.blocked&&this.selected&&['queued','running'].includes(this.selected.state)&&!this.selected.cancel_requested_at);}
 remember(result){
  this.selected=result;const ref={run_id:result.run_id,state:result.state,case_context:result.request.case_context,updated_at:result.updated_at};
  this.rows=this.rows.some(r=>r.run_id===result.run_id)?this.rows.map(r=>r.run_id===result.run_id?ref:r):[ref,...this.rows].slice(0,10);
 }
 setContext(user,record,available){
  const key=user&&record?JSON.stringify([user.username,user.role,record.id,record.version,record.status,record.source_sha256]):'';
  if(key!==this.key){this.epoch++;this.controller?.abort();Object.assign(this,{key,controller:null,rows:[],selected:null,pending:null,blocked:false,busy:false,loaded:false,message:''});}
  Object.assign(this,{user,record,available:Boolean(available&&user&&record)});this.changed();
  if(this.available&&!this.loaded&&!this.busy)return this.load();return Promise.resolve(false);
 }
 async json(path,options={}){
  const response=await this.fetcher(path,{...options,signal:this.controller.signal});
  if(!response.ok){const error=Error();error.status=response.status;throw error;}return response.json();
 }
 async action(work){
  if(this.busy||!this.available)return false;
  const epoch=++this.epoch;this.controller=new AbortController();const controller=this.controller;
  const timer=setTimeout(()=>controller.abort(),12000);this.busy=true;this.changed();
  const current=()=>epoch===this.epoch;
  try{await work(current);return current();}
  catch(error){if(current()){
   this.rows=[];this.selected=null;this.loaded=false;
   this.blocked=Boolean(error.protocol||[401,403,409].includes(error.status));
   this.message=error.status===409?'Saved state or the request changed. Refresh cases and reselect before starting again.':error.status===429?'The local queue is full. Wait, refresh saved runs and retry the same submission.':error.status===503?'The local worker or case storage is unavailable. Refresh to check saved investigations.':error.protocol?'The response did not match this case. Results were cleared; refresh cases and reselect.':'No verified response returned. A submission may have completed. Retry the same submission or inspect saved investigations before starting another.';
  }return false;}
  finally{clearTimeout(timer);if(current()){this.busy=false;this.controller=null;this.changed();}}
 }
 load(){return this.action(async current=>{
  const record=this.record,old=this.selected?.run_id;const rows=validateCaseJobs(await this.json(`/api/v1/research/cases/${record.id}/jobs`),record);
  const ref=rows.find(r=>r.run_id===old);const selected=ref?validateCaseJob(await this.json('/api/v1/research/agent-jobs/'+ref.run_id),record,ref):null;
  if(current()){Object.assign(this,{rows,selected,loaded:true,message:`${rows.length} saved investigations. Updates appear when you refresh.`});if(selected)this.remember(selected);}
 });}
 select(runId){
  if(!runId){this.epoch++;this.controller?.abort();this.busy=false;this.selected=null;this.changed();return Promise.resolve(false);}
  const ref=this.rows.find(r=>r.run_id===runId);if(!ref)return Promise.resolve(false);
  return this.action(async current=>{const result=validateCaseJob(await this.json('/api/v1/research/agent-jobs/'+runId),this.record,ref);if(current()){this.remember(result);this.message='Saved case-bound investigation loaded. No model was rerun.';}});
 }
 submit(objective,acknowledged){
  if(!this.canStart||this.busy||acknowledged!==true)return Promise.resolve(false);
  const body=JSON.stringify(caseJobRequest(this.record,objective));if(this.pending&&this.pending.body!==body)return Promise.resolve(false);
  const pending=this.pending??{body,key:this.newKey()};this.pending=pending;
  return this.action(async current=>{
   const result=validateCaseJob(await this.json(`/api/v1/research/cases/${this.record.id}/jobs`,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body:pending.body}),this.record);
   const expected=JSON.parse(pending.body).investigation;
   require(Object.keys(result.request).length===Object.keys(expected).length+1&&Object.entries(expected).every(([k,v])=>JSON.stringify(result.request[k])===JSON.stringify(v)));
   require(result.request.case_context.case_version===this.record.version&&result.request.objective===objective.trim());
   if(current()){this.remember(result);this.pending=null;this.loaded=true;this.message='Investigation saved to the local queue. Refresh to inspect checkpoints; no review or attachment was recorded.';}
  });
 }
 cancel(){
  if(!this.canCancel||this.busy)return Promise.resolve(false);const old=this.selected;
  return this.action(async current=>{const result=validateCaseJob(await this.json('/api/v1/research/agent-cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:old.run_id})}),this.record,{run_id:old.run_id,case_context:old.request.case_context});
   if(current()){this.remember(result);this.message=result.state==='cancelled'?'Waiting investigation cancelled. Saved evidence is retained.':'Stop requested. Refresh after the next safe boundary; an in-flight call may finish.';}
  });
 }
}

export function mountCaseJobs(parent){
 const section=document.createElement('section');section.className='case-jobs';section.hidden=true;section.setAttribute('aria-labelledby','case-jobs-heading');
 section.innerHTML=`<div class="case-job-heading"><div><span class="research-badge">Case-linked local AI</span><h4 id="case-jobs-heading">Investigate this case</h4><p>Start a bounded investigation tied to the case version you have inspected.</p></div><span class="scoped-private">Owner-only</span></div><p data-context></p><form data-start><label>Case investigation objective<textarea name="objective" minlength="12" maxlength="600" required rows="3"></textarea></label><button type="button" class="btn sm" data-example>Use comparison example</button><p>New investigation scope: recorded January–March versus May 2025 input distributions. No individual-flight explanation, simulation or case sharing.</p><label class="case-job-consent"><input type="checkbox" name="ack"> I understand this starts local AI using the case title and version metadata. Case notes are not automatically sent; the output requires review.</label><button type="submit" class="btn" data-submit>Start case investigation</button></form><div class="case-job-actions"><button type="button" class="btn sm" data-refresh>Refresh investigations</button><button type="button" class="btn sm" data-run-refresh>Refresh selected run</button><button type="button" class="btn sm" data-cancel>Request investigation stop</button></div><p data-status role="status" aria-live="polite"></p><label>Saved case investigations<select data-runs aria-label="Saved case investigations"></select></label><div data-result></div><p class="case-job-scope">Updates are manual. Refreshing or selecting a run does not start AI. Leaving this view or signing out does not cancel saved work. To submit again after a reload, inspect saved runs first. Reviews and attachments use the existing investigation and case controls.</p>`;
 parent.append(section);const form=section.querySelector('[data-start]'),list=section.querySelector('[data-runs]'),result=section.querySelector('[data-result]');let renderedKey='',renderedRun=null;
 const client=new CaseJobClient(apiFetch,()=>{
  section.hidden=!client.record||!client.user;if(section.hidden){form.reset();renderedKey='';renderedRun=null;result.replaceChildren();list.replaceChildren();section.querySelector('[data-context]').textContent='';section.querySelector('[data-status]').textContent='';return;}
  if(renderedKey!==client.key){form.reset();renderedKey=client.key;renderedRun=null;result.replaceChildren();}
  form.hidden=!client.writer||client.record.status!=='open';
  form.elements.objective.disabled=!client.canStart||client.busy||Boolean(client.pending);form.elements.ack.disabled=form.elements.objective.disabled;
  section.querySelector('[data-example]').disabled=form.elements.objective.disabled;
  const submit=section.querySelector('[data-submit]');submit.textContent=client.pending?'Retry same submission':'Start case investigation';submit.disabled=!client.canStart||client.busy||(!client.pending&&(!form.elements.ack.checked||form.elements.objective.value.trim().length<12));
  section.querySelector('[data-context]').textContent=`${client.record.title} · case v${client.record.version} · ${client.record.status}. Captured version metadata stays with the saved job.`;
  section.querySelector('[data-refresh]').disabled=!client.available||client.busy;section.querySelector('[data-run-refresh]').disabled=!client.available||client.busy||!client.selected;
  section.querySelector('[data-cancel]').disabled=!client.canCancel||client.busy;
  section.querySelector('[data-status]').textContent=client.message;
  list.replaceChildren(new Option('Choose a saved investigation',''),...client.rows.map(r=>new Option(`Case v${r.case_context.case_version} · ${r.state.replaceAll('_',' ')} · ${r.run_id}`,r.run_id)));list.value=client.selected?.run_id??'';list.disabled=!client.available||client.busy||!client.rows.length;
  if(renderedRun!==client.selected){result.innerHTML=client.selected?renderCaseJob(client.selected,client.record):'';renderedRun=client.selected;}section.setAttribute('aria-busy',String(client.busy));
 });
 form.addEventListener('input',()=>client.changed());
 section.querySelector('[data-example]').addEventListener('click',()=>{form.elements.objective.value='Inspect the recorded historical input-distribution comparison for this case. Quote its limits and avoid individual-flight explanations.';client.changed();});
 form.addEventListener('submit',async event=>{event.preventDefault();if(await client.submit(form.elements.objective.value,form.elements.ack.checked)){form.elements.ack.checked=false;client.changed();}});
 section.querySelector('[data-refresh]').addEventListener('click',()=>client.load());section.querySelector('[data-run-refresh]').addEventListener('click',()=>client.select(client.selected?.run_id));
 section.querySelector('[data-cancel]').addEventListener('click',()=>client.cancel());list.addEventListener('change',()=>client.select(list.value));
 return {element:section,setContext:(user,record,available)=>client.setContext(user,record,available)};
}
