import test from 'node:test';
import assert from 'node:assert/strict';
import { proxyApi, serve, BACKEND_ORIGIN } from './proxy.mts';

test('GET preserves encoded path/query and strips platform credentials', async () => {
  let calls = 0;
  const request = new Request('https://site.example/api/products/unseen%20id/passport?as_of=old', { headers: {
    'X-Demo-Role': 'BUYER', 'X-Demo-Actor': 'visitor', Cookie: 'site-login=private',
    Authorization: 'Bearer private', 'OAI-Authenticated-User-Email': 'private@example.test',
  } });
  const response = await proxyApi(request, async (url, init) => {
    calls++;
    assert.equal(url, BACKEND_ORIGIN + '/api/products/unseen%20id/passport?as_of=old');
    assert.equal(init.method, 'GET');
    assert.equal(init.body, undefined);
    assert.equal(init.headers.get('x-demo-role'), 'BUYER');
    assert.equal(init.headers.get('x-demo-actor'), 'visitor');
    assert.equal(init.headers.get('cookie'), null);
    assert.equal(init.headers.get('authorization'), null);
    assert.equal(init.headers.get('oai-authenticated-user-email'), null);
    return Response.json({ result: 'stored' }, { headers: { 'set-cookie': 'backend=private' } });
  });
  assert.equal(calls, 1);
  assert.equal(response.headers.get('set-cookie'), null);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.deepEqual(await response.json(), { result: 'stored' });
});

test('POST body and revision error pass through exactly once', async () => {
  const body = JSON.stringify({ result_id: 'unseen-result', case_revision: 7 });
  let calls = 0;
  const response = await proxyApi(new Request('https://site.example/api/cases/random/reviews', {
    method: 'POST', body, headers: { 'content-type': 'application/json', 'x-demo-role': 'REVIEWER' },
  }), async (_url, init) => {
    calls++;
    assert.equal(init.method, 'POST');
    assert.equal(await new Response(init.body).text(), body);
    assert.equal(init.headers.get('x-demo-role'), 'REVIEWER');
    return Response.json({ detail: 'REVISION_CONFLICT' }, { status: 409 });
  });
  assert.equal(calls, 1);
  assert.equal(response.status, 409);
  assert.equal((await response.json()).detail, 'REVISION_CONFLICT');
});

for (const status of [403, 404, 422, 500]) {
  test('upstream error ' + status + ' remains visible', async () => {
    const response = await proxyApi(new Request('https://site.example/api/unknown'),
      async () => new Response('detail', { status }));
    assert.equal(response.status, status);
    assert.equal(await response.text(), 'detail');
  });
}

test('redirects are not followed and unknown network failures are reported', async () => {
  const request = new Request('https://site.example/api/unknown');
  const redirect = await proxyApi(request, async (_url, init) => {
    assert.equal(init.redirect, 'manual');
    return new Response(null, { status: 302, headers: { location: 'https://unrelated.example' } });
  });
  assert.equal(redirect.status, 502);
  let calls = 0;
  const failed = await proxyApi(request, async () => { calls++; throw new TypeError('network'); });
  assert.equal(failed.status, 502);
  assert.equal(calls, 1);
  const timeout = await proxyApi(request, async () => { throw new DOMException('deadline', 'TimeoutError'); });
  assert.equal(timeout.status, 504);
});

test('frontend SPA routes use assets without contacting backend', async () => {
  for (const pathname of ['/', '/buyer/unseen', '/reviewer', '/observe']) {
    const response = await serve(new Request('https://site.example' + pathname), {
      fetch: async request => {
        assert.equal(new URL(request.url).pathname, '/passport.html');
        return new Response('<html>frontend</html>', { headers: { 'content-type': 'text/html' } });
      },
    }, async () => { throw new Error('frontend must not call backend'); });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-cache');
  }
});

test('missing assets stay missing and UI writes are rejected', async () => {
  const assets = { fetch: async () => new Response('missing', { status: 404 }) };
  for (const pathname of ['/assets/missing.js', '/image.png']) {
    assert.equal((await serve(new Request('https://site.example' + pathname), assets)).status, 404);
  }
  assert.equal((await serve(new Request('https://site.example/.env'), assets)).status, 404);
  assert.equal((await serve(new Request('https://site.example/buyer', { method: 'POST' }), assets)).status, 405);
});
