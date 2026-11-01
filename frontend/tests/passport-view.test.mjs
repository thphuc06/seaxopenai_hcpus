import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { toPassportResponse, withPassportMetadata } from '../src/passportView.ts';
import { createApiClient } from '../src/api/client.ts';
import { sessionFor } from '../src/api/session.ts';
import { mockTransport } from '../src/mock/transport.ts';
import { BuyerPassportView } from '../src/pages/BuyerPassport.tsx';
import preview from '../src/mock/passport.json' with { type: 'json' };

test('wire projection omits display metadata and preserves findings for unrelated input', () => {
  const variant = structuredClone(preview);
  variant.product_id = 'unseen-lotion';
  variant.fields[0].field_key = 'another_stored_field';
  variant.fields[0].public_text = 'A different source statement';
  variant.fields[0].hidden_citations = 8;
  variant.fields[0].citations[0].ui_note = 'presentation only';
  const original = structuredClone(variant);
  const response = toPassportResponse(variant);
  assert.equal(response.product_id, 'unseen-lotion');
  assert.equal(response.fields[0].field_key, 'another_stored_field');
  assert.equal(response.fields[0].public_text, variant.fields[0].public_text);
  assert.equal(response.fields[0].verdict, variant.fields[0].verdict);
  assert.ok(!('llm_mode' in response));
  assert.ok(response.fields.every((field) => !('hidden_citations' in field)));
  assert.ok(!('ui_note' in response.fields[0].citations[0]));
  assert.deepEqual(variant, original);
});
test('pending display rows are rejected by the wire projection', () => {
  const pending = structuredClone(preview);
  pending.fields[0].verdict = null;
  assert.throws(() => toPassportResponse(pending), /pending display row/);
});

test('pending claims come from metadata and only annotate the ingredients row', () => {
  for (const count of [0, 1, 7]) {
    const passport = structuredClone(preview);
    const before = structuredClone(passport);
    const result = withPassportMetadata(passport, { llm_mode: 'REPLAY', hidden_citations: {}, pending_claims: count });
    assert.equal(result.fields.find((field) => field.field_key === 'key_ingredients').claims_under_review, count);
    assert.ok(result.fields.filter((field) => field.field_key !== 'key_ingredients').every((field) => field.claims_under_review === undefined));
    assert.deepEqual(passport, before);
  }
});
test('separate metadata preserves mode and hidden count in the buyer view', async () => {
  const api = createApiClient({ getSession: () => sessionFor('BUYER'), transport: mockTransport });
  const [product] = await api.getProducts();
  const passport = await api.getPassport(product.id);
  const html = renderToStaticMarkup(createElement(MemoryRouter, null,
    createElement(BuyerPassportView, { product, passport })));
  assert.match(html, /data-testid="badge-mode">FALLBACK/);
  assert.match(html, /1 private document \(reviewers only\)/);
  assert.ok(!('llm_mode' in passport));
  const before = structuredClone(passport);
  const result = withPassportMetadata(passport, { llm_mode: 'REPLAY', hidden_citations: { volume: 3 } });
  assert.equal(result.llm_mode, 'REPLAY');
  assert.equal(result.fields.find((field) => field.field_key === 'volume').hidden_citations, 3);
  assert.deepEqual(passport, before);
  for (let i = 0; i < passport.fields.length; i++) assert.equal(result.fields[i].verdict, passport.fields[i].verdict);
});
