import './register.mjs';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../src/mock/passport.json' with {type:'json'};
import { createPhase4Transport } from '../src/mock/phase4Transport.ts';
import { toPassportResponse } from '../src/passportView.ts';
import { readReceipt, readWebAudit, readScorecard } from '../src/api/phase4Types.ts';
import { ReceiptView } from '../src/pages/Receipt.tsx';
import { WebAuditView } from '../src/components/WebAudit.tsx';

if (process.argv.includes('--read-contract')) {
  const input = JSON.parse(readFileSync(0, 'utf8'));
  const receipt = readReceipt(input.receipt), audit = readWebAudit(input.audit);
  process.stdout.write(JSON.stringify({receipt, audit, scorecard:readScorecard(input.scorecard),
    buyer:renderToStaticMarkup(createElement(ReceiptView, {receipt,role:'BUYER'})),
    expert:renderToStaticMarkup(createElement(WebAuditView, {audit}))}));
} else {
  const bodies = [];
  for (const product of ['unrelated-wire-product', 'other-wire-product']) {
    const snapshot = toPassportResponse(structuredClone(raw)); snapshot.product_id = product;
    const transport = createPhase4Transport(async () => Response.json(snapshot));
    const headers = {'X-Demo-Role':'OPERATOR','X-Demo-Actor':'wire-actor'};
    const creation = await (await transport('/api/orders', {method:'POST',headers,body:JSON.stringify({product_id:product})})).json();
    snapshot.fields.find(field => field.field_key === 'volume').freshness = 'STALE';
    const detail = await (await transport('/api/orders/'+creation.id, {method:'GET',headers})).json();
    const audit = await (await transport('/api/cases/wire-case/web-search', {method:'GET',headers})).json();
    const scorecard = await (await transport('/api/internal/eval/metrics', {method:'GET',headers})).json();
    bodies.push({creation,detail,audit,scorecard});
  }
  process.stdout.write(JSON.stringify(bodies));
}
