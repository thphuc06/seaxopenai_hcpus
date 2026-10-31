import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../src/mock/passport.json' with {type:'json'};
import sample from '../src/mock/phase4.json' with {type:'json'};
import { toPassportResponse } from '../src/passportView.ts';
import { readReceipt, readWebAudit } from '../src/api/phase4Types.ts';
import { receiptDiff, createPhase4Transport } from '../src/mock/phase4Transport.ts';
import { ReceiptView } from '../src/pages/Receipt.tsx';
import { WebAuditView } from '../src/components/WebAudit.tsx';
import { Scorecard } from '../src/pages/Observe.tsx';
import { createApiClient } from '../src/api/client.ts';
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const receipt = () => {
  const snapshot = toPassportResponse(structuredClone(raw));
  return {id:'unrelated-order', product_id:snapshot.product_id, created_at:'2026-10-31T07:00:00Z', snapshot, snapshot_hash:null, chain_head:null, changed_since_purchase:false, diff:receiptDiff(snapshot,snapshot)};
};

test('an empty comparison is not a no-change finding and still shows five saved fields', () => {
  const value = receipt(); value.diff = [];
  const html = render(ReceiptView, {receipt:value, role:'BUYER'});
  assert.match(html, /Comparison not available/);
  assert.doesNotMatch(html, /No changes since purchase/);
  assert.equal((html.match(/data-testid="field-row-/g) ?? []).length, 5);
});

test('at-purchase labels retain the frozen run state for unrelated current fields', () => {
  const value = receipt();
  value.snapshot.run_status = 'RUNNING';
  for (const key of ['volume', 'key_ingredients']) {
    const row = value.diff.find(item => item.field_key === key);
    row.before.freshness = 'CURRENT';
    value.diff = [row];
    const html = render(ReceiptView, {receipt:value, role:'BUYER'});
    assert.match(html, /<td>Updating<p>/);
    value.diff = receipt().diff;
  }
});

test('receipt boundary rejects malformed findings, unknown or duplicate diff keys and mixed identities', () => {
  const mutations = [
    r => { delete r.snapshot.fields[0].verdict; },
    r => { r.snapshot.fields[0].verdict = ['CONSISTENT']; },
    r => { r.diff[0].field_key = 'claim:unexpected:private'; },
    r => { r.diff.push(structuredClone(r.diff[0])); },
    r => { r.diff[0].after.field_key = 'skin_type'; },
    r => { r.snapshot.product_id = 'different-product'; },
  ];
  for (const mutate of mutations) { const value = receipt(); mutate(value); assert.throws(() => readReceipt(value), /supported contract/); }
});

test('web audit rejects unknown classifications and negative/non-finite counts', () => {
  for (const mutate of [a => {a.searches[0].results[0].classification='UNRECOGNIZED';}, a => {a.searches[0].results[0].rank=-1;}, a => {a.snapshots[0].passages_count=NaN;}]) {
    const value = structuredClone(sample.audit); mutate(value); assert.throws(() => readWebAudit(value), /supported contract/);
  }
});

test('preview field comparison ignores JSON property order without changing snapshots', () => {
  const before = toPassportResponse(structuredClone(raw));
  const after = structuredClone(before);
  after.fields = after.fields.map(field => Object.fromEntries(Object.entries(field).reverse()));
  assert.equal(receiptDiff(before, after).some(row => row.changed), false);
  after.fields.find(field => field.field_key === 'volume').public_text = 'Different stored volume text.';
  assert.deepEqual(receiptDiff(before, after).filter(row => row.changed).map(row => row.field_key), ['volume']);
  assert.notEqual(before.fields[0].public_text, after.fields[0].public_text);
});

test('preview expert requests require actor and recognized role', async () => {
  const transport = createPhase4Transport();
  const response = await transport('/api/internal/observability', {method:'GET', headers:{'X-Demo-Role':'OPERATOR'}});
  assert.equal(response.status, 403);
});

test('audit empty state and missing/computed scorecards keep distinct meanings', () => {
  assert.match(render(WebAuditView, {audit:{case_id:'case',searches:[],snapshots:[]}}), /No web search/);
  assert.match(render(Scorecard, {data:null}), /Not computed yet/);
  const html = render(Scorecard, {data:{computed_at:'2026-10-31T07:00:00Z',status:'DRAFT',metrics:{accuracy:0}}});
  assert.match(html, /\/api\/internal\/eval\/metrics/); assert.match(html, /computed/); assert.match(html, /DRAFT/); assert.match(html, /<dd>0<\/dd>/);
});

test('S4 reads and purchase reject responses belonging to another requested resource', async () => {
  const api = createApiClient({getSession: () => ({role:'REVIEWER',actor:'reviewer-unrelated'}), transport: async path => Response.json(path.includes('web-search') ? sample.audit : receipt())});
  await assert.rejects(() => api.getOrder('other-order'), /requested order/);
  await assert.rejects(() => api.getWebAudit('other-case'), /requested case/);
  await assert.rejects(() => api.createOrder('other-product'), /different product/);
});

test('receipt projection drops unexpected expert/display extras and audit explains empty query results', () => {
  const value = receipt();
  value.snapshot.llm_mode = {internal:'invalid-object'};
  value.snapshot.web_sources = {internal:'invalid-object'};
  value.snapshot.chain_head = 'hidden-chain-marker';
  const parsed = readReceipt(value);
  assert.equal(parsed.snapshot.chain_head, undefined);
  const html = render(ReceiptView, {receipt:parsed,role:'BUYER'});
  assert.doesNotMatch(html, /hidden-chain-marker|invalid-object/);
  assert.equal((html.match(/data-testid="field-row-/g) ?? []).length, 5);
  assert.match(render(WebAuditView, {audit:{case_id:'c',searches:[{query:'unrelated query',results:[]}],snapshots:[]}}), /No results recorded for this query/);
});
