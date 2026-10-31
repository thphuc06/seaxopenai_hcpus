import { useCallback, useState } from 'react';
import type { ApiClient } from '../api/client.ts';
import type { WebAuditResponse } from '../api/phase4Types.ts';
import { usePoll } from '../usePoll.ts';
import { ErrorNotice, LoadingNotice } from './Feedback.tsx';
import { formatTime } from './PassportCard.tsx';

export function webUrl(value: string): string | undefined {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined; }
  catch { return undefined; }
}
export function WebAuditView({ audit }: { audit: WebAuditResponse }) {
  return <section className="phase4-panel" data-testid="web-audit"><p className="eyebrow">Source discovery</p><h3>Web search audit</h3>
    {!audit.searches.length && <p>No web search has been recorded for this case.</p>}
    {audit.searches.map((search, index) => <section key={index}><h4>Query: {search.query}</h4>{!search.results.length && <p>No results recorded for this query.</p>}<ol className="audit-results">{search.results.map((result, i) => <li key={i}>
      <div><span className="plain-badge">{result.classification}</span> Rank {result.rank} · {result.domain}</div>
      <a href={webUrl(result.url)} target="_blank" rel="noreferrer">{result.title}</a><p>{result.decision} · {result.reason}</p>
    </li>)}</ol></section>)}
    <h4>Stored snapshots</h4>{!audit.snapshots.length && <p>No page snapshots recorded.</p>}
    {audit.snapshots.map((snapshot, index) => <article className="audit-snapshot" key={index}><a href={webUrl(snapshot.url)} target="_blank" rel="noreferrer">{snapshot.url}</a>
      <p>Captured {formatTime(snapshot.captured_at)} · {snapshot.passages_count} passages · {snapshot.sha256.slice(0, 12)}</p>
      <span className="plain-badge">{snapshot.confirm_only ? 'confirm-only' : snapshot.identity_verified ? 'identity verified' : 'Identity not established'}</span>
    </article>)}
  </section>;
}
// Mounted only inside expert role boundaries; fetching never launches a search.
export function WebAudit({ api, caseId }: { api: ApiClient; caseId: string }) {
  const load = useCallback((signal: AbortSignal) => api.getWebAudit(caseId, signal), [api, caseId]);
  const state = usePoll(load, 10_000);
  return <>{state.loading && <LoadingNotice />}{state.error && <ErrorNotice error={state.error} technical />}{state.data && <WebAuditView audit={state.data} />}</>;
}

export function WebAuditDisclosure({ api, caseId }: { api: ApiClient; caseId: string }) {
  const [open, setOpen] = useState(false);
  return <section><button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{open ? 'Close web search audit' : 'Open web search audit'}</button>{open && <WebAudit api={api} caseId={caseId} />}</section>;
}
