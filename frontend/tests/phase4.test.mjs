import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../src/mock/passport.json' with { type: 'json' };
import sample from '../src/mock/phase4.json' with { type: 'json' };
import { toPassportResponse } from '../src/passportView.ts';
import { createApiClient, ApiError } from '../src/api/client.ts';
import { createPhase4Transport } from '../src/mock/phase4Transport.ts';
import { ReceiptView } from '../src/pages/Receipt.tsx';
import { Observe, ObserveView, Scorecard } from '../src/pages/Observe.tsx';
import { WebAuditView, webUrl } from '../src/components/WebAudit.tsx';
import { PassportCard } from '../src/components/PassportCard.tsx';
import { sourceDomain } from '../src/components/EvidenceDrawer.tsx';
import { groupEvidence } from '../src/evidence.ts';
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const session = { role: 'BUYER', actor: 'unrelated-buyer' };

test('different web URLs never share a source heading despite matching capture metadata', () => {
  const citation = { source_kind:'WEB_PAGE', source_label:'Source page', source_version:1, captured_at:'2026-10-31T07:00:00Z' };
  assert.equal(groupEvidence([{...citation, source_url:'https://a.example/page'}, {...citation, source_url:'https://b.example/page'}]).length, 2);
});

test('unsupported successful S4 payloads become visible errors instead of rendering crashes', async () => {
  const api = createApiClient({getSession: () => session, transport: async () => Response.json({unexpected: []})});
  await assert.rejects(() => api.getOrder('new-order'), /supported contract/);
  await assert.rejects(() => api.getWebAudit('new-case'), /supported contract/);
  await assert.rejects(() => api.getScorecard(), /supported contract/);
});

test('web provenance counts unique public REAL versions only; absent metadata makes no count claim', () => {
  const source = { source_version_id: 'unrelated-version', url: 'https://example.org/item', captured_at: '2026-10-31T07:00:00Z', origin: 'REAL', visibility: 'PUBLIC' };
  assert.doesNotMatch(render(PassportCard, { passport: raw }), /REAL web sources/);
  const html = render(PassportCard, { passport: { ...raw, web_sources: [source, source, {...source, source_version_id:'private', visibility:'PRIVATE'}, {...source, source_version_id:'synthetic', origin:'SYNTHETIC'}] } });
  assert.match(html, /1 REAL web sources/);
  assert.equal(sourceDomain('https://other.example:443/item'), 'other.example');
  assert.equal(sourceDomain('javascript:alert(1)'), null);
});

for (const fieldKey of ['notification_number', 'skin_type']) {
  test(`receipt freezes purchase and detects later ${fieldKey} change`, async () => {
    let current = toPassportResponse(structuredClone(raw));
    const transport = createPhase4Transport(async () => Response.json(current), () => '2026-10-31T07:00:00Z');
    const api = createApiClient({ getSession: () => session, transport });
    const order = await api.createOrder(current.product_id);
    const frozen = structuredClone(order.snapshot);
    current.fields.find(f => f.field_key === fieldKey).freshness = 'STALE';
    const receipt = await api.getOrder(order.id);
    assert.deepEqual(receipt.snapshot, frozen);
    assert.equal(receipt.changed_since_purchase, true);
    assert.deepEqual(receipt.diff.filter(row => row.changed).map(row => row.field_key), [fieldKey]);
    assert.equal((await api.getOrder(order.id)).id, order.id);
    assert.equal((await api.getOrder(order.id)).diff.filter(row => row.changed).length, 1);
    const html = render(ReceiptView, {receipt, role:'BUYER'});
    const table = html.slice(html.indexOf('<tbody>'), html.indexOf('</tbody>'));
    const title = fieldKey === 'skin_type' ? 'Skin type' : 'Notification number';
    assert.ok(table.indexOf(title) < table.indexOf('Volume'));
    assert.equal(receipt.diff[0].field_key, 'volume');
  });
}
test('receipt buyer redacts integrity references; expert can inspect them', () => {
  const snapshot = toPassportResponse(raw);
  const receipt = { id: 'order-independent', placed_at: '2026-10-31T07:00:00Z', snapshot, snapshot_hash: 'secret-hash-marker', chain_head: 'chain-marker', diff: [], changed_since_purchase: false };
  for (const role of ['BUYER', 'SELLER']) {
    const html = render(ReceiptView, { receipt, role });
    assert.doesNotMatch(html, /secret-hash-marker|chain-marker/);
    assert.match(html, /data-testid="receipt-diff"/);
  }
  assert.match(render(ReceiptView, { receipt, role: 'REVIEWER' }), /secret-hash-marker/);
});
test('expert-only reads reject buyer and seller in preview', async () => {
  const transport = createPhase4Transport();
  for (const role of ['BUYER', 'SELLER']) {
    const api = createApiClient({ getSession: () => ({ ...session, role }), transport });
    for (const read of [() => api.getWebAudit('different-case'), () => api.getScorecard(), () => api.getObservability()]) await assert.rejects(read, error => error instanceof ApiError && error.status === 403);
    assert.match(render(Observe, { api, role }), /Expert access required/);
  }
});
test('web audit shows query, decisions and snapshots without executable links', () => {
  const audit = structuredClone(sample.audit);
  audit.queries[0].results[0].url = 'javascript:alert(1)';
  const html = render(WebAuditView, { audit });
  assert.match(html, /data-testid="web-audit"/);
  assert.match(html, /lead only/); assert.match(html, /skipped/); assert.match(html, /Captured/);
  assert.doesNotMatch(html, /javascript:/);
  assert.equal(webUrl('data:text/html,hello'), undefined);
  assert.equal(webUrl('https://unrelated.example/page'), 'https://unrelated.example/page');
});
test('observability retains actual counts, zero and absent scorecard', () => {
  const data = structuredClone(sample.observability);
  data.model_calls.replayed = 17; data.review_queue_size = 3;
  data.calls_by_step = { extract: { live: 0, replayed: 17, avoided: 2 } };
  const html = render(ObserveView, { data, readAt: '2026-10-31T07:00:00Z' });
  assert.match(html, /17/); assert.match(html, /Calls · extract/); assert.match(html, /\/api\/internal\/observability/);
  assert.match(render(Scorecard, { data: null }), /Not computed yet/);
});
test('receipt and web requests encode IDs, preserve headers, and surface 501', async () => {
  const calls = [];
  const api = createApiClient({ getSession: () => session, transport: async (path, init) => { calls.push({path, init}); return new Response(null, {status:501}); } });
  await assert.rejects(() => api.createOrder('product/x'), error => error.status === 501);
  await assert.rejects(() => api.getOrder('order/x'), error => error.status === 501);
  await assert.rejects(() => api.getWebAudit('case/x'), error => error.status === 501);
  assert.equal(calls[0].init.body, JSON.stringify({product_id:'product/x'}));
  assert.equal(calls[1].path, '/api/orders/order%2Fx');
  assert.equal(calls[2].path, '/api/cases/case%2Fx/web-search');
  assert.equal(calls[2].init.method, 'GET');
  assert.equal(calls[0].init.headers['X-Demo-Role'], 'BUYER');
});
