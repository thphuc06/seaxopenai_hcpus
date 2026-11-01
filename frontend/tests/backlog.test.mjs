import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { projectExplanation } from '../src/glassbox.ts';
import { ExplanationView } from '../src/components/WhyDialog.tsx';
import { readScorecard } from '../src/api/phase4Types.ts';
import { Scorecard } from '../src/pages/Observe.tsx';
import { createApiClient } from '../src/api/client.ts';

test('Buyer Why retains real quoted evidence and filters private passages defensively', () => {
  const citation = { passage_id: 'p-unseen', source_kind: 'BRAND_PAGE', source_version: 2,
    locator: 'paragraph:3', excerpt: '83 ml', text: 'Net contents: 83 ml.',
    source_label: 'Label text', captured_at: '2026-11-01T00:00:00Z', visibility: 'PUBLIC' };
  const data = projectExplanation({ audience: 'BUYER', product_id: 'other-product', field_key: 'volume',
    public_text: 'Single source.', summaries: ['Single source.', 'One independent source supports this finding.'],
    citations: [citation, { ...citation, passage_id: 'private', text: 'PRIVATE TEXT', excerpt: 'PRIVATE TEXT', visibility: 'PRIVATE' }], hidden_citations: 0 });
  const html = renderToStaticMarkup(createElement(ExplanationView, { data, expert: false }));
  assert.match(html, /<mark>83 ml<\/mark>/);
  assert.match(html, /paragraph:3/);
  assert.ok(!html.includes('PRIVATE TEXT'));
  assert.ok(!html.includes('p-unseen'));
});

test('offline scorecard shows actual mode and fallback limitations beside metrics', () => {
  const data = readScorecard({ available: true, generated_at: '2026-11-01T00:00:00Z', gold_status: 'DRAFT',
    mode: 'fallback', requested_mode: 'replay', fallback_reason: 'REPLAY_MISS', models: ['unit-model'],
    prompt_versions: ['unit-prompt'], policy_versions: ['unit-policy'], limitations: ['Diagnostic labels have not been reviewed.'],
    metrics_by_gold_status: { DRAFT: { accuracy: 0, coverage: null } } });
  const html = renderToStaticMarkup(createElement(Scorecard, { data }));
  for (const text of ['FALLBACK', 'REPLAY', 'REPLAY_MISS', 'DRAFT', 'unit-model', 'Diagnostic labels have not been reviewed.']) assert.ok(html.includes(text));
  assert.equal(data.metrics['DRAFT · accuracy'], undefined);
  assert.equal(data.metrics['metrics_by_gold_status · DRAFT · accuracy'], 0);
  assert.throws(() => readScorecard({ available: true, mode: 'guess' }), /mode/);
});

test('review queue uses explicit product identity and preserves stored provenance', async () => {
  const calls = [];
  const citation = { passage_id: 'different-passage', source_kind: 'PACKAGING_IMAGE', source_version: 3, locator: 'label:1', excerpt: '83 ml' };
  const api = createApiClient({ getSession: () => ({ role: 'REVIEWER', actor: 'reviewer' }), transport: async (path) => {
    calls.push(path);
    if (path === '/api/review/queue') return Response.json([{ id: 'task', case_id: 'case', result_id: 'result', case_revision: 7,
      reason_code: 'CHECK', product_id: 'direct-product', dataset_origin: 'SYNTHETIC', llm_mode: 'REPLAY', seller_attributable: false }]);
    if (path === '/api/cases/case/history') return Response.json({ results: [{ id: 'result', field_key: 'volume', citations: [citation] }] });
    if (path === '/api/products/direct-product/fields/volume/evidence') return Response.json({ citations: [{ ...citation, text: 'Volume: 83 ml.', visibility: 'PUBLIC' }], hidden_citations: 0 });
    throw new Error(`Unexpected route ${path}`);
  } });
  const [task] = await api.getReviewQueue();
  assert.equal(task.llm_mode, 'REPLAY'); assert.equal(task.dataset_origin, 'SYNTHETIC'); assert.equal(task.seller_attributable, false);
  assert.equal(task.evidence.citations[0].passage_id, citation.passage_id);
  assert.equal(calls.length, 3); assert.ok(!calls.includes('/api/products'));
});
