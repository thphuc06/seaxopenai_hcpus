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
  return <section className="phase4-panel" data-testid="web-audit" data-snapshot-count={audit.snapshots.length}><p className="eyebrow">Source discovery</p><h3>Web search audit</h3>
    {!audit.queries.length && <p>No web search has been recorded for this case.</p>}
    {audit.queries.map((query) => <section key={query.id}><h4>Query: {query.query}</h4><p>{query.provider} · {query.mode} · {formatTime(query.created_at)}</p>{!query.results.length && <p>No results recorded for this query.</p>}<ul className="audit-results">{query.results.map((result, i) => <li key={i}>
      <div><span className="plain-badge">{result.class}</span> · {result.domain} · Score: {result.score ?? 'Not recorded'}</div>
      <a href={webUrl(result.url)} target="_blank" rel="noreferrer">{webUrl(result.url) ?? 'Link unavailable'}</a><p>{result.decision} · {result.reason}</p>
    </li>)}</ul></section>)}
    <h4>Stored snapshots</h4>{!audit.snapshots.length && <p>No page snapshots recorded.</p>}
    {audit.snapshots.map((snapshot, index) => <article className="audit-snapshot" key={index}><a href={webUrl(snapshot.url)} target="_blank" rel="noreferrer">{webUrl(snapshot.url) ?? 'Link unavailable'}</a>
      <p>{snapshot.dataset_origin} · Captured {formatTime(snapshot.captured_at)} · {snapshot.passages.length} passages · {snapshot.sha256.slice(0, 12)}</p>
      <span className="plain-badge">{snapshot.identity_verified ? 'identity verified' : 'Identity not established'}</span>
      <details><summary>Stored source text</summary>{snapshot.passages.map((passage) => <div key={passage.id}><p>{passage.locator} · Source text</p><blockquote>{passage.text}</blockquote></div>)}</details>
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
