import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {scopedExport} from '../apps/web/scoped-lab-contract.mjs';
import {canonical,sha256,reviewResult,assessment,buildReview,verifyReview} from '../apps/web/scoped-review-contract.mjs';
import {MAX_REVIEW_BYTES,readReviewFile,renderImportedReview} from '../apps/web/scoped-review-import.mjs';
const fixture=name=>{const f=JSON.parse(fs.readFileSync(new URL('./scoped_lab_fixtures.json',import.meta.url),'utf8')).cases[name];return scopedExport(f.response,f.request);};
const annotations=r=>({source_checked:false,question_answered:r.mode==='excerpts'?'uncertain':'not_applicable',decision_appropriate:r.mode==='excerpts'?'not_applicable':r.mode==='evidence_only'?'not_evaluable':'uncertain',claims:r.claims.map((c,i)=>({claim_index:i,citation:c.citation,supported:'uncertain',relevant:'uncertain'})),notes:''});
const completed=r=>{const a=annotations(r);a.source_checked=true;if(r.mode==='excerpts'){a.question_answered='yes';a.claims.forEach(c=>{c.supported=c.relevant='yes';});}else if(r.mode!=='evidence_only')a.decision_appropriate='yes';return a;};

test('canonical result binding is stable across key order and changes with source content',async()=>{
 assert.equal(canonical({b:2,a:[1,true,null]}),canonical({a:[1,true,null],b:2}));
 assert.equal(await sha256({a:1,b:2}),await sha256({b:2,a:1}));
 assert.notEqual(await sha256({a:1}),await sha256({a:2}));
 for(const value of [undefined,NaN,Infinity,new Date(),()=>{}])assert.throws(()=>canonical(value));
 const r=fixture('excerpts'),changed=structuredClone(r);changed.claims[0].text=changed.claims[0].quote='A different complete public source quotation.';
 assert.notEqual(await sha256(reviewResult(r)),await sha256(reviewResult(changed)));
});

test('self-review requires explicit source checking and complete claim judgments',async()=>{
 const r=fixture('excerpts'),a=annotations(r);assert.equal(assessment(r,a),'draft');
 a.source_checked=true;assert.equal(assessment(r,a),'draft');
 const good=completed(r);assert.equal(assessment(r,good),'self_reviewed');
 good.claims[0].supported='no';assert.equal(assessment(r,good),'needs_revision');
 good.claims[0].supported='yes';good.question_answered='no';assert.equal(assessment(r,good),'needs_revision');
 const bundle=await buildReview(r,completed(r),'2026-11-23T12:00:00.000Z');
 assert.equal(bundle.result.human_review_complete,false);assert.equal(bundle.independent_review,false);assert.equal(bundle.production_ready,false);
 assert.equal((await verifyReview(bundle)).assessment,'self_reviewed');
});

test('refusal reviews and unavailable generation cannot become positive answer reviews',async()=>{
 for(const name of ['coverage','conflict','paraphrase','abstained']){
  const r=fixture(name),a=completed(r);assert.equal(assessment(r,a),'self_reviewed_refusal');
  a.decision_appropriate='no';assert.equal(assessment(r,a),'refusal_needs_revision');
  a.decision_appropriate='uncertain';assert.equal(assessment(r,a),'draft');
 }
 const r=fixture('unavailable'),a=completed(r);assert.equal(assessment(r,a),'not_evaluable');
 assert.equal((await verifyReview(await buildReview(r,a))).assessment,'not_evaluable');
});

test('changed result, review judgments, claimed approval or digests are rejected',async()=>{
 const r=fixture('excerpts'),bundle=await buildReview(r,completed(r));
 for(const change of [b=>b.result.question+=' changed',b=>b.result.claims.reverse(),b=>b.annotations.notes='changed after export',b=>b.annotations.claims[0].supported='no',b=>b.assessment='self_reviewed_refusal',b=>b.result_sha256='a'.repeat(64),b=>b.review_sha256='b'.repeat(64),b=>b.independent_review=true,b=>b.result.human_review_complete=true,b=>b.production_ready=true,b=>b.created_at='yesterday']){
  const modified=structuredClone(bundle);change(modified);await assert.rejects(()=>verifyReview(modified));
 }
});

test('strict annotations bind claim indexes and prevent incomplete or unbounded review data',async()=>{
 const r=fixture('excerpts');
 for(const change of [a=>a.source_checked='true',a=>a.claims.pop(),a=>a.claims[0].claim_index=1,a=>a.claims[0].citation='unknown',a=>a.claims[0].supported='approved',a=>a.notes='x'.repeat(2001),a=>a.private_token='PRIVATE-ERROR',a=>a.decision_appropriate='yes']){
  const a=completed(r);change(a);await assert.rejects(()=>buildReview(r,a));
 }
 assert.equal((await buildReview(r,{...completed(r),notes:'<script>literal analyst note</script>'})).annotations.notes,'<script>literal analyst note</script>');
});

test('normalization excludes private response fields and verifier rejects unknown envelope fields',async()=>{
 const r=fixture('excerpts');r.private_error='PRIVATE-ERROR';r.claims[0].private_token='PRIVATE-ERROR';r.coverage.extra='PRIVATE-ERROR';
 const bundle=await buildReview(r,completed(r));assert.ok(!JSON.stringify(bundle).includes('PRIVATE-ERROR'));
 await assert.rejects(()=>verifyReview({...bundle,private_extra:'PRIVATE-ERROR'}));
 const changed=structuredClone(bundle);changed.result.private_extra='PRIVATE-ERROR';await assert.rejects(()=>verifyReview(changed));
});

test('offline verifier accepts exported reviews and rejects changes without printing query or notes',async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'ain-self-review-')),file=path.join(folder,'review.json');
 try{
  const r=fixture('excerpts'),a={...completed(r),notes:'PRIVATE-ANALYST-NOTE'};const bundle=await buildReview(r,a);fs.writeFileSync(file,JSON.stringify(bundle));
  let run=spawnSync(process.execPath,['scripts/verify-scoped-review.mjs',file],{encoding:'utf8'});assert.equal(run.status,0);assert.equal(JSON.parse(run.stdout).verified,true);assert.ok(!run.stdout.includes(r.question));assert.ok(!run.stdout.includes(a.notes));
  bundle.annotations.notes='altered';fs.writeFileSync(file,JSON.stringify(bundle));run=spawnSync(process.execPath,['scripts/verify-scoped-review.mjs',file],{encoding:'utf8'});assert.notEqual(run.status,0);assert.match(run.stderr,/could not be verified/);assert.ok(!run.stderr.includes('altered'));
 }finally{fs.unlinkSync(file);fs.rmdirSync(folder);}
});


test('local file inspector verifies a native File without changing the imported artifact',async()=>{
 const r=fixture('excerpts'),bundle=await buildReview(r,completed(r)),serialized=JSON.stringify(bundle);
 const loaded=await readReviewFile(new File([serialized],'review.json',{type:'application/json'}));
 assert.equal(loaded.verification.verified,true);assert.equal(loaded.bundle.result_sha256,bundle.result_sha256);
 assert.equal(JSON.stringify(loaded.bundle),serialized);assert.equal(loaded.bundle.result.human_review_complete,false);
 const html=await renderImportedReview(loaded.bundle);assert.match(html,/Imported file/);assert.match(html,/not a new model response/);assert.match(html,/Positive self-assessment/);
});
test('local file inspector bounds reads and rejects malformed, changed and oversized content',async()=>{
 let reads=0;await assert.rejects(()=>readReviewFile({size:MAX_REVIEW_BYTES+1,arrayBuffer:async()=>{reads++;return new ArrayBuffer(0);}}));assert.equal(reads,0);
 for(const f of [new File(['not json'],'bad.json'),new File([new Uint8Array([255])],'bad-utf8.json'),{size:2,arrayBuffer:async()=>new ArrayBuffer(1)},new File([],'empty.json')])await assert.rejects(()=>readReviewFile(f));
 const r=fixture('excerpts'),bundle=await buildReview(r,completed(r));bundle.annotations.notes='Changed after export';await assert.rejects(()=>readReviewFile(new File([JSON.stringify(bundle)],'changed.json')));
 const large=fixture('excerpts');large.question='x'.repeat(601);await assert.rejects(()=>buildReview(large,completed(large)));
});
test('import rendering escapes notes and preserves draft, negative, refusal and unavailable labels',async()=>{
 const r=fixture('excerpts'),a={...completed(r),notes:'<img src=x onerror=alert(1)> literal analyst note'};a.claims[0].relevant='no';
 const html=await renderImportedReview(await buildReview(r,a));assert.match(html,/needs revision/);assert.ok(!html.includes('<img'));assert.match(html,/&lt;img/);assert.match(html,/Analyst marked support/);
 for(const [name,want] of [['coverage','Refusal marked appropriate'],['unavailable','not evaluable']]){const result=fixture(name);assert.match(await renderImportedReview(await buildReview(result,completed(result))),new RegExp(want));}
 assert.match(await renderImportedReview(await buildReview(r,annotations(r))),/Draft self-assessment/);
 const invalid=await buildReview(r,a);invalid.result.production_ready=true;await assert.rejects(()=>renderImportedReview(invalid));
});
test('offline verifier uses the same strict UTF-8 boundary without printing file contents',async()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'ain-review-import-')),file=path.join(folder,'invalid.json');
 try{fs.writeFileSync(file,Buffer.from([255]));const run=spawnSync(process.execPath,['scripts/verify-scoped-review.mjs',file],{encoding:'utf8'});assert.notEqual(run.status,0);assert.match(run.stderr,/could not be verified/);assert.equal(run.stdout,'');}
 finally{fs.unlinkSync(file);fs.rmdirSync(folder);}
});
