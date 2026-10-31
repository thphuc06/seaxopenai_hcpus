import { useEffect, useState } from 'react';
import type { ApiClient } from '../api/client.ts';
import type { EvidenceResponse, FieldKey } from '../types.ts';
import { FIELD_TITLES } from '../labels.ts';
import { groupEvidence, highlightExcerpt } from '../evidence.ts';
import { formatTime } from './PassportCard.tsx';
import { Dialog } from './Dialog.tsx';
import { ErrorNotice, LoadingNotice } from './Feedback.tsx';

const SOURCE_TITLES = {
  LISTING: 'Listing', BRAND_PAGE: 'Brand page', NOTIFICATION_DOC: 'Notification document',
  PACKAGING_IMAGE: 'Packaging image', SELLER_UPLOAD: 'Seller document', REGISTRY_RECORD: 'Registry record', WEB_PAGE: 'Web page',
};

export function sourceDomain(value?: string): string | null {
  if (!value) return null;
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.hostname : null; }
  catch { return null; }
}

export function EvidenceContent({ evidence, withinSource = false, allowPrivate = false }: { evidence: EvidenceResponse; withinSource?: boolean; allowPrivate?: boolean }) {
  const visible = evidence.citations.filter((citation) => allowPrivate || citation.visibility === 'PUBLIC');
  const hidden = evidence.hidden_citations + evidence.citations.length - visible.length;
  return <>
    <p className="evidence-intro">Read the stored source passage. The highlighted words are the cited excerpt.</p>
    {groupEvidence(visible).map((group, index) => {
      const first = group[0];
      if (!first) return null;
      return <section className="evidence-group" key={index}>
        <header><h3>{first.source_label}</h3><p>{SOURCE_TITLES[first.source_kind]} · Version {first.source_version} · Captured {formatTime(first.captured_at)}{sourceDomain(first.source_url) && <> · {sourceDomain(first.source_url)}</>}</p>
          {withinSource && group.length > 1 && <p className="source-conflict-note">These passages are from the same source snapshot. This is not attributed to the seller.</p>}
        </header>
        <div className={withinSource && group.length > 1 ? 'evidence-pair' : 'evidence-stack'}>
          {group.map((citation, citationIndex) => {
            const parts = highlightExcerpt(citation.text, citation.excerpt);
            return <article className="evidence-passage" key={`${citation.passage_id}:${citationIndex}`}>
              <p className="evidence-locator">Location: {citation.locator}{(citation.source_kind === 'LISTING' || citation.source_kind === 'SELLER_UPLOAD') && <span className="plain-badge">Seller text</span>}{citation.visibility === 'PRIVATE' && <span className="plain-badge">Reviewer document</span>}</p>
              <blockquote>{parts.map((part, partIndex) => part.highlighted ? <mark key={partIndex}>{part.text}</mark> : part.text)}</blockquote>
              {!parts.some((part) => part.highlighted) && <p className="evidence-mismatch" role="alert">The cited excerpt could not be located in this passage.</p>}
            </article>;
          })}
        </div>
      </section>;
    })}
    {visible.length === 0 && <p className="empty-state">No source passage is available for this field.</p>}
    {hidden > 0 && <p className="private-note">+{hidden} private {hidden === 1 ? 'document' : 'documents'} (reviewers only)</p>}
  </>;
}

export function EvidenceDrawer({ api, productId, fieldKey, withinSource, onClose, allowPrivate = false }: {
  api: ApiClient; productId: string; fieldKey: FieldKey; withinSource: boolean; onClose: () => void; allowPrivate?: boolean;
}) {
  const [state, setState] = useState<{ data: EvidenceResponse | null; error: Error | null }>({ data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ data: null, error: null });
    api.getEvidence(productId, fieldKey, controller.signal).then(
      (data) => { if (!controller.signal.aborted) setState({ data, error: null }); },
      (error: unknown) => { if (!controller.signal.aborted) setState({ data: null, error: error instanceof Error ? error : new Error('Could not load evidence.') }); },
    );
    return () => controller.abort();
  }, [api, productId, fieldKey, attempt]);
  return <Dialog title={`${FIELD_TITLES[fieldKey]} · Evidence`} onClose={onClose} wide>
    {!state.data && !state.error && <LoadingNotice />}
    {state.error && <><ErrorNotice error={state.error} /><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry evidence</button></>}
    {state.data && <EvidenceContent evidence={state.data} withinSource={withinSource} allowPrivate={allowPrivate} />}
  </Dialog>;
}
