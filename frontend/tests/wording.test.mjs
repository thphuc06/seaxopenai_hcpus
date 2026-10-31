import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalWordingPattern, frontendWordingGuard } from './wording.mjs';

test('frontend scan retains substring and Unicode coverage for every canonical term', () => {
  const terms = canonicalWordingPattern().match(/\(\?:([^)]*)\)/u)?.[1].split('|');
  assert.ok(terms?.length);
  const guard = frontendWordingGuard();
  for (const term of terms) {
    assert.ok(guard.test(term), term);
    assert.ok(guard.test(`prefix${term}suffix`), `embedded ${term}`);
    assert.ok(guard.test(`“${term.toUpperCase()}”`), `case variant ${term}`);
  }
});
