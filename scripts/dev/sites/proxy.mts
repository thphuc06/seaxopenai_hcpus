export const BACKEND_ORIGIN = 'https://product-truth-passport-demo.onrender.com';
export type Send = (input: string, init: RequestInit & { duplex?: 'half' }) => Promise<Response>;
export interface Assets { fetch(request: Request): Promise<Response> }

const REQUEST_HEADERS = ['accept', 'content-type', 'x-demo-role', 'x-demo-actor', 'range', 'if-none-match', 'if-modified-since'];
const RESPONSE_HEADERS = ['content-type', 'content-disposition', 'etag', 'last-modified', 'content-range', 'accept-ranges', 'retry-after'];

/** Fixed upstream; the caller cannot choose another host. No write retries. */
export async function proxyApi(request: Request, send: Send = fetch): Promise<Response> {
  const source = new URL(request.url);
  const target = new URL(BACKEND_ORIGIN);
  target.pathname = source.pathname;
  target.search = source.search;
  const headers = new Headers();
  for (const key of REQUEST_HEADERS) {
    const value = request.headers.get(key);
    if (value !== null) headers.set(key, value);
  }
  try {
    const upstream = await send(target.href, {
      method: request.method,
      headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual',
      signal: AbortSignal.timeout(130_000),
      duplex: 'half',
    });
    if (upstream.status >= 300 && upstream.status < 400 && upstream.status !== 304) {
      return Response.json({ detail: 'Unexpected backend redirect' }, { status: 502 });
    }
    const responseHeaders = new Headers({ 'cache-control': 'no-store' });
    for (const key of RESPONSE_HEADERS) {
      const value = upstream.headers.get(key);
      if (value !== null) responseHeaders.set(key, value);
    }
    return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: responseHeaders });
  } catch (error) {
    const timeout = error instanceof Error && ['TimeoutError', 'AbortError'].includes(error.name);
    return Response.json({ detail: timeout ? 'Backend request timed out' : 'Backend connection unavailable' }, {
      status: timeout ? 504 : 502,
      headers: { 'cache-control': 'no-store' },
    });
  }
}

export async function serve(request: Request, assets: Assets, send: Send = fetch): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname === '/api' || url.pathname.startsWith('/api/')) return proxyApi(request, send);
  if (!['GET', 'HEAD'].includes(request.method)) {
    return new Response('Method not allowed', { status: 405, headers: { allow: 'GET, HEAD' } });
  }
  if (url.pathname.split('/').some(part => part.startsWith('.'))) return new Response('Not found', { status: 404 });
  const isAsset = url.pathname.startsWith('/assets/') || /\.[^/]+$/.test(url.pathname);
  if (isAsset) return assets.fetch(request);
  const index = new URL('/passport.html', url.origin);
  const response = await assets.fetch(new Request(index.href, { method: request.method }));
  const headers = new Headers(response.headers);
  headers.set('cache-control', 'no-cache');
  return new Response(response.body, { status: response.status, headers });
}
