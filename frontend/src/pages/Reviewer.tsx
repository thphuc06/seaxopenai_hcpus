import { useCallback, useRef, useState } from 'react';
import { ApiError } from '../api/client.ts';
import type { ApiClient } from '../api/client.ts';
import type { CaseHistory, ReviewDecision, ReviewTask } from '../api/reviewTypes.ts';
import type { DemoRole, Verdict } from '../types.ts';
import { usePoll } from '../usePoll.ts';
import { EvidenceContent } from '../components/EvidenceDrawer.tsx';
import { EmptyPanel, ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';
import { formatTime } from '../components/PassportCard.tsx';
import { reviewFindingTitle } from '../labels.ts';
import { CaseExplorer } from '../components/CaseExplorer.tsx';
import { WebAuditDisclosure } from '../components/WebAudit.tsx';

export function DecisionHistory({ history }: { history: CaseHistory }) {
  return <>
    <section className="review-decisions" aria-label="Decisions"><h3>Decisions</h3>
      {history.reviews.length === 0 && <p>No decisions recorded yet.</p>}
      <ul>{history.reviews.map((review) => <li key={review.id} data-testid={`review-decision-${review.id}`}><strong>{review.decision}</strong> · Revision {review.case_revision} · {review.review_state}<p>{review.reason}</p><small>{formatTime(review.created_at)}</small></li>)}</ul>
    </section>
    <section aria-label="Result history"><h3>Result history</h3>
      <ul className="result-history">{history.results.map((result) => <li key={result.id}><strong>{result.field_key} · {result.verdict}</strong> · Version {result.result_version} · Revision {result.case_revision}<p>{result.superseded_by ? 'Superseded result version' : 'Stored result version'}</p><small>{formatTime(result.created_at)}</small></li>)}</ul>
    </section>
    <section aria-label="Case events"><h3>Case events</h3><ul>{history.events.map((event) => <li key={event.event_id}>{event.outcome} · {event.reason} · {formatTime(event.received_at)}</li>)}</ul></section>
    <section aria-label="Evidence requests"><h3>Evidence requests</h3><ul>{history.requests.map((request) => <li key={request.id}>{request.field_key} · {request.status}<p>{request.reason}</p></li>)}</ul></section>
  </>;
}

function ReviewCase({ api, task, onReload, onPendingChange }: { api: ApiClient; task: ReviewTask; onReload: () => void; onPendingChange: (pending: boolean) => void }) {
  const [refresh, setRefresh] = useState(0);
  const [explore, setExplore] = useState(false);
  const load = useCallback((signal: AbortSignal) => api.getCaseHistory(task.case_id, signal), [api, task.case_id, refresh]);
  const history = usePoll(load, 5_000);
  const [reason, setReason] = useState('');
  const [decision, setDecision] = useState<ReviewDecision>('APPROVE');
  const [verdict, setVerdict] = useState<Verdict>(task.result.verdict);
  const [publicText, setPublicText] = useState(task.result.public_text);
  const [citationIndices, setCitationIndices] = useState<number[]>(task.result.citations.map((_, index) => index));
  const [error, setError] = useState<Error | null>(null);
  const [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const lock = useRef(false);
  const currentRevision = error instanceof ApiError ? error.detail?.current_revision ?? history.data?.case_revision : history.data?.case_revision;
  const revisionChanged = history.data !== null && history.data.case_revision !== task.case_revision;

  async function submit() {
    if (lock.current || !reason.trim() || conflict || revisionChanged || saved) return;
    lock.current = true; setPending(true); onPendingChange(true); setError(null);
    try {
      await api.submitReview(task.case_id, {
        result_id: task.result.id, case_revision: task.case_revision, decision, reason: reason.trim(),
        ...(decision === 'OVERRIDE' ? { override: { verdict, public_text: publicText,
          citations: task.result.citations.filter((_, index) => citationIndices.includes(index)) } } : {}),
      });
      // The POST response is not a replacement for the durable decisions list.
      setSaved(true); setRefresh((value) => value + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('The decision could not be submitted.'));
      if (caught instanceof ApiError && caught.status === 409) { setConflict(true); setRefresh((value) => value + 1); }
    } finally { lock.current = false; setPending(false); onPendingChange(false); }
  }
  const result = task.result;
  return <article className="review-case" aria-label="Selected review case">
    <header><p className="eyebrow">{result.field_key.startsWith('claim:') ? 'Claim finding' : 'Field finding'} · Revision {task.case_revision}</p><h2>{reviewFindingTitle(result.field_key)}</h2>
      {result.field_key.startsWith('claim:') && <p>Claim reference: <code>{result.field_key}</code></p>}
      <dl className="review-facts"><div><dt>Verdict</dt><dd>{result.verdict}</dd></div><div><dt>Conflict locus</dt><dd>{result.conflict_locus ?? 'None'}</dd></div><div><dt>Seller attribution</dt><dd>{task.seller_attributable === undefined ? 'Not supplied' : task.seller_attributable ? 'Yes' : 'No'}</dd></div><div><dt>Review state</dt><dd>{result.review_state}</dd></div><div><dt>Case revision</dt><dd>{task.case_revision}</dd></div></dl>
      <p>Review reason: {task.reason_code}</p>
      <p>{result.public_text}</p>
    </header>
    <section className="review-evidence" aria-label="Review evidence"><h3>Evidence, side by side</h3>{task.evidence_error && <ErrorNotice error={task.evidence_error} technical />}{task.evidence ? <EvidenceContent evidence={task.evidence} withinSource={result.conflict_locus === 'WITHIN_SOURCE'} allowPrivate /> : <>
      <p className="evidence-intro">Stored cited excerpts. Full passages are unavailable until the case is linked to its product.</p>
      {result.citations.map((citation, index) => <article className="evidence-passage" key={`${citation.passage_id}:${index}`}><p className="evidence-locator">{citation.source_kind} · Version {citation.source_version} · {citation.locator}{['LISTING', 'SELLER_UPLOAD'].includes(citation.source_kind) && <span className="plain-badge">Seller text</span>}</p><blockquote>{citation.excerpt}</blockquote></article>)}
      {result.citations.length === 0 && <p>No stored citations are available.</p>}
    </>}</section>
    <form className="review-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <h3>Record a decision</h3>
      <label>Decision<select aria-label="Decision" value={decision} disabled={pending || saved} onChange={(event) => setDecision(event.target.value as ReviewDecision)}><option value="APPROVE">Approve</option><option value="OVERRIDE">Override</option><option value="REJECT">Reject</option></select></label>
      <label>Reason<textarea aria-label="Reason" data-testid="review-reason" required value={reason} disabled={pending || saved} onChange={(event) => setReason(event.target.value)} /></label>
      {decision === 'OVERRIDE' && <fieldset disabled={pending || saved}><legend>Replacement finding</legend>
        <label>Verdict<select aria-label="Verdict" value={verdict} onChange={(event) => setVerdict(event.target.value as Verdict)}>{(['CONSISTENT', 'SINGLE_SOURCE', 'CONFLICTING', 'INSUFFICIENT', 'UNCERTAIN', 'NOT_APPLICABLE'] as const).map((value) => <option key={value}>{value}</option>)}</select></label>
        <label>Public explanation<textarea aria-label="Public explanation" required value={publicText} onChange={(event) => setPublicText(event.target.value)} /></label>
        <p>Choose stored citations. The backend checks the replacement finding before publishing.</p>
        {result.citations.map((citation, index) => <label className="citation-choice" key={`${citation.passage_id}:${index}`}><input type="checkbox" checked={citationIndices.includes(index)} onChange={(event) => { const checked = event.target.checked; setCitationIndices((indices) => checked ? [...indices, index] : indices.filter((item) => item !== index)); }} />{citation.source_kind} · {citation.locator}<span className="citation-excerpt">“{citation.excerpt}”</span></label>)}
      </fieldset>}
      {(conflict || revisionChanged) && <div role="alert" className="revision-conflict">The case changed since you opened it (revision {task.case_revision} → {currentRevision !== task.case_revision ? currentRevision ?? 'unknown' : 'unknown'}). Reload.<button type="button" disabled={pending} onClick={onReload}>Reload case</button></div>}
      {error && !(error instanceof ApiError && error.status === 409) && <><ErrorNotice error={error} technical />{error instanceof ApiError && error.detail?.code && <p role="alert">{error.detail.code}</p>}</>}
      <button className="primary-button" type="submit" data-testid={decision === 'OVERRIDE' ? 'review-override' : decision === 'REJECT' ? 'review-reject' : 'review-approve'} disabled={pending || saved || !reason.trim() || conflict || revisionChanged}>{pending ? 'Submitting…' : saved ? 'Submitted' : `Submit ${decision.toLowerCase()}`}</button>
      {saved && <p role="status">Decision submitted. Check the decisions list below.</p>}
    </form>
    {history.error && <><ErrorNotice error={history.error} technical /><button type="button" onClick={() => setRefresh((value) => value + 1)}>Retry history</button></>}
    {history.loading && <LoadingNotice />}
    {history.data && <DecisionHistory history={history.data} />}
    <button type="button" aria-expanded={explore} onClick={() => setExplore((value) => !value)}>{explore ? 'Close evidence explorer' : 'Explore evidence and dependencies'}</button>
    <WebAuditDisclosure key={task.case_id} api={api} caseId={task.case_id} />
    {explore && <CaseExplorer key={task.case_id} api={api} caseId={task.case_id} />}
  </article>;
}

function ReviewWorkspace({ api }: { api: ApiClient }) {
  const [refresh, setRefresh] = useState(0);
  const load = useCallback((signal: AbortSignal) => api.getReviewQueue(signal), [api, refresh]);
  const queue = usePoll(load, 5_000);
  // Pin the opened task. Polling must never silently rebind the form to a new revision.
  const [selected, setSelected] = useState<ReviewTask | null>(null);
  const [openVersion, setOpenVersion] = useState(0);
  const [reloadError, setReloadError] = useState<Error | null>(null);
  const [reloading, setReloading] = useState(false);
  const [reviewPending, setReviewPending] = useState(false);
  const pendingReview = useRef(false);
  function pendingChanged(pending: boolean) { pendingReview.current = pending; setReviewPending(pending); }
  async function reload() {
    if (reloading || pendingReview.current) return;
    setReloading(true); setReloadError(null);
    try {
      const tasks = await api.getReviewQueue();
      const next = tasks.find((task) => task.case_id === selected?.case_id && task.result.field_key === selected.result.field_key);
      setSelected(next ?? null); setOpenVersion((value) => value + 1); setRefresh((value) => value + 1);
    } catch (error) { setReloadError(error instanceof Error ? error : new Error('The case could not be reloaded.')); }
    finally { setReloading(false); }
  }
  return <>
    {queue.error && <><ErrorNotice error={queue.error} technical /><button type="button" onClick={() => setRefresh((value) => value + 1)}>Retry queue</button></>}
    {reloadError && <ErrorNotice error={reloadError} technical />}
    {queue.loading && <LoadingNotice />}
    <div className="review-layout"><aside className="review-queue" aria-label="Review queue"><h2>Open tasks</h2>
      {queue.data?.length === 0 && <p>No open review tasks.</p>}
      {queue.data?.map((task) => <button type="button" key={task.id} data-testid={`review-task-${task.result.field_key}`} aria-pressed={selected?.id === task.id} disabled={reloading || reviewPending} onClick={() => { if (pendingReview.current) return; setSelected(task); setOpenVersion((value) => value + 1); }}><strong>{reviewFindingTitle(task.result.field_key)}</strong><span>{task.result.verdict} · Revision {task.case_revision}</span></button>)}
    </aside>{selected ? <ReviewCase key={`${selected.id}:${openVersion}`} api={api} task={selected} onPendingChange={pendingChanged} onReload={() => { void reload(); }} /> : <p className="empty-state">Select a task to inspect its evidence and revision.</p>}</div>
  </>;
}

export function Reviewer({ api, role }: { api: ApiClient; role: DemoRole }) {
  return <div className="reviewer-page"><EmptyPanel eyebrow="Reviewer workspace" title="Make room for a closer look."><p>Read both sides, check the case revision, and leave a reason for each decision.</p></EmptyPanel>
    {role === 'REVIEWER' ? <ReviewWorkspace key={role} api={api} /> : <p className="role-notice">Select the Reviewer role to open the review queue.</p>}
  </div>;
}
