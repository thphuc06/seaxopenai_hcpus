import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import type { ApiClient } from '../api/client.ts';
import type { DemoRole } from '../types.ts';
import { usePoll } from '../usePoll.ts';
import { EmptyPanel, ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';

function EventCatalog({ api }: { api: ApiClient }) {
  const load = useCallback((signal: AbortSignal) => api.getEventCatalog(signal), [api]);
  const { data, error, loading } = usePoll(load, 30_000);
  return <>
    {error && <ErrorNotice error={error} technical />}
    {loading && <LoadingNotice />}
    <div className="event-grid">{data?.map((event, index) => <article className="event-card" key={event.name}>
      <span className="eyebrow">Event {String(index + 1).padStart(2, '0')}</span>
      <h2>{event.title}</h2><p>{event.expect}</p>
      <button type="button" data-testid={`event-btn-${event.name}`} disabled>Run event <span aria-hidden="true">↗</span></button>
    </article>)}</div>
    <p className="shell-note">Event execution will be connected in the next phase.</p>
  </>;
}

export function Operator({ api, role, buyerPath }: { api: ApiClient; role: DemoRole; buyerPath: string | null }) {
  return <>
    <EmptyPanel eyebrow="Operator workspace" title="See how a source becomes a finding.">
      <p>Follow a listing change through comparison and into the buyer’s Passport.</p>
      {buyerPath && <Link className="primary-link" to={buyerPath}>Open buyer Passport <span aria-hidden="true">↗</span></Link>}
    </EmptyPanel>
    {role === 'OPERATOR' ? <EventCatalog api={api} /> : <div className="role-notice">Select the Operator role to view the event catalog. Buyer views only read stored information.</div>}
  </>;
}
