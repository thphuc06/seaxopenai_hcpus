import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../src/App.tsx';
import { BuyerPassportView } from '../src/pages/BuyerPassport.tsx';
import { PassportCard } from '../src/components/PassportCard.tsx';
import { createApiClient } from '../src/api/client.ts';
import { mockTransport } from '../src/mock/transport.ts';
import { sessionFor } from '../src/api/session.ts';
import { FIELD_KEYS } from '../src/labels.ts';
import passport from '../src/mock/passport.json' with { type: 'json' };
import products from '../src/mock/products.json' with { type: 'json' };

const render = (element, path = '/') => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [path] }, element));

test('buyer renders all five states, stable testids, metadata and private count without private text', () => {
  const html = render(createElement(BuyerPassportView, { product: products[0], passport }));
  for (const key of FIELD_KEYS) {
    for (const prefix of ['field-row', 'field-label', 'evidence-open', 'why-open']) assert.ok(html.includes(`data-testid="${prefix}-${key}"`));
  }
  for (const label of ['Consistent', 'Conflict in source', 'Single source', 'Not verified', 'Stale']) assert.ok(html.includes(`>${label}</span>`));
  assert.match(html, /1 private document \(reviewers only\)/);
  assert.match(html, /data-testid="badge-origin">SYNTHETIC/);
  assert.match(html, /data-testid="badge-mode">FALLBACK/);
  assert.ok(html.includes(passport.disclaimer));
  assert.ok(!html.includes('Official store'));
  assert.equal((html.match(/ disabled=""/g) ?? []).length, 10);
});
test('new product text comes entirely from data; official store badge is conditional', () => {
  const product = structuredClone(products[0]);
  product.name = 'Different botanical lotion'; product.brand = 'Another brand';
  product.presentation.shop = 'Another shop'; product.presentation.official_store = true;
  const html = render(createElement(BuyerPassportView, { product, passport }));
  assert.match(html, /Different botanical lotion/); assert.match(html, /Another shop/); assert.match(html, /Official store/);
  assert.ok(!html.includes(products[0].name));
});
test('missing fields show neutral pending states instead of disappearing', () => {
  const html = render(createElement(PassportCard, { passport: { ...passport, fields: [], run_status: null } }));
  assert.equal((html.match(/data-testid="field-row-/g) ?? []).length, 5);
  assert.equal((html.match(/data-testid="field-label-[^"]+"><span[^>]*><\/span>Not checked yet<\/span>/g) ?? []).length, 5);
});
test('five routes and unknown route render their intended shell with no server or network', () => {
  const api = createApiClient({ getSession: () => sessionFor('BUYER'), transport: mockTransport });
  const routes = [
    ['/', 'See how a source becomes a finding.'], ['/buyer/unseen', 'Loading information'],
    ['/reviewer', 'Make room for a closer look.'], ['/observe', 'Follow the work behind each finding.'],
    ['/orders/receipt-example', 'A record of what you saw.'], ['/unknown', 'This page could not be found.'],
  ];
  for (const [path, heading] of routes) {
    const html = render(createElement(App, { api, role: 'BUYER', onRoleChange() {}, useMock: true, sessionError: null }), path);
    assert.ok(html.includes(heading), path);
  }
});
test('frontend-authored text follows docs/06 wording guard', () => {
  const forbidden = /genuine|authentic|fake|counterfeit|safe|certified|verified product|chính hãng|hàng giả|an toàn/iu;
  function scan(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directory);
      if (entry.isDirectory()) scan(url);
      else if (/\.(tsx?|json|svg)$/.test(entry.name)) assert.ok(!forbidden.test(readFileSync(url, 'utf8')), url.pathname);
    }
  }
  scan(new URL('../src/', import.meta.url));
});
