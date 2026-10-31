import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { completedWaterfall, scopePlacement } from '../src/glassbox.ts';
import { RunGlassbox } from '../src/components/RunGlassbox.tsx';
import { reviewFindingTitle } from '../src/labels.ts';
test('completion timestamps position sequential and overlapping measured spans', () => {
  const steps = [{ id: 'a', seq: 1, t_ms: 100, latency_ms: 100 }, { id: 'b', seq: 2, t_ms: 150, latency_ms: 50 }];
  assert.deepEqual(completedWaterfall(steps).map((s) => [s.step.t_ms, s.step.latency_ms]), [[0, 100], [100, 50]]);
  assert.equal(completedWaterfall([{ ...steps[1], latency_ms: 120 }])[0].step.t_ms, 30);
  assert.equal(steps[0].t_ms, 100);
});
test('producer refs and accepted flag show grounded code placements, rejection overrides legacy flags', () => {
  const step = { step: 'scope:validate', actor: 'code', input_refs: ['unseen-passage'], output_refs: ['unseen-anchor'], detail: { accepted: true } };
  assert.deepEqual(scopePlacement(step), { passage: 'unseen-passage', anchor: 'unseen-anchor', verified: true, rejected: false });
  assert.equal(scopePlacement({ ...step, actor: 'llm' }).verified, false);
  assert.equal(scopePlacement({ ...step, output_refs: [] }).verified, false);
  assert.equal(scopePlacement({ ...step, detail: { accepted: false, verified: true } }).verified, false);
  for (const bad of [123, true, '', '   ', null]) {
    assert.equal(scopePlacement({ ...step, input_refs: [], detail: { verified: true, passage_id: bad } }).verified, false);
    assert.equal(scopePlacement({ ...step, output_refs: [], detail: { verified: true, anchor_passage_id: bad } }).verified, false);
  }
});
test('actual effect payload displays scope passages without inventing added evidence or no-change', () => {
  const detail = { run: { status: 'COMPLETED', stop_reason: null }, steps: [{ id: 's', seq: 1, step: 'agent:effect', actor: 'code', t_ms: 10, latency_ms: 0, detail: { field: 'skin_type', before: 'UNCERTAIN', after: 'SINGLE_SOURCE', passages: ['unseen-passage'] } }] };
  const html = renderToStaticMarkup(createElement(RunGlassbox, { detail }));
  assert.match(html, /Scope passages/); assert.match(html, /unseen-passage/);
  assert.ok(!html.includes('Passages added')); assert.ok(!html.includes('No change recorded'));
});
test('review titles handle unrelated claim families and fields without verdict logic', () => {
  assert.equal(reviewFindingTitle('claim:ingredient:unseen'), 'Ingredient claim');
  assert.equal(reviewFindingTitle('claim:other:unseen'), 'Claim — Phát biểu cần duyệt');
  assert.equal(reviewFindingTitle('new_field'), 'new_field');
});
