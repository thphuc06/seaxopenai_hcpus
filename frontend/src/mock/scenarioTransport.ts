import rawScenarios from './scenarios.json' with { type: 'json' };
import type { Transport } from '../api/client.ts';
import type { AdmitResult, EventLogItem, Metrics, RunDetail } from '../types.ts';
import { mockTransport } from './transport.ts';

export interface PreviewScenario {
  name: string; event_id: string; idempotency_key: string;
  outcome: AdmitResult['outcome']; reason: string; stale_fields: string[];
}

/** An explicitly labelled UI simulator; production always uses the server policy. */
export function createScenarioTransport({ scenarios = rawScenarios as PreviewScenario[], base = mockTransport, now = () => new Date().toISOString() }: {
  scenarios?: PreviewScenario[]; base?: Transport; now?: () => string;
} = {}): Transport {
  const seen = new Set<string>();
  const runs: RunDetail[] = [];
  const events: EventLogItem[] = [];
  let metrics: Metrics;
  function reset() {
    seen.clear(); runs.length = 0; events.length = 0;
    metrics = { events: { ADMITTED: 0, NOOP: 0, DUPLICATE: 0, REJECTED: 0 }, runs: 0, jobs: 0, model_calls: { live: 0, replayed: 0, avoided: 0 }, passport_reads: 0 };
  }
  reset();
  return async (path, init) => {
    if (init.signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
    const role = new Headers(init.headers).get('X-Demo-Role');
    const actor = new Headers(init.headers).get('X-Demo-Actor');
    if (!actor || !['BUYER', 'SELLER', 'REVIEWER', 'OPERATOR', 'SYSTEM'].includes(role ?? '')) return new Response(null, { status: 403, statusText: 'Role required' });
    const parts = path.split('/').map(decodeURIComponent);
    if (path.startsWith('/api/internal/')) {
      const runRead = init.method === 'GET' && (parts[3] === 'runs' || path === '/api/internal/events/log');
      if (role !== 'OPERATOR' && !(runRead && role === 'REVIEWER')) return new Response(null, { status: 403, statusText: 'Role not permitted' });
    }
    if (init.method === 'POST' && path === '/api/internal/demo/reset') { reset(); return Response.json({ status: 'RESET' }); }
    if (init.method === 'POST' && parts.length === 6 && parts[3] === 'demo' && parts[4] === 'fire') {
      const scenario = scenarios.find((item) => item.name === parts[5]);
      if (!scenario) return new Response(null, { status: 404, statusText: 'Preview event unavailable' });
      const duplicate = seen.has(scenario.idempotency_key);
      const outcome = duplicate ? 'DUPLICATE' : scenario.outcome;
      if (outcome !== 'REJECTED') seen.add(scenario.idempotency_key);
      const result: AdmitResult = { event_id: scenario.event_id, outcome, reason: duplicate ? 'This event key has already been handled.' : scenario.reason, job_id: null, stale_fields: outcome === 'ADMITTED' ? scenario.stale_fields : [] };
      const time = now();
      let runId: string | null = null;
      if (outcome === 'ADMITTED') {
        runId = `preview-run-${runs.length + 1}`;
        result.job_id = `preview-job-${runs.length + 1}`;
        const steps = [...(scenario.stale_fields.length ? ['stale:mark'] : []), 'pin_revision', 'extract', 'policy:volume', 'publish'];
        runs.unshift({
          run: { id: runId, case_id: 'preview-case', case_revision: runs.length + 1, trigger_event_id: result.event_id, status: 'COMPLETED', stop_reason: null, llm_mode: 'FALLBACK', started_at: time, finished_at: time, usage: { model_calls: 0, tokens_in: 0, tokens_out: 0 } },
          steps: steps.map((step, index) => ({ id: `${runId}:step:${index + 1}`, run_id: runId!, seq: index + 1, step, actor: 'code', input_refs: [], output_refs: [], latency_ms: 0, tokens_in: 0, tokens_out: 0, error: null, detail: { preview: true, mode: 'FALLBACK' }, created_at: time, t_ms: index })),
        });
        metrics.runs++; metrics.jobs++; metrics.model_calls.avoided++;
      }
      metrics.events[outcome]++;
      events.unshift({ ...result, received_at: time, run_id: runId });
      return Response.json(result);
    }
    if (init.method === 'GET') {
      if (path === '/api/internal/metrics') return Response.json(metrics);
      if (path === '/api/internal/runs') return Response.json(runs.map(({ run }) => run));
      if (path === '/api/internal/events/log') return Response.json(events);
      if (parts[3] === 'runs' && parts.length === 5) {
        const run = runs.find(({ run: item }) => item.id === parts[4]);
        return run ? Response.json(run) : new Response(null, { status: 404, statusText: 'Preview run unavailable' });
      }
    }
    const response = await base(path, init);
    if (response.ok && init.method === 'GET' && parts[2] === 'products' && parts[4] === 'passport') metrics.passport_reads++;
    return response;
  };
}

export const scenarioTransport = createScenarioTransport();
