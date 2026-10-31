import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import raw from '../src/mock/passport.json' with {type:'json'};
import sample from '../src/mock/phase4.json' with {type:'json'};
import { toPassportResponse } from '../src/passportView.ts';
import { receiptDiff, createPhase4Transport } from '../src/mock/phase4Transport.ts';
import { readReceipt, readScorecard, readWebAudit } from '../src/api/phase4Types.ts';
import { ReceiptView } from '../src/pages/Receipt.tsx';
import { Scorecard } from '../src/pages/Observe.tsx';
import { WebAuditView } from '../src/components/WebAudit.tsx';
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const receipt = () => {
  const snapshot = toPassportResponse(structuredClone(raw));
  return {id:'variant-order',product_id:snapshot.product_id,case_id:'variant-case',placed_at:'2026-10-31T08:00:00Z',case_revision:29,
    snapshot,snapshot_hash:'hidden-hash',chain_head:'hidden-chain',hash_valid:true,changed_since_purchase:false,diff:receiptDiff(snapshot,snapshot)};
};

test('preview receipt reads remain scoped to the purchasing actor across roles and products', async () => {
  let reads = 0;
  const transport = createPhase4Transport(async path => {
    reads += 1;
    const snapshot = toPassportResponse(structuredClone(raw));
    snapshot.product_id = decodeURIComponent(path.split('/')[3]);
    return Response.json(snapshot);
  });
  for (const [owner, product] of [['buyer-one', 'unrelated item'], ['buyer-two', 'other/item']]) {
    const headers = {'X-Demo-Role':'BUYER', 'X-Demo-Actor':owner};
    const created = await (await transport('/api/orders', {method:'POST',headers,body:JSON.stringify({product_id:product})})).json();
    for (const role of ['BUYER', 'OPERATOR']) {
      const before = reads;
      const denied = await transport('/api/orders/'+created.id, {method:'GET',headers:{'X-Demo-Role':role,'X-Demo-Actor':'other-actor'}});
      assert.equal(denied.status,404);
      assert.equal(reads,before);
      const allowed = await transport('/api/orders/'+created.id, {method:'GET',headers:{...headers,'X-Demo-Role':role}});
      assert.equal(allowed.status,200);
      const detail = await allowed.json();
      assert.equal(detail.product_id,product);
      assert.deepEqual(detail.snapshot,created.snapshot);
    }
  }
});

test('contract4 null comparisons cannot claim no change even with five diff keys', () => {
  const data = receipt();
  data.diff = data.diff.map(row => ({...row,then:null,now:null}));
  const html = render(ReceiptView,{receipt:readReceipt(data),role:'BUYER'});
  assert.match(html,/Comparison not available/);
  assert.doesNotMatch(html,/No changes since purchase|hidden-hash|hidden-chain/);
});

test('receipt status at purchase never becomes an inferred current run status', () => {
  const data = receipt(); data.snapshot.run_status = 'RUNNING';
  for (const row of data.diff) {row.then.freshness='CURRENT';row.now.freshness='CURRENT';}
  const html = render(ReceiptView,{receipt:readReceipt(data),role:'BUYER'});
  assert.match(html, /At purchase/); assert.match(html, /<td>Updating<p>/);
  assert.match(html, /Current processing status is unavailable/);
  assert.match(html, /<td>Consistent<p>/);
});

test('one missing comparison side is unknown and contradictory change summaries are rejected', () => {
  for (const side of ['then','now']) {
    const data=receipt();data.diff[0][side]=null;
    const html=render(ReceiptView,{receipt:readReceipt(data),role:'BUYER'});
    assert.match(html,/Comparison not available/);assert.doesNotMatch(html,/No changes since purchase/);
    assert.match(html,/Not recorded<\/td><\/tr>/);
  }
  const data=receipt();data.diff[0].changed=true;
  assert.throws(()=>readReceipt(data),/supported contract/);
});

test('published receipt enums and required integrity fields are validated', () => {
  const data=receipt(); data.snapshot.fields[0].verdict='NOT_APPLICABLE';
  assert.equal(readReceipt(data).snapshot.fields[0].verdict,'NOT_APPLICABLE');
  for (const mutate of [r=>delete r.hash_valid,r=>r.snapshot.run_status=['RUNNING'],r=>r.snapshot.dataset_origin='UNKNOWN',r=>r.diff[0].then.review_state='UNKNOWN']) {
    const value=receipt();mutate(value);assert.throws(()=>readReceipt(value),/supported contract/);
  }
});

test('web classes and scores follow the wire without inventing rank, title or confirm-only', () => {
  const data=structuredClone(sample.audit);
  data.queries[0].results[0].class='retailer';data.queries[0].results[0].score=0;
  data.snapshots[0].identity_verified=false;
  const html=render(WebAuditView,{audit:readWebAudit(data)});
  assert.match(html,/retailer/);assert.match(html,/Score: 0/);assert.match(html,/Identity not established/);
  assert.doesNotMatch(html,/Rank |confirm-only|REAL/);
  assert.equal((html.match(/class="audit-snapshot"/g)??[]).length,data.snapshots.length);
});

test('scorecard available false, zero, null and nested generated reports remain distinct', () => {
  assert.equal(readScorecard({available:false}),null);
  const data=readScorecard({generated_at:'2026-10-31T08:00:00Z',gold_status:'DRAFT',totals:{candidate:{accuracy:0,latency:null}}});
  assert.deepEqual(data.metrics,{'candidate · accuracy':0,'candidate · latency':null});
  const html=render(Scorecard,{data,readAt:'2026-10-31T08:03:00Z'});
  assert.match(html,/DRAFT/);assert.match(html,/\/api\/internal\/eval\/metrics/);assert.match(html,/<dd>0<\/dd>/);assert.match(html,/Not recorded/);
  assert.match(html,/retrieved/);assert.match(html,/computed/);
  const undated=render(Scorecard,{data:readScorecard({available:true,metrics:{accuracy:0}})});
  assert.match(undated,/Date not recorded/);assert.doesNotMatch(undated,/Not computed yet/);
  assert.deepEqual(readScorecard({available:true,computed_at:null,score:0}).metrics,{score:0});
});
