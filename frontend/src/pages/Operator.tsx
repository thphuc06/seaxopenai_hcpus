import { useCallback, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ApiClient } from '../api/client.ts';
import type { AdmitResult, DemoRole, Metrics, RunDetail } from '../types.ts';
import { usePoll } from '../usePoll.ts';
import { EmptyPanel, ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';
import { Dialog } from '../components/Dialog.tsx';
import { formatTime } from '../components/PassportCard.tsx';
import { traceLane } from '../trace.ts';

const OUTCOMES = ['ADMITTED', 'NOOP', 'DUPLICATE', 'REJECTED'] as const;

export function Counters({ metrics }: { metrics: Metrics }) {
  return <section className="metrics-grid" aria-label="Activity counters">
    <article className="metric-card metric-model"><span className="metric-label">Model calls</span>
      <strong data-testid="model-calls-counter">{metrics.model_calls.live + metrics.model_calls.replayed}</strong>
      <p>{metrics.model_calls.live} live · {metrics.model_calls.replayed} replayed · {metrics.model_calls.avoided} avoided</p>
    </article>
    <article className="metric-card"><span className="metric-label">Runs / jobs</span><strong>{metrics.runs} / {metrics.jobs}</strong><p>Work created by admitted events</p></article>
    <article className="metric-card"><span className="metric-label">Passport reads</span><strong>{metrics.passport_reads}</strong><p>Reads do not call a model</p></article>
    <article className="metric-card metric-events"><span className="metric-label">Event outcomes</span><dl>{OUTCOMES.map((outcome) => <div key={outcome}><dt>{outcome}</dt><dd>{metrics.events[outcome]}</dd></div>)}</dl></article>
  </section>;
}

export function TraceTable({ detail }: { detail: RunDetail }) {
  return <>
    <div className="run-summary"><span className="plain-badge" data-testid="run-status">{detail.run.status}</span><span className="plain-badge" data-testid="badge-mode">{detail.run.llm_mode}</span><span>Revision {detail.run.case_revision}</span><span>{detail.run.usage.model_calls} model calls</span>
      {detail.run.stop_reason && <p className="stop-reason">Stopped: {detail.run.stop_reason}</p>}
    </div>
    <div className="trace-legend" aria-label="Trace lanes">{(['code', 'model', 'agent', 'gap', 'web', 'other'] as const).map((lane) => <span className={`lane-chip lane-${lane}`} key={lane}>{lane}</span>)}</div>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Run trace">
      <table className="trace-table"><caption>Steps for {detail.run.id}</caption><thead><tr><th scope="col">Seq</th><th scope="col">Step</th><th scope="col">Actor</th><th scope="col">Latency</th><th scope="col">Tokens in / out</th><th scope="col">Error</th></tr></thead>
        <tbody>{detail.steps.map((step) => <tr key={step.id} className={`trace-row lane-${traceLane(step.step)}`}><td>{step.seq}</td><td><span className={`lane-chip lane-${traceLane(step.step)}`}>{step.step}</span></td><td>{step.actor}</td><td>{step.latency_ms} ms</td><td>{step.tokens_in} / {step.tokens_out}</td><td>{step.error ?? '—'}</td></tr>)}</tbody>
      </table>
    </div>
    {detail.steps.length === 0 && <p className="empty-state">No trace steps have been recorded yet.</p>}
  </>;
}

function RunInspector({ api, runId }: { api: ApiClient; runId: string }) {
  const load = useCallback((signal: AbortSignal) => api.getRun(runId, signal), [api, runId]);
  const { data, error, loading } = usePoll(load, 2_000);
  return <section className="run-inspector" aria-label="Selected run">{error && <ErrorNotice error={error} technical />}{loading && <LoadingNotice />}{data && <TraceTable detail={data} />}</section>;
}

function OperatorDashboard({ api }: { api: ApiClient }) {
  const [refresh, setRefresh] = useState(0);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const lock = useRef(false);
  const [outcome, setOutcome] = useState<AdmitResult | null>(null);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetMessage, setResetMessage] = useState(false);
  const loadCatalog = useCallback((signal: AbortSignal) => api.getEventCatalog(signal), [api]);
  const loadMetrics = useCallback((signal: AbortSignal) => api.getMetrics(signal), [api, refresh]);
  const loadRuns = useCallback((signal: AbortSignal) => api.getRuns(signal), [api, refresh]);
  const catalog = usePoll(loadCatalog, 30_000);
  const metrics = usePoll(loadMetrics, 2_000);
  const runs = usePoll(loadRuns, 2_000);
  const activeRun = runs.data?.find((run) => run.id === selectedRun)?.id ?? runs.data?.[0]?.id;

  async function act(name: string, reset = false) {
    if (lock.current) return;
    lock.current = true; setPending(name); setActionError(null); setOutcome(null); setResetMessage(false);
    try {
      if (reset) {
        await api.resetDemo(); setOutcome(null); setSelectedRun(null); setConfirmReset(false); setResetMessage(true);
      } else setOutcome(await api.fireEvent(name));
      setRefresh((value) => value + 1);
    } catch (error) { setActionError(error instanceof Error ? error : new Error('The action could not be completed.')); }
    finally { lock.current = false; setPending(null); }
  }
  return <div className="operator-dashboard">
    {metrics.error && <ErrorNotice error={metrics.error} technical />}
    {metrics.loading && <LoadingNotice />}
    {metrics.data && <Counters metrics={metrics.data} />}
    {actionError && <ErrorNotice error={actionError} technical />}
    {outcome && <section className={`event-toast outcome-${outcome.outcome.toLowerCase()}`} role="status" aria-live="polite"><strong>{outcome.outcome}</strong><p>{outcome.reason}</p><p>Stale fields: {outcome.stale_fields.length ? outcome.stale_fields.join(', ') : 'None'}</p></section>}
    {resetMessage && <p className="event-toast" role="status">Demo data reset.</p>}
    <div className="section-heading"><div><p className="eyebrow">Event catalog</p><h2>Trigger a change</h2></div><button type="button" onClick={() => { setActionError(null); setConfirmReset(true); }} disabled={pending !== null}>Reset demo</button></div>
    {catalog.error && <ErrorNotice error={catalog.error} technical />}
    {catalog.loading && <LoadingNotice />}
    {catalog.data?.length === 0 && <p className="empty-state">No events are available.</p>}
    <div className="event-grid">{catalog.data?.map((event, index) => <article className="event-card" key={event.name}>
      <span className="eyebrow">Event {String(index + 1).padStart(2, '0')}</span><h3>{event.title}</h3><p>{event.expect}</p>
      <button type="button" data-testid={`event-btn-${event.name}`} disabled={pending !== null} onClick={() => { void act(event.name); }}>{pending === event.name ? 'Sending…' : 'Run event'} <span aria-hidden="true">↗</span></button>
    </article>)}</div>
    <section className="runs-panel"><div className="section-heading"><div><p className="eyebrow">Decision activity</p><h2>Runs &amp; trace</h2></div></div>
      {runs.error && <ErrorNotice error={runs.error} technical />}{runs.loading && <LoadingNotice />}
      {runs.data?.length === 0 && <p className="empty-state">No runs yet. An admitted event can start a comparison.</p>}
      <div className="runs-layout"><div className="run-list" aria-label="Recent runs">{runs.data?.map((run) => <button type="button" className="run-item" key={run.id} aria-pressed={run.id === activeRun} onClick={() => setSelectedRun(run.id)}><strong>{run.id}</strong><span>{run.status} · {run.llm_mode}</span><small>{formatTime(run.started_at)}</small></button>)}</div>
        {activeRun && <RunInspector key={activeRun} api={api} runId={activeRun} />}
      </div>
    </section>
    {confirmReset && <Dialog title="Reset demo data?" onClose={() => { if (!lock.current) setConfirmReset(false); }}><p>This reloads the demo fixtures and clears the current demo activity.</p>
      <div className="dialog-actions"><button type="button" disabled={pending !== null} onClick={() => setConfirmReset(false)}>Cancel</button><button type="button" className="primary-button" disabled={pending !== null} onClick={() => { void act('reset', true); }}>{pending ? 'Resetting…' : 'Confirm reset'}</button></div>
      {actionError && <ErrorNotice error={actionError} technical />}
    </Dialog>}
  </div>;
}

export function Operator({ api, role, buyerPath }: { api: ApiClient; role: DemoRole; buyerPath: string | null }) {
  return <div className="operator-page">
    <EmptyPanel eyebrow="Operator workspace" title="See how a source becomes a finding."><p>Follow a listing change through comparison and into the buyer’s Passport.</p>{buyerPath && <Link className="primary-link" to={buyerPath}>Open buyer Passport <span aria-hidden="true">↗</span></Link>}</EmptyPanel>
    {role === 'OPERATOR' ? <OperatorDashboard key={role} api={api} /> : <div className="role-notice">Select the Operator role to view the event catalog. Buyer views only read stored information.</div>}
  </div>;
}
