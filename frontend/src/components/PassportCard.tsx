import { FIELD_KEYS, FIELD_TITLES } from '../labels.ts';
import type { PassportView } from '../types.ts';
import { StatusBadge } from './StatusBadge.tsx';

export function formatTime(value: string | null): string {
  if (!value) return 'Not checked yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Check time unavailable';
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' }).format(date) + ' ICT';
}

export function PassportCard({ passport }: { passport: PassportView }) {
  return <section className="passport-card" aria-labelledby="passport-title">
    <header className="passport-heading">
      <div className="passport-heading-top"><span className="eyebrow">A closer look at the listing</span><span className="passport-mark" aria-hidden="true">P<span>↗</span></span></div>
      <h2 id="passport-title">Product Truth Passport</h2>
      <p>What the sources say, one detail at a time.</p>
      <div className="passport-meta">
        <span className="plain-badge" data-testid="badge-origin">{passport.dataset_origin}</span>
        {passport.llm_mode && <span className="plain-badge" data-testid="badge-mode">{passport.llm_mode}</span>}
        <span>Checked {formatTime(passport.last_checked_at)}</span>
      </div>
    </header>
    <div className="field-list">
      {FIELD_KEYS.map((key, index) => {
        const field = passport.fields.find((item) => item.field_key === key) ?? {
          field_key: key, label: '', public_text: 'No comparison is available yet.', verdict: null,
          conflict_locus: null, freshness: 'UNKNOWN', review_state: 'AUTO_DRAFT', checked_at: null, citations: [],
        };
        return <article className="field-row" key={key} data-testid={`field-row-${key}`}>
          <span className="field-index" aria-hidden="true">0{index + 1}</span>
          <div className="field-content">
            <div className="field-heading"><h3>{FIELD_TITLES[key]}</h3><StatusBadge field={field} runStatus={passport.run_status} /></div>
            <p className="field-description">{field.public_text}</p>
            <div className="field-footer">
              <span className="field-time">{formatTime(field.checked_at)}</span>
              <div className="field-actions">
                <button type="button" className="text-button" data-testid={`evidence-open-${key}`} disabled title="Evidence view is coming in the next phase">View evidence <span aria-hidden="true">↗</span></button>
                <button type="button" className="text-button why-button" data-testid={`why-open-${key}`} disabled title="Explanation view is coming in a later phase">Why?</button>
              </div>
            </div>
            {(field.hidden_citations ?? 0) > 0 && <p className="private-note">+{field.hidden_citations} private {field.hidden_citations === 1 ? 'document' : 'documents'} (reviewers only)</p>}
          </div>
        </article>;
      })}
    </div>
    <footer className="passport-footnote"><span aria-hidden="true">ⓘ</span><p>{passport.disclaimer}</p></footer>
  </section>;
}
