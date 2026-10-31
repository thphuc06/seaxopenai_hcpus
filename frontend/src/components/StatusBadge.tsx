import { buyerLabel } from '../labels.ts';
import type { PassportField, RunStatus } from '../types.ts';

export function StatusBadge({ field, runStatus }: { field: PassportField; runStatus: RunStatus | null }) {
  const label = buyerLabel(field, runStatus);
  return <span className={`status-badge tone-${label.tone}`} data-testid={`field-label-${field.field_key}`}>
    <span className="status-dot" aria-hidden="true" />{label.text}
  </span>;
}
