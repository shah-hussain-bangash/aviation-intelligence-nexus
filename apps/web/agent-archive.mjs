import {apiFetch} from './research-auth.mjs';
import {archiveStates,archiveQuery,validateArchive} from './agent-archive-contract.mjs';
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderArchive(data){
 validateArchive(data);
 return data.runs.length?`<div class="gate-history-buttons">${data.runs.map((r,i)=>`<button type="button" class="btn sm" data-archive-open="${i}"><strong>${escape(r.objective)}</strong><span>${escape(r.state.replaceAll('_',' '))} · ${escape(r.actor)} · Created ${escape(r.created_at.slice(0,19).replace('T',' '))} UTC · ${escape(r.run_id.slice(0,8))}</span></button>`).join('')}</div>`:'<p>No saved investigations match these filters.</p>';
}
export function mountArchive(parent,onOpen,onClear){
 const section=document.createElement('section');section.className='agent-archive';section.innerHTML=`<h4>Investigation archive</h4><p>Find older saved work. Ten results per page, newest created first. Search matches literal objective text; English letter case is ignored. States reflect the last page load.</p><form class="agent-archive-filter"><label>Search objectives<input name="q" maxlength="120" type="search" placeholder="For example: calibration or JFK"></label><label>Investigation state<select name="state">${archiveStates.map(s=>`<option value="${s}">${s.replaceAll('_',' ')}</option>`).join('')}</select></label><button type="submit" class="btn sm">Search archive</button></form><p data-archive-status role="status"></p><div data-archive-list></div><div class="research-toolbar"><button class="btn sm" type="button" data-archive-prev disabled>Previous page</button><button class="btn sm" type="button" data-archive-next disabled>Older investigations</button><button class="btn sm" type="button" data-archive-reset disabled>Reload newest</button></div>`;
 parent.append(section);const form=section.querySelector('form'),list=section.querySelector('[data-archive-list]'),status=section.querySelector('[data-archive-status]'),prev=section.querySelector('[data-archive-prev]'),next=section.querySelector('[data-archive-next]'),reset=section.querySelector('[data-archive-reset]'),submit=form.querySelector('button');
 let user=null,epoch=0,controller=null,data=null,before=null,through=null,stack=[];
 function invalidate(){epoch++;controller?.abort();list.replaceChildren();data=null;prev.disabled=true;next.disabled=true;}
 async function load(){
  invalidate();if(!user)return;const current=epoch;controller=new AbortController();const active=controller,timer=setTimeout(()=>active.abort(),8000);submit.disabled=true;reset.disabled=true;status.textContent='Loading saved investigations…';
  try{
   const query=archiveQuery(new URLSearchParams({q:form.elements.q.value,state:form.elements.state.value,...(before===null?{}:{before}),...(through===null?{}:{through})}));
   const response=await apiFetch('/api/v1/research/agent-archive?'+query,{signal:controller.signal});if(!response.ok)throw new Error();const result=validateArchive(await response.json());if(current!==epoch)return;
   data=result;through=result.through;list.innerHTML=renderArchive(result);status.textContent=`Page ${stack.length+1} · ${result.runs.length} saved investigations shown. Newer insertions appear after Reload newest; changing states can change filter membership.`;prev.disabled=!stack.length;next.disabled=result.next_before===null;
  }catch{if(current===epoch){list.replaceChildren();data=null;status.textContent='Archive unavailable. Retry or reload newest; no saved work was changed.';}}
  finally{clearTimeout(timer);if(current===epoch){submit.disabled=!user;reset.disabled=!user;}}
 }
 function newest(){before=null;through=null;stack=[];load();}
 form.addEventListener('input',()=>{invalidate();before=null;through=null;stack=[];submit.disabled=!user;reset.disabled=!user;status.textContent=user?'Select Search archive to apply these filters.':'';});
 form.addEventListener('submit',event=>{event.preventDefault();if(user)newest();});
 next.addEventListener('click',()=>{if(!data?.next_before)return;stack.push({before,through});before=data.next_before;load();});
 prev.addEventListener('click',()=>{if(!stack.length)return;({before,through}=stack.pop());load();});
 reset.addEventListener('click',()=>{if(user)newest();});
 section.addEventListener('click',async event=>{
  const index=event.target.closest('[data-archive-open]')?.dataset.archiveOpen;if(index===undefined||!data?.runs[Number(index)]||!user)return;
  const id=data.runs[Number(index)].run_id,current=++epoch;controller?.abort();controller=new AbortController();const active=controller,timer=setTimeout(()=>active.abort(),8000);onClear();status.textContent='Opening saved investigation…';
  try{const response=await apiFetch('/api/v1/research/agent-jobs/'+encodeURIComponent(id),{signal:active.signal});if(!response.ok)throw new Error();const run=await response.json();if(current!==epoch)return;if(run.run_id!==id||run.research_only!==true||run.operational_approval!==false)throw new Error();onOpen(run);status.textContent='Saved investigation opened above. Its evidence and export retain their original scope.';}
  catch{if(current===epoch)status.textContent='Saved investigation could not be opened. Retry or reload the archive.';}
  finally{clearTimeout(timer);}
 });
 return {setSession(value){user=value;invalidate();before=null;through=null;stack=[];form.reset();submit.disabled=!user;reset.disabled=!user;status.textContent='';if(user)load();}};
}
