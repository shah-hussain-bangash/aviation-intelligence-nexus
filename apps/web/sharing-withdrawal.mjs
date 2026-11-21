import {apiFetch} from './research-auth.mjs';
export function canWithdrawSharing(run,user){
 return !!user&&run?.state==='awaiting_review'&&run.request?.require_peer_review===true&&run.review_access?.can_withdraw===true&&/^[a-f0-9]{64}$/.test(run.report_sha256);
}
export function mountSharingWithdrawal(parent,onSaved){
 const section=document.createElement('section');section.className='sharing-withdrawal';section.hidden=true;
 section.innerHTML='<h4>Withdraw this report from peer review</h4><p>End future peer access while keeping the saved report and evidence. Previously viewed or exported copies cannot be recalled. A completed research decision cannot be withdrawn here.</p><form><label>Reason<textarea name="note" rows="2" minlength="5" maxlength="500" required placeholder="Record why peer sharing should end."></textarea></label><label class="knowledge-generation"><input type="checkbox" name="acknowledged" required> I want to withdraw this pending report from shared review.</label><button class="btn" type="submit">Withdraw sharing</button></form><button class="btn sm" type="button" data-withdraw-refresh>Refresh this report</button><p role="status" data-withdraw-status></p>';
 parent.append(section);parent.querySelector('.agent-review')?.before(section);const form=section.querySelector('form'),submit=form.querySelector('button'),refresh=section.querySelector('[data-withdraw-refresh]'),status=section.querySelector('[data-withdraw-status]');let run=null,user=null,epoch=0,controller=null,submission=null;
 function setReport(value,account){epoch++;controller?.abort();run=value;user=account;submission=null;form.reset();status.textContent='';section.hidden=!canWithdrawSharing(run,user);submit.disabled=false;refresh.disabled=false;}
 async function execute(withdraw){
  if(!run||!user||withdraw&&!canWithdrawSharing(run,user)||submit.disabled||refresh.disabled)return;
  if(withdraw&&!form.elements.acknowledged.checked)return;
  const current=epoch,id=run.run_id;controller?.abort();controller=new AbortController();const pending=controller,timer=setTimeout(()=>pending.abort(),10000);submit.disabled=true;refresh.disabled=true;status.textContent=withdraw?'Withdrawing this exact report from shared review…':'Refreshing saved report…';
  try{
   const base={run_id:id,report_sha256:run.report_sha256,note:form.elements.note.value.trim(),acknowledged:true};
   if(withdraw){const identity=JSON.stringify(base);if(!submission||submission.identity!==identity)submission={identity,key:crypto.randomUUID()};}
   const response=await apiFetch(withdraw?'/api/v1/research/agent-withdraw-sharing':'/api/v1/research/agent-jobs/'+encodeURIComponent(id),{...(withdraw?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...base,withdrawal_key:submission.key})}:{}),signal:pending.signal});
   const result=await response.json();if(current!==epoch)return;if(!response.ok||result.run_id!==id||result.research_only!==true||result.operational_approval!==false)throw new Error();
   if(withdraw&&(result.state!=='withdrawn'||result.report_sha256!==base.report_sha256||result.sharing_withdrawal?.report_sha256!==base.report_sha256||result.sharing_withdrawal?.withdrawal_key!==submission.key||result.sharing_withdrawal?.note!==base.note||result.sharing_withdrawal?.actor_id!==user.id||result.sharing_withdrawal?.acknowledged!==true))throw new Error();onSaved(result);
  }catch{if(current===epoch)status.textContent=withdraw?'Withdrawal was not confirmed. Refresh this report to check its saved state. An unchanged retry uses the same withdrawal key.':'Saved report could not be refreshed. Its current sharing state is unknown.';}
  finally{clearTimeout(timer);if(current===epoch){submit.disabled=false;refresh.disabled=false;}}
 }
 form.addEventListener('submit',event=>{event.preventDefault();execute(true);});refresh.addEventListener('click',()=>execute(false));
 return {setReport};
}
