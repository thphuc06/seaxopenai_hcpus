import test from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, createApiClient } from '../src/api/client.ts';
import { readSession, saveRole, sessionFor } from '../src/api/session.ts';
import { mockTransport } from '../src/mock/transport.ts';

test('buyer reads use only GET, encode IDs and send role and actor on every call', async () => {
  const calls = [];
  const api = createApiClient({ getSession: () => sessionFor('BUYER'), transport: async (path, init) => { calls.push({ path, init }); return Response.json({}); } });
  await api.getProducts();
  await api.getPassport('unseen/product ?');
  await api.getEvidence('unseen/product ?', 'volume');
  assert.deepEqual(calls.map((call) => call.path), ['/api/products', '/api/products/unseen%2Fproduct%20%3F/passport', '/api/products/unseen%2Fproduct%20%3F/fields/volume/evidence']);
  for (const { init } of calls) {
    assert.equal(init.method, 'GET');
    assert.equal(init.body, undefined);
    assert.equal(init.headers['X-Demo-Role'], 'BUYER');
    assert.equal(init.headers['X-Demo-Actor'], 'demo-buyer');
  }
});
test('each S1 operator route uses its documented method and current session', async () => {
  let session = sessionFor('OPERATOR');
  const calls = [];
  const api = createApiClient({ getSession: () => session, transport: async (path, init) => { calls.push({ path, init }); return Response.json({}); } });
  await api.getEventCatalog(); await api.getEventLog(); await api.getRuns(); await api.getRun('run / new'); await api.getMetrics();
  await api.submitEvent({ event_id: 'test-event' }); await api.fireEvent('an event/variant'); await api.resetDemo();
  assert.deepEqual(calls.map(({ path, init }) => `${init.method} ${path}`), [
    'GET /api/internal/events/catalog', 'GET /api/internal/events/log', 'GET /api/internal/runs', 'GET /api/internal/runs/run%20%2F%20new', 'GET /api/internal/metrics',
    'POST /api/internal/events', 'POST /api/internal/demo/fire/an%20event%2Fvariant', 'POST /api/internal/demo/reset',
  ]);
  assert.equal(JSON.parse(calls[5].init.body).event_id, 'test-event');
  session = sessionFor('REVIEWER');
  await api.getProducts();
  assert.equal(calls.at(-1).init.headers['X-Demo-Role'], 'REVIEWER');
});
test('HTTP, network and malformed response errors surface without backend text injection', async () => {
  const options = { getSession: () => sessionFor('BUYER') };
  const http = createApiClient({ ...options, transport: async () => new Response('arbitrary server content', { status: 503, statusText: 'Service Unavailable' }) });
  await assert.rejects(http.getProducts(), (error) => error instanceof ApiError && error.status === 503 && error.path === '/products' && !error.message.includes('arbitrary server content'));
  const network = createApiClient({ ...options, transport: async () => { throw new TypeError('Disconnected'); } });
  await assert.rejects(network.getProducts(), (error) => error instanceof ApiError && error.status === 0);
  const malformed = createApiClient({ ...options, transport: async () => new Response('not json') });
  await assert.rejects(malformed.getProducts(), /response could not be read/);
});
test('role persists, unknown values cannot become SYSTEM, storage failures propagate', () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  assert.equal(readSession(storage).role, 'BUYER');
  saveRole(storage, 'SELLER'); assert.deepEqual(readSession(storage), sessionFor('SELLER'));
  storage.setItem('ptp.demo-role', 'SYSTEM'); assert.equal(readSession(storage).role, 'BUYER');
  assert.throws(() => saveRole({ setItem() { throw new Error('Storage unavailable'); } }, 'OPERATOR'), /Storage unavailable/);
});
test('mock reads are isolated, unknown products fail, and mutations are unavailable', async () => {
  const api = createApiClient({ getSession: () => sessionFor('BUYER'), transport: mockTransport });
  const [product] = await api.getProducts();
  const first = await api.getPassport(product.id);
  first.fields[0].public_text = 'Changed by consumer';
  const second = await api.getPassport(product.id);
  assert.notEqual(second.fields[0].public_text, first.fields[0].public_text);
  await assert.rejects(api.getPassport('a-new-product'), (error) => error.status === 404);
  await assert.rejects(api.fireEvent('new-event'), (error) => error.status === 501);
  for (const field of second.fields) {
    const evidence = await api.getEvidence(product.id, field.field_key);
    assert.ok(evidence.citations.every((citation) => citation.visibility === 'PUBLIC' && citation.text.includes(citation.excerpt)));
  }
});
