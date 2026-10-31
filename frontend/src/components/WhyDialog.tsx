import { useCallback } from 'react';
import type { ApiClient } from '../api/client.ts';
import type { DemoRole, FieldKey } from '../types.ts';
import type { Explanation } from '../glassbox.ts';
import { FIELD_TITLES } from '../labels.ts';
import { usePoll } from '../usePoll.ts';
import { Dialog } from './Dialog.tsx';
import { ErrorNotice, LoadingNotice } from './Feedback.tsx';

export function ExplanationView({ data, expert }: { data: Explanation; expert: boolean }) {
  return <div className="explanation-view">
    {data.summary.slice(0, 3).map((sentence, index) => <p key={index}>{sentence}</p>)}
    {!data.summary.length && !expert && <p>No explanation has been recorded yet.</p>}
    {expert && <><h3>Decision trail</h3><ol className="decision-trail">{data.trail?.map((item, index) => <li key={index}><span className="eyebrow">{item.stage}</span><h4>{item.title}</h4>{item.facts.map((fact, i) => <p key={i}>{fact}</p>)}</li>)}</ol>{!data.trail?.length && <p>The detailed trail is unavailable.</p>}</>}
  </div>;
}
export function WhyDialog({ api, productId, fieldKey, role, onClose }: { api: ApiClient; productId: string; fieldKey: FieldKey; role: DemoRole; onClose: () => void }) {
  const load = useCallback((signal: AbortSignal) => api.getExplanation(productId, fieldKey, signal), [api, productId, fieldKey]);
  const { data, error, loading } = usePoll(load, 30_000);
  const expert = role === 'REVIEWER' || role === 'OPERATOR';
  return <Dialog title={`Why? · ${FIELD_TITLES[fieldKey]}`} onClose={onClose} wide={expert}>
    {loading && <LoadingNotice />}{error && <ErrorNotice error={error} technical={expert} plain={!expert} />}
    {data && <ExplanationView data={data} expert={expert} />}
  </Dialog>;
}
