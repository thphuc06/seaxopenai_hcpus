import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { waterfall, latestBudget, explanation } from '../src/glassbox.ts';
import { ExplanationView } from '../src/components/WhyDialog.tsx';
import { RunGlassbox } from '../src/components/RunGlassbox.tsx';
import { createApiClient } from '../src/api/client.ts';
import { createReviewTransport } from '../src/mock/reviewTransport.ts';
import products from '../src/mock/products.json' with { type: 'json' };

const step = (seq, name, detail = {}, t_ms = seq * 10, latency_ms = 5) => ({ id: `s${seq}`, seq, step: name, detail, t_ms, latency_ms, actor: 'code', error: null });
const render = (type, props) => renderToStaticMarkup(createElement(type, props));
test('buyer explanation excludes all expert trail even when server over-returns', () => {
  const data = { summary: ['Compared the listed size.', 'Sources differ.', 'Attribution is not recorded.'], trail: [{ stage: 'rules', title: 'RULE_INTERNAL', facts: ['hash-secret', 'model-internal', 'private evidence'] }] };
  const buyer = render(ExplanationView, { data, expert: false });
  for (const secret of ['RULE_INTERNAL', 'hash-secret', 'model-internal', 'private evidence']) assert.ok(!buyer.includes(secret));
  assert.match(render(ExplanationView, { data, expert: true }), /hash-secret/);
  assert.equal((buyer.match(/<p>/g) ?? []).length, 3);
});
test('waterfall preserves offsets, overlap and chronological order without mutating trace', () => {
  const input = [step(2, 'extract', {}, 40, 60), step(1, 'pin_revision', {}, 10, 50)];
  assert.deepEqual(waterfall(input).map(({ left, width }) => [left, width]), [[10, 50], [40, 60]]);
  assert.equal(input[0].seq, 2);
  assert.ok(waterfall([step(1, 'empty', {}, NaN, -1)]).every((s) => Number.isFinite(s.left) && Number.isFinite(s.width)));
});
test('budget uses latest recorded value, distinguishes zero from missing and rejects malformed usage', () => {
  const steps = [step(2, 'agent:stop', { budget: { seconds: { used: 0, cap: 0 } } }), step(1, 'agent:start', { budget: { seconds: { used: 1, cap: 10 } } })];
  assert.deepEqual(latestBudget(steps, 'seconds'), { used: 0, cap: 0 });
  assert.equal(latestBudget(steps, 'tool_calls'), null);
  assert.equal(latestBudget([step(1, 'agent:start', { budget: { seconds: { used: -1, cap: 10 } } })], 'seconds'), null);
});
test('only a code validation with an anchor presents a checked placement; missing effect is not no-change', () => {
  const detail = { run: { status: 'PARTIAL', stop_reason: 'AGENT_TOOL_CALLS' }, steps: [step(1, 'agent:proposal', { verified: true, anchor_passage_id: 'anchor-x', passage_id: 'passage-x' }), step(2, 'scope:validate', { verified: true, anchor_passage_id: 'anchor-y', passage_id: 'passage-y' }), step(3, 'scope:validate', { accepted: false, reason: 'anchor missing' })] };
  const html = render(RunGlassbox, { detail });
  assert.equal((html.match(/verified by code/g) ?? []).length, 1);
  assert.match(html, /anchor-y/); assert.match(html, /needs reviewer/); assert.match(html, /not accepted/);
  assert.match(html, /No effect record available/); assert.ok(!html.includes('No change recorded.'));
  assert.match(html, /AGENT_TOOL_CALLS/);
  detail.steps.push(step(4, 'agent:effect', { before: { skin_type: 'UNCERTAIN' }, after: { skin_type: 'SINGLE_SOURCE' }, passages_added: ['passage-y'], changed: true }));
  const changed = render(RunGlassbox, { detail }); assert.match(changed, /UNCERTAIN/); assert.match(changed, /SINGLE_SOURCE/);
  detail.steps[3].detail.changed = false;
  assert.match(render(RunGlassbox, { detail }), /No change recorded/);
});
test('explain request encodes identity, is GET-only and rejects incompatible responses', async () => {
  const calls = [];
  const api = createApiClient({ getSession: () => ({ role: 'BUYER', actor: 'buyer' }), transport: async (path, init) => { calls.push([path, init]); return Response.json({ summary: ['Stored comparison.'], extra: 'discarded' }); } });
  assert.deepEqual(await api.getExplanation('id/a?', 'volume'), { summary: ['Stored comparison.'], trail: undefined });
  assert.equal(calls[0][0], '/api/products/id%2Fa%3F/fields/volume/explain'); assert.equal(calls[0][1].method, 'GET');
  for (const invalid of [null, {}, { summary: 'wrong' }, { summary: [], trail: [{}] }]) assert.throws(() => explanation(invalid));
});
test('preview explanations filter expert content by role', async () => {
  let role = 'BUYER';
  const api = createApiClient({ getSession: () => ({ role, actor: role }), transport: createReviewTransport() });
  const buyer = await api.getExplanation(products[0].id, 'volume'); assert.equal(buyer.trail, undefined);
  role = 'REVIEWER'; const expert = await api.getExplanation(products[0].id, 'volume'); assert.ok(expert.trail.length);
});
test('model-authored validation and effects never acquire code provenance in the panel', () => {
  const detail = { run: { status: 'COMPLETED', stop_reason: null }, steps: [
    { ...step(1, 'scope:validate', { verified: true, anchor_passage_id: 'untrusted-anchor' }), actor: 'llm' },
    { ...step(2, 'agent:effect', { changed: false }), actor: 'llm' },
  ] };
  const html = render(RunGlassbox, { detail });
  assert.ok(!html.includes('verified by code')); assert.ok(!html.includes('No change recorded.'));
  assert.match(html, /No effect record available/);
});
