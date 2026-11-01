import { useEffect, useState } from 'react';
import { buyerLabel, FIELD_KEYS, FIELD_TITLES } from '../labels.ts';
import type { FieldKey, PassportView, PassportViewField, RunStatus } from '../types.ts';
import { StatusBadge } from './StatusBadge.tsx';

export function formatTime(value: string | null): string {
  if (!value) return 'Not checked yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Check time unavailable';
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(date) + ' ICT';
}

export function FieldRow({ fieldKey, field, runStatus, index, onEvidence, onWhy }: {
  fieldKey: FieldKey; field: PassportViewField; runStatus: RunStatus | null; index: number; onEvidence?: (key: FieldKey) => void; onWhy?: (key: FieldKey) => void;
}) {
  const label = buyerLabel(field, runStatus);
  const [previousLabel, setPreviousLabel] = useState(label.text);
  const [pulse, setPulse] = useState({ count: 0, tone: '' });
  useEffect(() => {
    if (previousLabel !== label.text) {
      setPreviousLabel(label.text);
      setPulse((previous) => ({ count: previous.count + 1, tone: label.tone === 'stale' ? 'stale' : 'change' }));
    }
  }, [label.text, label.tone, previousLabel]);
  return <article className="field-row" data-testid={`field-row-${fieldKey}`}>
    {pulse.count > 0 && <span key={pulse.count} className={`field-ripple ripple-${pulse.tone}`} aria-hidden="true" />}
    <span className="field-index" aria-hidden="true">0{index + 1}</span>
    <div className="field-content">
      <div className="field-heading"><h3>{FIELD_TITLES[fieldKey]}</h3><StatusBadge field={field} runStatus={runStatus} /></div>
      <p className="field-description">{field.public_text}</p>
      {fieldKey === 'key_ingredients' && (field.claims_under_review ?? 0) > 0 && <p className="claim-count">{field.claims_under_review} {field.claims_under_review === 1 ? 'claim' : 'claims'} under review</p>}
      <div className="field-footer">
        <span className="field-time">{formatTime(field.checked_at)}</span>
        <div className="field-actions">
          <button type="button" className="text-button" data-testid={`evidence-open-${fieldKey}`} disabled={!onEvidence} onClick={() => onEvidence?.(fieldKey)}>View evidence <span aria-hidden="true">↗</span></button>
          <button type="button" className="text-button why-button" data-testid={`why-open-${fieldKey}`} disabled={!onWhy} onClick={() => onWhy?.(fieldKey)}>Why?</button>
        </div>
      </div>
      {(field.hidden_citations ?? 0) > 0 && <p className="private-note">+{field.hidden_citations} private {field.hidden_citations === 1 ? 'document' : 'documents'} (reviewers only)</p>}
    </div>
  </article>;
}

export function PassportCard({ passport, onEvidence, onWhy }: { passport: PassportView; onEvidence?: (key: FieldKey) => void; onWhy?: (key: FieldKey) => void }) {
  return <section className="passport-card" aria-labelledby="passport-title">
    <header className="passport-heading">
      <div className="passport-heading-top"><span className="eyebrow">A closer look at the listing</span><span className="passport-mark" aria-hidden="true">P<span>↗</span></span></div>
      <h2 id="passport-title">Product Truth Passport</h2>
      <p>What the sources say, one detail at a time.</p>
      <div className="passport-meta">
        <span className="plain-badge" data-testid="badge-origin">{passport.dataset_origin}</span>
        {passport.web_sources && <span className="plain-badge">{new Set(passport.web_sources.filter((source) => source.origin === 'REAL' && source.visibility === 'PUBLIC').map((source) => source.source_version_id)).size} REAL web sources</span>}
        {passport.llm_mode && <span className="plain-badge" data-testid="badge-mode">{passport.llm_mode}</span>}
        <span>Checked {formatTime(passport.last_checked_at)}</span>
      </div>
    </header>
    {passport.run_status === 'FAILED' && <div className="update-notice" role="status"><strong>Could not update</strong><p>This says nothing about the product.</p></div>}
    <div className="field-list">
      {FIELD_KEYS.map((key, index) => {
        const field = passport.fields.find((item) => item.field_key === key) ?? {
          field_key: key, label: '', public_text: 'No comparison is available yet.', verdict: null,
          conflict_locus: null, freshness: 'UNKNOWN', review_state: 'AUTO_DRAFT', checked_at: null, citations: [],
        };
        return <FieldRow key={key} fieldKey={key} field={field} runStatus={passport.run_status} index={index} onEvidence={onEvidence} onWhy={onWhy} />;
      })}
    </div>
    <footer className="passport-footnote"><span aria-hidden="true">ⓘ</span><p>{passport.disclaimer}</p></footer>
  </section>;
}
