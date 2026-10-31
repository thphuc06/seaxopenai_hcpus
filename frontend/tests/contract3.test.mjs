import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { projectExplanation } from '../src/glassbox.ts';
import { ExplanationView } from '../src/components/WhyDialog.tsx';
import { DependencyGraph, SearchResults } from '../src/components/CaseExplorer.tsx';
import { createApiClient } from '../src/api/client.ts';
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
test('contract3 expert projection covers each stage and cannot render in buyer view', () => {
  const data = projectExplanation({ audience: 'EXPERT', product_id: 'other', field_key: 'volume', result_id: 'result-x', trigger_event_id: 'event-x', sources: [{ source_version_id: 'sv-x', sha256: '0123456789abcdef', captured_at: '2026-10-31', origin: 'REAL' }], claims: [{ source_version_id: 'sv-x', passage_id: 'passage-x', quote: '<script>source text</script>', extractor: 'extractor-x', prompt_version: 'version-x', mapped_by: 'CODE' }], rules: [{ rule: 'rule-x', outcome: 'included', detail: 'source match' }], publish_checks: ['locator matched'], chain_head: 'fedcba9876543210', reviews: [] });
  assert.equal(data.trail.length, 7);
  const expert = render(ExplanationView, { data, expert: true });
  for (const value of ['event-x', 'REAL', '0123456789ab', 'extractor-x', 'rule-x', 'locator matched', 'fedcba987654']) assert.ok(expert.includes(value));
  assert.ok(!expert.includes('<script>'));
  const buyer = render(ExplanationView, { data, expert: false });
  assert.ok(!buyer.includes('extractor-x')); assert.ok(!buyer.includes('source text'));
});
test('contract3 buyer projection discards over-returned expert fields', () => {
  const data = projectExplanation({ audience: 'BUYER', public_text: 'Stored text.', summaries: ['One.', 'Two.'], rules: ['internal'], sources: ['private'] });
  assert.deepEqual(data, { summary: ['One.', 'Two.'] });
});
test('search routes preserve special characters, mode and read-only method; 501 surfaces', async () => {
  let requested;
  const api = createApiClient({ getSession: () => ({ role: 'REVIEWER', actor: 'r' }), transport: async (path, init) => { requested = [path, init]; return new Response(null, { status: 501 }); } });
  await assert.rejects(api.searchEvidence('case/a', 'oily & dry?', 'bm25'), /501/);
  assert.equal(requested[1].method, 'GET');
  const url = new URL(requested[0], 'http://test'); assert.equal(url.searchParams.get('q'), 'oily & dry?'); assert.equal(url.searchParams.get('mode'), 'bm25');
  assert.ok(url.pathname.includes('case%2Fa'));
});
test('graph highlights revoked source and stale target; search preserves source text and stage ranks', () => {
  const graph = { nodes: [{ id: 'a', kind: 'source', label: 'Source A', status: 'REVOKED' }, { id: 'b', kind: 'field', label: 'Volume', status: 'STALE' }], edges: [{ source: 'a', target: 'b', relation: 'depends_on' }] };
  assert.match(render(DependencyGraph, { graph }), /dependency-stale/);
  const result = { hits: [{ passage_id: 'p', text: 'Dry skin <tag>', source_label: 'Source B' }], stages: { bm25: [{ passage_id: 'p', rank: 2 }], dense: [], fused: [] } };
  const html = render(SearchResults, { result, query: 'Dry skin' });
  assert.match(html, /<mark>Dry skin<\/mark>/); assert.match(html, /&lt;tag&gt;/); assert.match(html, /rank 2/); assert.match(html, /no answer generated/);
});
