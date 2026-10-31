import test from 'node:test';
import assert from 'node:assert/strict';
import { buyerLabel } from '../src/labels.ts';

const field = (patch = {}) => ({ field_key: 'volume', verdict: 'CONSISTENT', freshness: 'CURRENT', conflict_locus: null, label: 'ignored', public_text: '', review_state: 'AUTO_DRAFT', checked_at: null, citations: [], ...patch });

test('stale takes precedence over every run status and verdict', () => {
  for (const status of ['RUNNING', 'FAILED', 'COMPLETED', 'QUEUED', null]) {
    for (const verdict of ['CONSISTENT', 'CONFLICTING', 'INSUFFICIENT', null]) {
      assert.equal(buyerLabel(field({ freshness: 'STALE', verdict }), status).text, 'Stale');
    }
  }
});
test('running and absent results precede completed-result labels', () => {
  assert.equal(buyerLabel(field(), 'RUNNING').text, 'Updating');
  assert.equal(buyerLabel(undefined, 'RUNNING').text, 'Updating');
  assert.equal(buyerLabel(null, 'COMPLETED').text, 'Not checked yet');
  assert.equal(buyerLabel(field({ verdict: null }), 'FAILED').text, 'Not checked yet');
});
test('within-source disagreement is distinguished from seller and cross-source disagreement', () => {
  assert.deepEqual(buyerLabel(field({ verdict: 'CONFLICTING', conflict_locus: 'WITHIN_SOURCE' }), 'COMPLETED'), { text: 'Conflict in source', tone: 'source-conflict' });
  for (const locus of ['ACROSS_SOURCES', 'LISTING_VS_SOURCE', null]) {
    assert.equal(buyerLabel(field({ verdict: 'CONFLICTING', conflict_locus: locus }), 'COMPLETED').text, 'Conflicting');
  }
});
test('maps all stored verdicts, preserves results after failed or partial updates', () => {
  const expected = { CONSISTENT: 'Consistent', SINGLE_SOURCE: 'Single source', INSUFFICIENT: 'Not verified', UNCERTAIN: 'Not verified', NOT_APPLICABLE: 'Not verified' };
  for (const [verdict, label] of Object.entries(expected)) {
    assert.equal(buyerLabel(field({ verdict }), 'COMPLETED').text, label);
    assert.equal(buyerLabel(field({ verdict }), 'PARTIAL').text, label);
    if (verdict !== 'NOT_APPLICABLE') assert.equal(buyerLabel(field({ verdict }), 'FAILED').text, label);
  }
  assert.equal(buyerLabel(field({ verdict: 'NOT_APPLICABLE' }), 'FAILED').text, 'Could not update');
});
test('display mapping is independent of fixture text, field identity and server label', () => {
  for (const key of ['volume', 'responsible_company', 'skin_type']) {
    assert.equal(buyerLabel(field({ field_key: key, public_text: 'A different example', label: 'CONFLICTING' }), 'COMPLETED').text, 'Consistent');
  }
});
