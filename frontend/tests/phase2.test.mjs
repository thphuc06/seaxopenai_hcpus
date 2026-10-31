import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createApiClient, ApiError } from '../src/api/client.ts';
import { sessionFor } from '../src/api/session.ts';
import { scenarioEvents, markedStaleWithoutModel } from '../src/lifecycle.ts';
import { TraceTable } from '../src/pages/Operator.tsx';
import { PassportCard } from '../src/components/PassportCard.tsx';
import { DecisionHistory } from '../src/pages/Reviewer.tsx';
import { createReviewTransport } from '../src/mock/reviewTransport.ts';
import { parseEvidenceJson } from '../src/components/EvidenceUpload.tsx';
import { matchingReviewEvidence } from '../src/api/reviewEvidence.ts';
import passport from '../src/mock/passport.json' with { type: 'json' };

test('review client encodes unrelated IDs, pins payload and uses current reviewer session', async () => {
  const requests = [];
  const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async (path, init) => { requests.push([path, init]); return Response.json([]); } });
  const submission = { result_id: 'other-result', case_revision: 37, decision: 'APPROVE', reason: 'Compared the stored passages' };
  await api.getReviewQueue(); await api.getCaseHistory('other/case'); await api.submitReview('other/case', submission);
  assert.deepEqual(requests.map(([path]) => path), ['/api/review/queue', '/api/cases/other%2Fcase/history', '/api/cases/other%2Fcase/reviews']);
  assert.deepEqual(JSON.parse(requests[2][1].body), submission);
  assert.deepEqual(requests.map(([, init]) => init.method), ['GET', 'GET', 'POST']);
  for (const [, init] of requests) assert.equal(new Headers(init.headers).get('X-Demo-Role'), 'REVIEWER');
});

test('review errors expose only bounded codes and numeric revision, arbitrary error bodies stay hidden', async () => {
  for (const [status, detail, expected] of [
    [409, { code: 'REVISION_CONFLICT', current_revision: 81 }, { code: 'REVISION_CONFLICT', current_revision: 81 }],
    [422, 'NO_CITATION', { code: 'NO_CITATION' }],
    [422, { code: 'FORBIDDEN_WORDING' }, { code: 'FORBIDDEN_WORDING' }],
    [422, { code: '<script>untrusted</script>', current_revision: 'untrusted' }, {}],
    [501, 'untrusted', null],
  ]) {
    const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async () => Response.json({ detail }, { status }) });
    await assert.rejects(api.submitReview('other-case', {}), (error) => {
      assert.ok(error instanceof ApiError); assert.equal(error.status, status); assert.deepEqual(error.detail, expected); assert.ok(!error.message.includes('untrusted')); return true;
    });
  }
});

test('scenario order is product-scoped, numeric and independently configurable without catalog mutation', () => {
  const event = (name, product_id = 'unseen') => ({ name, product_id, title: name, expect: `Caption ${name}` });
  const input = [event('step-12'), event('step-2'), event('step-1', 'other'), event('step-3')];
  assert.deepEqual(scenarioEvents(input, 'unseen').map((item) => item.name), ['step-2', 'step-3', 'step-12']);
  assert.deepEqual(scenarioEvents(input, 'unseen', ['step-12', 'step-2']).map((item) => item.expect), ['Caption step-12', 'Caption step-2']);
  assert.equal(input[0].name, 'step-12');
});

test('stale chip requires both recorded stale step and zero calls; PARTIAL reason remains visible', () => {
  for (const [calls, step, expected] of [[0, 'stale:mark', true], [1, 'stale:mark', false], [0, 'extract', false]]) {
    const detail = { run: { id: 'unseen-run', status: 'PARTIAL', llm_mode: 'FALLBACK', case_revision: 37, usage: { model_calls: calls }, stop_reason: 'RUN_DEADLINE' }, steps: [{ id: 'step', seq: 1, step, actor: 'code', latency_ms: 0, tokens_in: 0, tokens_out: 0, error: null }] };
    assert.equal(markedStaleWithoutModel(detail), expected);
    const html = renderToStaticMarkup(createElement(TraceTable, { detail }));
    assert.match(html, /data-testid="run-status">PARTIAL/); assert.match(html, /RUN_DEADLINE/);
    assert.equal(html.includes('marked stale — no model call'), expected);
  }
});

test('claim count is neutral and restricted to ingredient row, review history is stored state', () => {
  const preview = structuredClone(passport);
  for (const field of preview.fields) field.claims_under_review = 4;
  const html = renderToStaticMarkup(createElement(PassportCard, { passport: preview }));
  assert.equal((html.match(/4 claims under review/g) ?? []).length, 1);
  preview.fields.find((field) => field.field_key === 'key_ingredients').claims_under_review = 0;
  assert.ok(!renderToStaticMarkup(createElement(PassportCard, { passport: preview })).includes('claims under review'));
  const history = { case_id: 'other-case', case_revision: 37, results: [], events: [], requests: [], reviews: [{ id: 'stored-decision', decision: 'APPROVE', case_revision: 37, review_state: 'REVIEWED', reason: 'Compared both passages', created_at: null }] };
  const rendered = renderToStaticMarkup(createElement(DecisionHistory, { history }));
  assert.match(rendered, /review-decision-stored-decision/); assert.match(rendered, /Compared both passages/);
});

test('preview review decision persists in history and closes only its queue task; role reads remain restricted', async () => {
  let role = 'REVIEWER';
  const api = createApiClient({ getSession: () => sessionFor(role), transport: createReviewTransport() });
  const tasks = await api.getReviewQueue(); const task = tasks[0];
  const decision = await api.submitReview(task.case_id, { result_id: task.result.id, case_revision: task.case_revision, decision: 'APPROVE', reason: 'Read the evidence' });
  assert.equal((await api.getCaseHistory(task.case_id)).reviews[0].id, decision.id);
  assert.equal((await api.getReviewQueue()).length, tasks.length - 1);
  role = 'BUYER'; await assert.rejects(api.getReviewQueue(), (error) => error.status === 403);
  await assert.rejects(api.getCaseHistory(task.case_id), (error) => error.status === 403);
});

test('preview event revision invalidates a prior review and reset clears durable preview decisions', async () => {
  let role = 'REVIEWER';
  const api = createApiClient({ getSession: () => sessionFor(role), transport: createReviewTransport() });
  const task = (await api.getReviewQueue())[0]; role = 'OPERATOR';
  const catalog = await api.getEventCatalog(); await api.fireEvent(catalog[0].name); role = 'REVIEWER';
  await assert.rejects(api.submitReview(task.case_id, { result_id: task.result.id, case_revision: task.case_revision, decision: 'REJECT', reason: 'Prior revision' }), (error) => error.status === 409 && error.detail.current_revision > task.case_revision);
  assert.equal((await api.getCaseHistory(task.case_id)).reviews.length, 0);
  role = 'OPERATOR'; await api.resetDemo(); role = 'REVIEWER';
  assert.equal((await api.getReviewQueue())[0].case_revision, 1);
});

test('seller evidence preserves arbitrary source JSON and encodes case path; malformed/non-object inputs fail locally', async () => {
  for (const text of ['[]', 'null', '12', '"text"', '{broken']) assert.throws(() => parseEvidenceJson(text));
  const payload = { kind: 'SELLER_UPLOAD', passages: [{ locator: 'other#3', text: 'Contents 73 ml.' }] };
  assert.deepEqual(parseEvidenceJson(JSON.stringify(payload)), payload);
  let captured;
  const api = createApiClient({ getSession: () => sessionFor('SELLER'), transport: async (path, init) => { captured = { path, init }; return Response.json({ status: 'ADMITTED' }); } });
  await api.uploadEvidence('new/case', payload);
  assert.equal(captured.path, '/api/cases/new%2Fcase/evidence'); assert.equal(captured.init.method, 'POST');
  assert.deepEqual(JSON.parse(captured.init.body), payload); assert.equal(new Headers(captured.init.headers).get('X-Demo-Role'), 'SELLER');
});

test('review evidence requires every stored citation identity and excludes unrelated passages', () => {
  const citation = { passage_id: 'unseen-passage', source_kind: 'BRAND_PAGE', source_version: 37, locator: 'section#8', excerpt: '73 ml' };
  const passage = { ...citation, text: 'Contents 73 ml.', source_label: 'Other reference', captured_at: '2026-10-31T03:00:00Z', visibility: 'PUBLIC' };
  const unrelated = { ...passage, passage_id: 'other-passage', excerpt: 'Other text' };
  assert.deepEqual(matchingReviewEvidence([citation], { citations: [unrelated, passage], hidden_citations: 2 }), { citations: [passage], hidden_citations: 2 });
  for (const [key, value] of [['passage_id', 'changed'], ['source_kind', 'LISTING'], ['source_version', 38], ['locator', 'section#9'], ['excerpt', '74 ml']]) {
    assert.equal(matchingReviewEvidence([citation], { citations: [{ ...passage, [key]: value }], hidden_citations: 0 }), null);
  }
  assert.equal(matchingReviewEvidence([citation, unrelated], { citations: [passage], hidden_citations: 0 }), null);
  assert.equal(matchingReviewEvidence([], { citations: [passage], hidden_citations: 0 }), null);
});

test('preview seller upload checks contract shape and accepts TEXT/IMAGE JSON without provider calls', async () => {
  let role = 'REVIEWER';
  const api = createApiClient({ getSession: () => sessionFor(role), transport: createReviewTransport() });
  const task = (await api.getReviewQueue())[0]; role = 'SELLER';
  for (const payload of [
    { kind: 'SELLER_UPLOAD', passages: [{ text: '73 ml' }] },
    { idempotency_key: 'other-key', field_keys: [], content: { kind: 'TEXT', text: '73 ml' } },
    { idempotency_key: 'other-key', field_keys: ['volume'], content: { kind: 'IMAGE', media_type: 'image/gif', data_base64: 'YWJj' } },
  ]) await assert.rejects(api.uploadEvidence(task.case_id, payload), (error) => error.status === 422);
  for (const content of [{ kind: 'TEXT', text: 'Volume 73 ml.' }, { kind: 'IMAGE', media_type: 'image/jpeg', data_base64: 'YWJj' }]) {
    const result = await api.uploadEvidence(task.case_id, { idempotency_key: `other-${content.kind}`, field_keys: ['volume'], content });
    assert.equal(result.outcome, 'ADMITTED'); assert.equal(result.job_id, null);
  }
});

test('optional review evidence failures preserve tasks and continue to a matching product', async () => {
  for (const failure of ['503', 'network', 'catalog']) {
    const base = createReviewTransport(); const paths = [];
    const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async (path, init) => {
      paths.push(path);
      if (path === '/api/products') {
        if (failure === 'catalog') return new Response(null, { status: 503 });
        const products = await (await base(path, init)).json();
        return Response.json([{ ...products[0], id: 'unrelated-failing-product' }, ...products]);
      }
      if (path.startsWith('/api/products/unrelated-failing-product/')) {
        if (failure === 'network') throw new TypeError('Connection unavailable');
        return new Response(null, { status: 503 });
      }
      return base(path, init);
    } });
    const tasks = await api.getReviewQueue();
    assert.equal(tasks.length, 3);
    assert.ok(tasks.every((task) => task.evidence_error instanceof ApiError));
    const volume = tasks.find((task) => task.result.field_key === 'volume');
    if (failure === 'catalog') assert.equal(volume.evidence, null);
    else {
      assert.ok(volume.evidence?.citations.length);
      assert.ok(paths.some((path) => path.endsWith('/fields/volume/evidence') && !path.includes('unrelated-failing-product')));
    }
  }
});

test('optional evidence cancellation and authorization failure are not converted to stored-excerpt fallback', async () => {
  for (const status of [401, 403]) {
    const base = createReviewTransport();
    const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async (path, init) => path.endsWith('/evidence') ? new Response(null, { status }) : base(path, init) });
    await assert.rejects(api.getReviewQueue(), (error) => error.status === status);
  }
  const controller = new AbortController(); const base = createReviewTransport();
  const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async (path, init) => {
    if (path.endsWith('/evidence')) { controller.abort(); throw new DOMException('Request aborted', 'AbortError'); }
    return base(path, init);
  } });
  await assert.rejects(api.getReviewQueue(controller.signal), (error) => error.name === 'AbortError');
});

test('review submission lock survives form remounts and releases after completion or failure', { timeout: 2000 }, async () => {
  let release; let posts = 0;
  const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async () => { posts++; return new Promise((resolve) => { release = resolve; }); } });
  const review = { result_id: 'independent-result', case_revision: 23, decision: 'APPROVE', reason: 'Read the stored passage' };
  const first = api.submitReview('independent-case', review);
  await assert.rejects(api.submitReview('independent-case', { ...review, reason: 'Another form' }), /already being submitted/);
  assert.equal(posts, 1);
  release(Response.json({ id: 'one-decision' })); await first;
  const second = api.submitReview('independent-case', review);
  assert.equal(posts, 2); release(new Response(null, { status: 422 }));
  await assert.rejects(second, (error) => error.status === 422);
  const third = api.submitReview('independent-case', review);
  assert.equal(posts, 3); release(Response.json({ id: 'corrected-decision' })); await third;
});

test('authorization still propagates after an earlier optional evidence warning', async () => {
  for (const status of [401, 403]) {
    const base = createReviewTransport();
    const api = createApiClient({ getSession: () => sessionFor('REVIEWER'), transport: async (path, init) => {
      if (path === '/api/products') {
        const products = await (await base(path, init)).json();
        return Response.json([{ ...products[0], id: 'first-unavailable-product' }, ...products]);
      }
      if (path.startsWith('/api/products/first-unavailable-product/')) return new Response(null, { status: 503 });
      if (path.endsWith('/evidence')) return new Response(null, { status });
      return base(path, init);
    } });
    await assert.rejects(api.getReviewQueue(), (error) => error.status === status);
  }
});
