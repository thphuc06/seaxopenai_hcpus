import { useRef, useState } from 'react';
import type { ApiClient } from '../api/client.ts';
import type { EvidenceUpload } from '../api/reviewTypes.ts';
import type { AdmitResult } from '../types.ts';
import { ErrorNotice } from './Feedback.tsx';

export function parseEvidenceJson(text: string): EvidenceUpload {
  const parsed: unknown = JSON.parse(text);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Evidence must be a JSON object.');
  return parsed as EvidenceUpload;
}

export function EvidenceUploadForm({ api }: { api: ApiClient }) {
  const [caseId, setCaseId] = useState('');
  const [text, setText] = useState('');
  const [error, setError] = useState<Error | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [admission, setAdmission] = useState<AdmitResult | null>(null);
  const lock = useRef(false);
  async function submit() {
    if (lock.current || !caseId.trim() || !text.trim()) return;
    let evidence: EvidenceUpload;
    try { evidence = parseEvidenceJson(text); }
    catch { setValidation('Enter an evidence JSON object.'); setAdmission(null); return; }
    lock.current = true; setPending(true); setError(null); setValidation(null); setAdmission(null);
    try {
      const result = await api.uploadEvidence(caseId.trim(), evidence);
      if (!['ADMITTED', 'REJECTED', 'NOOP', 'DUPLICATE'].includes(result.outcome) || typeof result.reason !== 'string') throw new Error('The server did not report an admission outcome.');
      setAdmission(result);
    }
    catch (caught) { setError(caught instanceof Error ? caught : new Error('Evidence could not be submitted.')); }
    finally { lock.current = false; setPending(false); }
  }
  return <section className="seller-evidence"><p className="eyebrow">Seller workspace</p><h2>Provide source evidence</h2>
    <p>Paste an evidence JSON object for the case. The server checks access and the evidence format.</p>
    <form className="review-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
      <label>Case reference<input aria-label="Case reference" required value={caseId} disabled={pending} onChange={(event) => { setCaseId(event.target.value); setAdmission(null); }} /></label>
      <label>Evidence JSON<textarea aria-label="Evidence JSON" required value={text} disabled={pending} onChange={(event) => { setText(event.target.value); setAdmission(null); }} /></label>
      {validation && <p role="alert">{validation}</p>}{error && <ErrorNotice error={error} />}
      <button type="submit" className="primary-button" disabled={pending || !caseId.trim() || !text.trim()}>{pending ? 'Submitting…' : 'Submit evidence'}</button>
      {admission && <div role={admission.outcome === 'REJECTED' ? 'alert' : 'status'} className="upload-outcome"><strong>{admission.outcome}</strong><p>{admission.reason}</p>
        {admission.outcome === 'ADMITTED' && <p>Evidence submitted. {admission.job_id ? 'Processing was queued.' : 'The request was admitted.'}</p>}
        {(admission.outcome === 'NOOP' || admission.outcome === 'DUPLICATE') && <p>No new processing was started.</p>}
      </div>}
    </form>
  </section>;
}
