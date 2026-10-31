import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ErrorNotice, LoadingNotice } from '../src/components/Feedback.tsx';
import { ApiError } from '../src/api/client.ts';

test('plain failures distinguish unavailable, missing, access and network without protocol details', () => {
  for (const path of ['/orders/unrelated%2Freceipt', '/products/another/fields/skin_type/evidence']) {
    for (const [status, text] of [[501, 'not available yet'], [404, 'could not be found'], [401, 'current access'], [403, 'current access'], [0, 'Check your connection'], [500, 'reload the page']]) {
      const html = renderToStaticMarkup(createElement(ErrorNotice, { error: new ApiError(path, status, 'PRIVATE_DETAIL'), plain: true }));
      assert.match(html, /role="alert"/);
      assert.ok(html.includes(text));
      assert.ok(!html.includes(path));
      assert.doesNotMatch(html, /PRIVATE_DETAIL|Response status|\/api|501|404|403|401|500/);
    }
  }
});

test('expert diagnostics remain available and plain copy never echoes unknown error text', () => {
  const error = new ApiError('/internal/eval/metrics', 501, 'Not Implemented');
  const expert = renderToStaticMarkup(createElement(ErrorNotice, { error, technical: true }));
  assert.match(expert, /501/);
  assert.match(expert, /\/internal\/eval\/metrics/);
  const plain = renderToStaticMarkup(createElement(ErrorNotice, { error: new Error('PRIVATE_DETAIL'), plain: true }));
  assert.doesNotMatch(plain, /PRIVATE_DETAIL/);
  assert.match(plain, /reload the page/);
  assert.match(renderToStaticMarkup(createElement(LoadingNotice)), /role="status"/);
});
