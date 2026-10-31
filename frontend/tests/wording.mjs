import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

export function canonicalWordingPattern() {
  const guard = readFileSync(new URL('../../backend/tests/test_guards.py', import.meta.url), 'utf8');
  const pattern = guard.match(/FORBIDDEN = re\.compile\(\s*r"([^"]+)"/u)?.[1];
  assert.ok(pattern, 'Canonical backend wording guard must be available');
  return pattern;
}

export function frontendWordingGuard() {
  // Retain the original frontend substring scan. Python and JS word boundaries
  // differ for Unicode, so copying Python's boundaries would miss some terms.
  return new RegExp(canonicalWordingPattern().replaceAll('\\b', ''), 'iu');
}
