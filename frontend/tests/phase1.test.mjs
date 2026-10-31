import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { highlightExcerpt, groupEvidence, passportPollInterval } from '../src/evidence.ts';
import { startPolling } from '../src/polling.ts';
import { traceLane } from '../src/trace.ts';
import { EvidenceContent } from '../src/components/EvidenceDrawer.tsx';
import { PassportCard } from '../src/components/PassportCard.tsx';
import { BuyerPassportView } from '../src/pages/BuyerPassport.tsx';
import { ErrorNotice } from '../src/components/Feedback.tsx';
import { Counters, TraceTable } from '../src/pages/Operator.tsx';
import { ApiError, createApiClient } from '../src/api/client.ts';
import { sessionFor } from '../src/api/session.ts';
import { createScenarioTransport } from '../src/mock/scenarioTransport.ts';
import passport from '../src/mock/passport.json' with { type: 'json' };
import products from '../src/mock/products.json' with { type: 'json' };
import { withPassportMetadata } from '../src/passportView.ts';

const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const passage = (overrides = {}) => ({ passage_id: 'unseen-a', source_kind: 'BRAND_PAGE', source_version: 3, locator: 'p2', excerpt: 'sample words', text: 'Before sample words after.', source_label: 'Source A', captured_at: '2026-10-31T03:00:00Z', visibility: 'PUBLIC', ...overrides });
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

test('excerpt matching preserves original NFC/decomposed/whitespace text and emoji offsets', () => {
  for (const [text, quote, expected] of [
    ['Before 12.5\n \t ml after', '12.5 ml', '12.5\n \t ml'],
    ['🧴 da kho\u0302 dùng thử', 'da khô', 'da kho\u0302'],
    ['A [x] (y) + z.', '[x] (y) +', '[x] (y) +'],
    ['x\u00a0y\r\nz', 'x y z', 'x\u00a0y\r\nz'],
  ]) {
    const parts = highlightExcerpt(text, quote);
    assert.equal(parts.map((part) => part.text).join(''), text);
    assert.equal(parts.filter((part) => part.highlighted).map((part) => part.text).join(''), expected);
  }
});
test('quotes are contiguous and case/punctuation sensitive; absent or empty quote has no highlight', () => {
  for (const quote of ['', ' ', 'sample Words', 'sample-words', 'sample ... after', 'missing']) {
    assert.equal(highlightExcerpt('Before sample words after.', quote).some((part) => part.highlighted), false);
  }
});
test('evidence groups only matching source metadata and retains separate versions and captures', () => {
  const input = [passage(), passage({ passage_id: 'unseen-b' }), passage({ source_version: 4 }), passage({ captured_at: '2026-11-01T03:00:00Z' }), passage({ source_label: 'Source B' })];
  assert.deepEqual(groupEvidence(input).map((items) => items.length), [2, 1, 1, 1]);
});
test('within-source evidence shows two passages, one source heading, full source text and hidden count', () => {
  const html = render(EvidenceContent, { withinSource: true, evidence: { citations: [passage(), passage({ passage_id: 'unseen-b', locator: 'p7' })], hidden_citations: 2 } });
  assert.equal((html.match(/<h3>Source A<\/h3>/g) ?? []).length, 1);
  assert.equal((html.match(/<blockquote>/g) ?? []).length, 2);
  assert.equal((html.match(/<mark>sample words<\/mark>/g) ?? []).length, 2);
  assert.match(html, /Before <mark>sample words<\/mark> after\./);
  assert.match(html, /evidence-pair/); assert.match(html, /2 private documents \(reviewers only\)/);
  assert.match(html, /not attributed to the seller/);
});
test('unmatched evidence reports an error and source markup stays escaped', () => {
  const html = render(EvidenceContent, { evidence: { citations: [passage({ text: '<img src=x onerror=alert(1)>', excerpt: 'absent' })], hidden_citations: 0 } });
  assert.match(html, /could not be located/); assert.ok(!html.includes('<img')); assert.match(html, /&lt;img/);
});
test('buyer evidence hides private text even if a transport mistakenly includes it; reviewers can view it', () => {
  const evidence = { citations: [passage(), passage({ visibility: 'PRIVATE', text: 'Internal reviewer material', excerpt: 'reviewer material', source_label: 'Private source' })], hidden_citations: 2 };
  const buyer = render(EvidenceContent, { evidence });
  assert.ok(!buyer.includes('Internal reviewer material')); assert.ok(!buyer.includes('Private source'));
  assert.match(buyer, /3 private documents/);
  const reviewer = render(EvidenceContent, { evidence, allowPrivate: true });
  assert.match(reviewer, /Internal <mark>reviewer material<\/mark>/); assert.match(reviewer, /2 private documents/);
});
test('poll interval follows stale/running/current state and failed fields do not suppress a stale check', () => {
  assert.equal(passportPollInterval(null), 10000);
  assert.equal(passportPollInterval({ fields: [], run_status: 'RUNNING' }), 2000);
  assert.equal(passportPollInterval({ fields: [{ freshness: 'STALE' }], run_status: 'FAILED' }), 2000);
  assert.equal(passportPollInterval({ fields: [{ freshness: 'CURRENT' }], run_status: 'COMPLETED' }), 10000);
});
test('adaptive polling changes the next delay without clearing data or issuing an extra request', async () => {
  const delays = []; const received = []; let fire; let calls = 0;
  const stop = startPolling(async () => ({ fields: [{ freshness: ++calls === 1 ? 'STALE' : 'CURRENT' }], run_status: 'COMPLETED' }), passportPollInterval,
    (data) => received.push(data), assert.fail, { visible: () => true, subscribe: () => () => {}, schedule: (callback, delay) => { fire = callback; delays.push(delay); return () => {}; } });
  await flush(); assert.deepEqual(delays, [2000]); assert.equal(calls, 1);
  fire(); await flush(); assert.deepEqual(delays, [2000, 10000]); assert.equal(calls, 2); assert.equal(received.length, 2); stop();
});
test('live evidence callbacks enable only evidence controls; failed update leaves stored findings visible', () => {
  const html = render(PassportCard, { passport: { ...passport, run_status: 'FAILED' }, onEvidence() {} });
  assert.equal((html.match(/ disabled=""/g) ?? []).length, 5);
  assert.match(html, /Could not update/); assert.match(html, /This says nothing about the product\./); assert.match(html, />Consistent<\/span>/); assert.match(html, />Stale<\/span>/);
});
test('null product presentation and metadata render without inventing mode or commerce details', () => {
  const wire = { ...passport, llm_mode: undefined };
  assert.equal(withPassportMetadata(wire, null), wire);
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(BuyerPassportView, { product: { ...products[0], presentation: null }, passport: wire })));
  assert.match(html, /Product image unavailable/); assert.ok(!html.includes('product-price')); assert.ok(!html.includes('badge-mode'));
});
test('buyer errors include the requested route and status without arbitrary response bodies', () => {
  const html = render(ErrorNotice, { error: new ApiError('/products/new/fields/volume/evidence', 501, 'Not Implemented') });
  assert.match(html, /\/api\/products\/new\/fields\/volume\/evidence/); assert.match(html, /501/);
});
test('trace lane vocabulary handles nested prefixes and unknown steps without hiding them', () => {
  for (const [step, lane] of Object.entries({ 'agent:web_scout': 'web', 'web:fetch': 'web', 'scope:code_prepass': 'agent', 'scope:validate': 'agent', 'agent:tool:search': 'agent', 'gap:hop2:registry': 'gap', 'extract:retry': 'model', 'canon:learn': 'model', 'claims:audit': 'model', 'publish:blocked': 'code', 'stale:mark': 'code', 'new-step': 'other' })) assert.equal(traceLane(step), lane);
});
test('preview event sequence exposes outcomes, trace, counters and zero model calls on buyer refresh', async () => {
  let role = 'OPERATOR';
  const api = createApiClient({ getSession: () => sessionFor(role), transport: createScenarioTransport() });
  const catalog = await api.getEventCatalog();
  for (const [index, expected] of ['ADMITTED', 'NOOP', 'DUPLICATE', 'REJECTED'].entries()) assert.equal((await api.fireEvent(catalog[index].name)).outcome, expected);
  const before = await api.getMetrics(); assert.equal(before.runs, 1); assert.equal(before.jobs, 1); assert.deepEqual(before.events, { ADMITTED: 1, NOOP: 1, DUPLICATE: 1, REJECTED: 1 });
  const [run] = await api.getRuns(); const detail = await api.getRun(run.id);
  assert.equal(detail.run.llm_mode, 'FALLBACK'); assert.ok(detail.steps.length > 0);
  assert.match(render(TraceTable, { detail }), /publish/); assert.match(render(Counters, { metrics: before }), /model-calls-counter/);
  role = 'BUYER'; const [product] = await api.getProducts();
  for (let index = 0; index < 3; index++) await api.getPassport(product.id);
  await assert.rejects(api.fireEvent(catalog[0].name), (error) => error.status === 403);
  role = 'OPERATOR'; const after = await api.getMetrics();
  assert.deepEqual(after.model_calls, before.model_calls); assert.equal(after.runs, before.runs); assert.equal(after.passport_reads, before.passport_reads + 3);
  await api.resetDemo(); assert.equal((await api.getRuns()).length, 0); assert.equal((await api.getMetrics()).passport_reads, 0);
});
test('preview idempotency and stale fields work for unrelated event names/keys without fixture branches', async () => {
  const scenarios = [{ name: 'unseen/event', event_id: 'new-id', idempotency_key: 'unseen-key', outcome: 'ADMITTED', reason: 'Changed source', stale_fields: ['volume'] }];
  const api = createApiClient({ getSession: () => sessionFor('OPERATOR'), transport: createScenarioTransport({ scenarios }) });
  assert.deepEqual((await api.fireEvent('unseen/event')).stale_fields, ['volume']);
  assert.equal((await api.fireEvent('unseen/event')).outcome, 'DUPLICATE'); assert.equal((await api.getRuns()).length, 1);
  await api.resetDemo(); assert.equal((await api.fireEvent('unseen/event')).outcome, 'ADMITTED');
});
