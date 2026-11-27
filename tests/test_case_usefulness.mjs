import test from 'node:test';
import assert from 'node:assert/strict';
import {template,assess,renderPacket,executionRows,renderExecution} from '../apps/web/case-usefulness-review.mjs';
const hash='a'.repeat(64);
const packet=()=>({format:'ain-case-usefulness-packet-v1',case:{title:'SYNTHETIC <script>case</script>',version:6,status:'closed'},run:{request:{objective:'SYNTHETIC <img src=x> objective'},model:{name:'qwen3:8b'},state:'needs_changes',report_sha256:hash,claims:[{text:'<script>quote</script>',citation:'T1'}]},evidence:[{id:'T1',text:'Full <img src=x> evidence'}]});
function completed(p){const v=template(p,hash);Object.assign(v,{reviewer_label:'SYNTHETIC TEST',source_checked:true,own_assessment:true,question_answered:'yes'});v.claims.forEach(c=>Object.assign(c,{supported:'yes',relevant:'yes'}));return v;}
test('review starts blank, pending and without authority',()=>{const p=packet(),v=template(p,hash);assert.equal(v.question_answered,'');assert.equal(v.claims[0].supported,'');assert.equal(v.own_assessment,false);assert.equal(assess(p,hash,v).status,'pending');assert.equal(assess(p,hash,v).human_identity_verified,false);});
test('missing acknowledgement, uncertainty and blank fields stay pending',()=>{const p=packet();for(const field of ['own_assessment','source_checked']){const v=completed(p);v[field]=false;assert.equal(assess(p,hash,v).status,'pending');}for(const value of ['','uncertain']){const v=completed(p);v.claims[0].supported=value;assert.equal(assess(p,hash,v).status,'pending');}});
test('completed declarations preserve negative ratings and never approve operations',()=>{const p=packet(),v=completed(p);assert.equal(assess(p,hash,v).status,'declared_acceptable');v.claims[0].relevant='no';const r=assess(p,hash,v);assert.equal(r.status,'declared_needs_revision');assert.equal(r.production_ready,false);assert.equal(r.operational_approval,false);});
test('changed packet, citation, claim inventory and extra authority fields are rejected',()=>{const p=packet();for(const mutate of [v=>v.packet_sha256='b'.repeat(64),v=>v.claims[0].citation='T2',v=>v.claims=[],v=>v.claims[0].supported='accepted',v=>v.approved=true]){const v=completed(p);mutate(v);assert.throws(()=>assess(p,hash,v));}});
test('source, objectives, claims and frozen JSON are escaped',()=>{const html=renderPacket(packet());assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('needs_changes'));assert.ok(html.includes('Choose your rating'));assert.ok(!html.includes('<option value="yes" selected'));});

test('execution summary distinguishes real calls, fixtures and unconfirmed optimization',()=>{
 const r={passed:true,prediction_inference_executed:true,prediction_fixture:false,retrieval_executed:false,qa_generation_executed:false,qa_fixture:true,worker_loop_executed:true,deterministic_checkpoint_fixture:false,synthetic_milp_executed:true};
 const rows=executionRows(r);assert.equal(rows.length,8);
 assert.equal(rows[0].status,'Executed in rehearsal');assert.equal(rows[1].status,'Fixture only');
 assert.equal(rows[2].status,'Fixture only');assert.equal(rows[3].status,'Executed in rehearsal');
 assert.equal(rows[4].status,'Not confirmed');assert.equal(rows[7].status,'Executed · synthetic');
 assert.equal(executionRows({...r,synthetic_milp_executed:false})[7].status,'Not confirmed');
});
test('missing, failed, contradictory and nonboolean execution records cannot claim execution',()=>{
 for(const receipt of [undefined,null,{}, {passed:false,prediction_inference_executed:true},
  {passed:true,prediction_inference_executed:'true'}, {passed:'true',prediction_inference_executed:true},
  {passed:true,prediction_inference_executed:true,prediction_fixture:true}]){
  assert.equal(executionRows(receipt)[0].status,'Not confirmed');
 }
});
test('summary shows exact revision, check count, transport and limits without rating changes',()=>{
 const p=packet();p.receipt={passed:true,source_revision:'b'.repeat(40),transport:'in_process_asgi_testclient',checks:{one:true,two:false,three:'true'}};
 const before=template(p,hash);const html=renderPacket(p);
 assert.ok(html.includes('b'.repeat(40)));assert.ok(html.includes('1 of 3 recorded checks passed'));
 assert.ok(html.includes('not a deployed browser journey'));assert.ok(html.includes('does not rate the prediction'));
 assert.deepEqual(template(p,hash),before);assert.equal(assess(p,hash,before).status,'pending');
});
test('summary rejects arbitrary revision markup and never injects receipt fields as HTML',()=>{
 const html=renderExecution({source_revision:'<img src=x>',transport:'<script>alert(1)</script>',checks:[]});
 assert.ok(html.includes('Not recorded'));assert.ok(html.includes('Transport not confirmed'));
 assert.ok(!html.includes('<img'));assert.ok(!html.includes('<script>'));
});
