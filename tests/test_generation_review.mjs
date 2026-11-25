import test from 'node:test';
import assert from 'node:assert/strict';
import { reviewSnapshot, reviewProgress } from '../apps/web/generation-review.mjs';

const fixture = () => ({ format: 'ain-generation-annotations-v1', packet_sha256: 'a'.repeat(64), reviewer_label: '', cases: [
  { id: 'generated', case_sha256: 'b'.repeat(64), source_checked: false, question_answered: 'uncertain', abstention_appropriate: 'not_applicable', claims: [{ claim_index: 0, citation: 'passage', supported: 'uncertain', relevant: 'uncertain' }], notes: '' },
  { id: 'abstained', case_sha256: 'c'.repeat(64), source_checked: false, question_answered: 'not_applicable', abstention_appropriate: 'uncertain', claims: [], notes: '' },
  { id: 'unavailable', case_sha256: 'd'.repeat(64), source_checked: false, question_answered: 'not_evaluable', abstention_appropriate: 'not_evaluable', claims: [], notes: '' }
] });

test('initial review never invents judgments and retains unavailable outcomes', () => {
  const initial = fixture();
  assert.deepEqual(reviewSnapshot(initial, structuredClone(initial)), initial);
  assert.deepEqual(reviewProgress(initial), { pending: 2, declared: 0, not_evaluable: 1 });
});

test('download snapshot preserves exact bindings and leaves input unchanged', () => {
  const initial = fixture(), edits = structuredClone(initial);
  edits.reviewer_label = 'SYNTHETIC UI TEST';
  edits.cases[0].source_checked = true; edits.cases[0].question_answered = 'no';
  edits.cases[0].claims[0].supported = 'no'; edits.cases[0].claims[0].relevant = 'yes';
  edits.cases[0].notes = '<img src=x onerror=alert(1)> is literal reviewer text';
  edits.packet_sha256 = 'forged'; edits.extra = 'ignored';
  const snapshot = reviewSnapshot(initial, edits);
  assert.equal(snapshot.packet_sha256, initial.packet_sha256);
  assert.equal(snapshot.extra, undefined);
  assert.equal(snapshot.cases[0].notes, edits.cases[0].notes);
  assert.deepEqual(reviewProgress(snapshot), { pending: 1, declared: 1, not_evaluable: 1 });
  assert.deepEqual(initial, fixture());
});

test('incomplete source and reviewer gates cannot appear declared', () => {
  const data = fixture();
  data.cases[1].abstention_appropriate = 'yes'; data.cases[1].source_checked = true;
  assert.equal(reviewProgress(data).declared, 0);
  data.reviewer_label = 'SYNTHETIC TEST'; assert.equal(reviewProgress(data).declared, 1);
  data.cases[1].source_checked = false; assert.equal(reviewProgress(data).declared, 0);
});

test('changed claims, skipped cases, invalid ratings and unavailable credit are rejected', () => {
  const mutations = [x => x.cases.pop(), x => { x.cases[0].id = 'other'; }, x => { x.cases[0].claims = []; },
    x => { x.cases[0].claims[0].citation = 'other'; }, x => { x.cases[0].claims[0].claim_index = true; },
    x => { x.cases[0].claims[0].supported = 'correct'; }, x => { x.cases[0].notes = 'x'.repeat(2001); },
    x => { x.cases[0].source_checked = 1; }, x => { x.cases[2].abstention_appropriate = 'yes'; },
    x => { x.reviewer_label = 'x'.repeat(81); }];
  for (const mutate of mutations) {
    const initial = fixture(), edits = structuredClone(initial); mutate(edits);
    assert.throws(() => reviewSnapshot(initial, edits));
  }
});
