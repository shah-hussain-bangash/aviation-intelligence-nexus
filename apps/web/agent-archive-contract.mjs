export const archiveStates=['all','queued','running','awaiting_review','reviewed','needs_changes','failed','interrupted','cancelled'];
const cursor=value=>typeof value==='string'&&/^(0|[1-9][0-9]{0,18})$/.test(value)&&BigInt(value)<=9223372036854775807n;
export function archiveQuery(parameters){
 const entries=[...parameters],keys=entries.map(([key])=>key);
 if(new Set(keys).size!==keys.length||keys.some(key=>!['q','state','before','through'].includes(key)))throw new Error('Invalid archive parameters');
 const q=(parameters.get('q')||'').trim(),state=parameters.get('state')||'all',before=parameters.get('before'),through=parameters.get('through');
 if([...q].length>120||!archiveStates.includes(state)||[before,through].some(value=>value!==null&&!cursor(value))||(before!==null&&(through===null||BigInt(before)>BigInt(through))))throw new Error('Invalid archive query');
 return new URLSearchParams({q,state,...(before===null?{}:{before}),...(through===null?{}:{through})});
}
export function validateArchive(data){
 if(data.research_only!==true||data.operational_approval!==false||data.page_size!==10||data.order!=='newest_created_first'||data.search_scope!=='objective_literal_ascii_case_insensitive'||!cursor(data.through)||!Array.isArray(data.runs)||data.runs.length>10||(data.next_before!==null&&(!cursor(data.next_before)||BigInt(data.next_before)>BigInt(data.through)||data.runs.length!==10)))throw new Error('Invalid archive scope');
 const ids=new Set();
 for(const row of data.runs){
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(row.run_id)||ids.has(row.run_id)||!archiveStates.slice(1).includes(row.state)||typeof row.actor!=='string'||typeof row.objective!=='string'||row.objective.length>600||![row.created_at,row.updated_at].every(value=>typeof value==='string'&&Number.isFinite(Date.parse(value))))throw new Error('Invalid archived run');
  ids.add(row.run_id);
 }
 return data;
}
