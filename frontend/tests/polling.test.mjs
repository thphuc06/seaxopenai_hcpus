import test from 'node:test';
import assert from 'node:assert/strict';
import { startPolling } from '../src/polling.ts';

function harness() {
  let visible = true;
  let listener;
  let scheduled;
  return {
    environment: {
      visible: () => visible,
      subscribe(callback) { listener = callback; return () => { listener = undefined; }; },
      schedule(callback) { scheduled = callback; return () => { scheduled = undefined; }; },
    },
    change(value) { visible = value; listener?.(); },
    fire() { const callback = scheduled; scheduled = undefined; callback?.(); },
    get scheduled() { return scheduled; },
    get listening() { return Boolean(listener); },
  };
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test('polls immediately, pauses while hidden, resumes on visibility and cleans up', async () => {
  const host = harness(); const values = []; let calls = 0;
  const stop = startPolling(async () => ++calls, 100, (value) => values.push(value), assert.fail, host.environment);
  await flush(); assert.deepEqual(values, [1]);
  host.change(false); host.fire(); await flush(); assert.equal(calls, 1);
  host.change(true); await flush(); assert.deepEqual(values, [1, 2]);
  stop(); host.fire(); host.change(false); host.change(true); await flush();
  assert.equal(calls, 2); assert.equal(host.listening, false); assert.equal(host.scheduled, undefined);
});
test('hidden initial tab does not request; stale in-flight responses cannot replace resumed data', async () => {
  const host = harness(); host.change(false);
  const pending = []; const values = [];
  const stop = startPolling((signal) => { const item = deferred(); pending.push({ ...item, signal }); return item.promise; }, 100, (value) => values.push(value), assert.fail, host.environment);
  assert.equal(pending.length, 0);
  host.change(true); assert.equal(pending.length, 1);
  host.change(false); assert.equal(pending[0].signal.aborted, true);
  host.change(true); assert.equal(pending.length, 2);
  pending[1].resolve('new value'); await flush();
  pending[0].resolve('old value'); await flush();
  assert.deepEqual(values, ['new value']); stop();
});
test('requests never overlap and failures are visible and retryable', async () => {
  const host = harness(); const pending = deferred(); const errors = []; let calls = 0;
  const stop = startPolling(() => { calls++; return pending.promise; }, 100, assert.fail, (error) => errors.push(error.message), host.environment);
  host.fire(); assert.equal(calls, 1); assert.equal(host.scheduled, undefined);
  pending.reject(new Error('Offline')); await flush();
  assert.deepEqual(errors, ['Offline']); assert.equal(typeof host.scheduled, 'function'); stop();
});
test('unmount aborts the request and suppresses its late error', async () => {
  const host = harness(); const pending = deferred(); let signal;
  const stop = startPolling((active) => { signal = active; return pending.promise; }, 100, assert.fail, assert.fail, host.environment);
  stop(); assert.equal(signal.aborted, true); pending.reject(new Error('Late failure')); await flush();
  assert.equal(host.scheduled, undefined);
});
