import { useCallback } from 'react';
import type { ApiClient } from '../api/client.ts';
import type { DemoRole, ObservabilityResponse } from '../types.ts';
import type { ScorecardResponse } from '../api/phase4Types.ts';
import { usePoll } from '../usePoll.ts';
import { EmptyPanel, ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';
import { formatTime } from '../components/PassportCard.tsx';

function Counts({ title, values }: { title: string; values: Record<string, number | null> }) {
  return <article className="phase4-panel"><h3>{title}</h3><dl className="count-list">{Object.entries(values).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value ?? 'Not recorded'}</dd></div>)}</dl>{!Object.keys(values).length && <p>No entries recorded.</p>}</article>;
}
export function ObserveView({ data, readAt }: { data: ObservabilityResponse; readAt: string }) {
  return <><p>Source: /api/internal/observability · retrieved {formatTime(readAt)}</p><div className="observe-grid">
    <Counts title="Verdict mix" values={data.verdicts} /><Counts title="Model calls" values={data.model_calls} />
    <Counts title="Publication and review" values={{ 'Published': data.publish_passed, 'Blocked': data.publish_blocked, 'Review queue': data.review_queue_size, 'Oldest review age (seconds)': data.oldest_review_age_s ?? null }} />
    <Counts title="Agent stop reasons" values={data.agent_stops} /><Counts title="Gap stop reasons" values={data.gap_stops} /><Counts title="Vocabulary" values={data.vocabulary} />
    {Object.entries(data.calls_by_step).map(([step, counts]) => <Counts key={step} title={`Calls · ${step}`} values={counts} />)}
  </div></>;
}
export function Scorecard({ data }: { data: ScorecardResponse | null }) {
  return <section className="phase4-panel"><h2>Offline scorecard</h2>{!data || !data.computed_at ? <p>Not computed yet</p> : <><p>Source: /api/internal/eval/metrics · computed {formatTime(data.computed_at)} · {data.status}</p><Counts title="Evaluation metrics" values={data.metrics} /></>}</section>;
}
function ExpertObserve({ api }: { api: ApiClient }) {
  const load = useCallback(async (signal: AbortSignal) => ({ value: await api.getObservability(signal), readAt: new Date().toISOString() }), [api]);
  const loadScore = useCallback((signal: AbortSignal) => api.getScorecard(signal), [api]);
  const state = usePoll(load, 10_000), score = usePoll(loadScore, 30_000);
  return <><h1>Observe</h1><p>Stored activity and offline evaluation.</p>{state.loading && <LoadingNotice />}{state.error && <ErrorNotice error={state.error} technical />}
    {state.data && <ObserveView data={state.data.value} readAt={state.data.readAt} />}{score.error ? <ErrorNotice error={score.error} technical /> : score.loading ? <LoadingNotice /> : <Scorecard data={score.data} />}</>;
}
export function Observe({ api, role }: { api: ApiClient; role: DemoRole }) {
  return role === 'OPERATOR' || role === 'REVIEWER' ? <ExpertObserve key={role} api={api} /> : <EmptyPanel eyebrow="Observability" title="Follow the work behind each finding."><p>Expert access required. Choose the Operator or Reviewer role to inspect activity.</p></EmptyPanel>;
}
