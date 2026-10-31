import { useCallback } from 'react';
import { useParams } from 'react-router-dom';
import type { ApiClient } from '../api/client.ts';
import type { ReceiptResponse } from '../api/phase4Types.ts';
import type { DemoRole } from '../types.ts';
import { usePoll } from '../usePoll.ts';
import { FIELD_KEYS, FIELD_TITLES, buyerLabel } from '../labels.ts';
import { PassportCard, formatTime } from '../components/PassportCard.tsx';
import { ErrorNotice, LoadingNotice } from '../components/Feedback.tsx';

export function ReceiptView({ receipt, role }: { receipt: ReceiptResponse; role: DemoRole }) {
  const expert = role === 'OPERATOR' || role === 'REVIEWER';
  const rows = [...receipt.diff].sort((a, b) => Number(b.changed) - Number(a.changed));
  const complete = FIELD_KEYS.every((key) => rows.some((row) => row.field_key === key && (row.changed || (row.then !== null && row.now !== null))));
  return <><header className="phase4-panel"><p className="eyebrow">Evidence receipt</p><h1>A record of what you saw.</h1><p>Saved {formatTime(receipt.placed_at)}</p>
    {expert && <details><summary>Receipt integrity references</summary><p>Snapshot hash: {receipt.snapshot_hash || 'Not recorded'}</p><p>Chain head: {receipt.chain_head ?? 'Not recorded'}</p><p>Integrity check: {receipt.snapshot_hash ? receipt.hash_valid ? 'Passed' : 'Did not pass' : 'Not recorded'}</p></details>}
  </header><section className="phase4-panel" data-testid="receipt-diff"><h2>{receipt.changed_since_purchase ? 'Changed since purchase' : complete ? 'No changes since purchase' : 'Comparison not available'}</h2>
    {!complete && <p>The comparison does not yet cover all five details. Missing comparisons do not indicate unchanged information.</p>}
    <p>The saved Passport stays as it was. The comparison below follows current stored results.</p>
    <p>Current processing status is unavailable. The Now column shows stored findings.</p>
    <div className="receipt-table"><table><thead><tr><th>Detail</th><th>At purchase</th><th>Now</th><th>Change</th></tr></thead><tbody>{rows.map((row) => <tr key={row.field_key}><th>{FIELD_TITLES[row.field_key]}</th>
      <td>{row.then ? <>{buyerLabel(row.then, receipt.snapshot.run_status).text}<p>{row.then.public_text}</p></> : 'Not recorded'}</td>
      <td>{row.now ? <>{buyerLabel(row.now, null).text}<p>{row.now.public_text}</p></> : 'Not recorded'}</td><td>{row.changed ? 'Changed' : row.then === null || row.now === null ? 'Not recorded' : 'Unchanged'}</td></tr>)}</tbody></table></div>
  </section><h2>Passport saved at purchase</h2><PassportCard passport={receipt.snapshot} /></>;
}
export function Receipt({ api, role }: { api: ApiClient; role: DemoRole }) {
  const { orderId = '' } = useParams();
  const load = useCallback((signal: AbortSignal) => api.getOrder(orderId, signal), [api, orderId]);
  const state = usePoll(load, 5_000);
  return <>{!state.data && <h1>A record of what you saw.</h1>}{state.loading && <LoadingNotice />}{state.error && <ErrorNotice error={state.error} technical={role === 'OPERATOR' || role === 'REVIEWER'} />}{state.data && <ReceiptView receipt={state.data} role={role} />}</>;
}
