import type { components, paths } from './schema.d.ts';
import type { FieldKey, PassportField } from '../types.ts';
import { FIELD_KEYS } from '../labels.ts';
import { toPassportResponse } from '../passportView.ts';

type Schema = components['schemas'];
export type CreateOrderResponse = paths['/api/orders']['post']['responses'][200]['content']['application/json'];
export type OrderDetailResponse = paths['/api/orders/{order_id}']['get']['responses'][200]['content']['application/json'];
export type ReceiptDiff = Omit<Schema['ReceiptFieldDiff'], 'field_key'> & { field_key: FieldKey };
export type ReceiptResponse = Omit<OrderDetailResponse, 'diff'> & { diff: ReceiptDiff[] };
export type WebAuditResponse = Schema['WebAuditResponse'];
export type ScorecardWire = paths['/api/internal/eval/metrics']['get']['responses'][200]['content']['application/json'];
// Presentation of numeric report entries; the wire contract preserves arbitrary JSON reports.
export interface ScorecardResponse {
  computed_at: string | null; status: string; metrics: Record<string, number | null>;
  provenance?: { mode: string; requested_mode?: string; fallback_reason?: string; models: string[]; prompt_versions: string[]; policy_versions: string[]; limitations: string[] };
}

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const strings = (value: Record<string, unknown>, keys: string[]) => keys.every((key) => typeof value[key] === 'string');
const nullableText = (value: unknown) => value === null || typeof value === 'string';
const oneOf = (value: unknown, values: readonly string[]) => typeof value === 'string' && values.includes(value);
const fieldKey = (value: unknown) => oneOf(value, FIELD_KEYS);
const count = (value: unknown) => typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 2 ** 53 - 1;
const field = (value: unknown) => value === null || (record(value)
  && fieldKey(value.field_key) && strings(value, ['label', 'public_text'])
  && oneOf(value.verdict, ['CONSISTENT', 'SINGLE_SOURCE', 'CONFLICTING', 'INSUFFICIENT', 'UNCERTAIN', 'NOT_APPLICABLE'])
  && oneOf(value.freshness, ['CURRENT', 'STALE', 'UNKNOWN'])
  && oneOf(value.review_state, ['AUTO_DRAFT', 'NEEDS_REVIEW', 'REVIEWED', 'SUPERSEDED'])
  && nullableText(value.checked_at) && (value.conflict_locus === null || oneOf(value.conflict_locus, ['WITHIN_SOURCE', 'ACROSS_SOURCES', 'LISTING_VS_SOURCE']))
  && Array.isArray(value.citations) && value.citations.every((citation) => record(citation)
    && strings(citation, ['passage_id', 'locator', 'excerpt']) && count(citation.source_version)
    && oneOf(citation.source_kind, ['LISTING', 'BRAND_PAGE', 'NOTIFICATION_DOC', 'PACKAGING_IMAGE', 'SELLER_UPLOAD', 'REGISTRY_RECORD', 'WEB_PAGE'])));
const uniqueFields = (values: unknown[]) => new Set(values.map((value) => record(value) ? value.field_key : null)).size === values.length;

export function readReceipt(value: unknown): ReceiptResponse {
  if (!record(value) || !strings(value, ['id', 'product_id', 'case_id', 'placed_at', 'snapshot_hash']) || !count(value.case_revision) || !record(value.snapshot)
    || !strings(value.snapshot, ['product_id', 'disclaimer']) || !oneOf(value.snapshot.dataset_origin, ['REAL', 'SYNTHETIC']) || !Array.isArray(value.snapshot.fields)
    || value.snapshot.product_id !== value.product_id || !nullableText(value.snapshot.last_checked_at)
    || !(value.snapshot.run_status === null || oneOf(value.snapshot.run_status, ['QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'WAITING_EVIDENCE', 'WAITING_REVIEW', 'FAILED', 'CANCELLED']))
    || !value.snapshot.fields.every((item) => item !== null && field(item)) || !uniqueFields(value.snapshot.fields) || !Array.isArray(value.diff)
    || !uniqueFields(value.diff)
    || !value.diff.every((row) => record(row) && fieldKey(row.field_key) && typeof row.changed === 'boolean' && field(row.then) && field(row.now)
      && (row.then === null || (record(row.then) && row.then.field_key === row.field_key))
      && (row.now === null || (record(row.now) && row.now.field_key === row.field_key)))
    || typeof value.changed_since_purchase !== 'boolean' || typeof value.hash_valid !== 'boolean' || !nullableText(value.chain_head)
    || (value.changed_since_purchase === false && value.diff.some((row) => record(row) && row.changed === true))) {
    throw new Error('The receipt response does not match the supported contract.');
  }
  const receipt = value as unknown as ReceiptResponse;
  const project = (item: PassportField | null) => item === null ? null : toPassportResponse({ ...receipt.snapshot, fields: [item] }).fields[0]!;
  return { id: receipt.id, product_id: receipt.product_id, case_id: receipt.case_id, placed_at: receipt.placed_at,
    case_revision: receipt.case_revision, snapshot_hash: receipt.snapshot_hash, chain_head: receipt.chain_head, hash_valid: receipt.hash_valid,
    changed_since_purchase: receipt.changed_since_purchase, snapshot: toPassportResponse(receipt.snapshot),
    diff: receipt.diff.map((row) => ({ field_key: row.field_key, then: project(row.then), now: project(row.now), changed: row.changed })) };
}
export function readWebAudit(value: unknown): WebAuditResponse {
  if (!record(value) || typeof value.case_id !== 'string' || !Array.isArray(value.queries) || !Array.isArray(value.snapshots)
    || !value.queries.every((query) => record(query) && strings(query, ['id', 'run_id', 'query', 'provider', 'created_at'])
      && oneOf(query.mode, ['LIVE', 'REPLAY', 'FALLBACK']) && Array.isArray(query.results)
      && query.results.every((row) => record(row) && strings(row, ['domain', 'url', 'class', 'decision', 'reason'])
        && (row.score === null || (typeof row.score === 'number' && Number.isFinite(row.score)))))
    || !value.snapshots.every((row) => record(row) && strings(row, ['source_version_id', 'url', 'captured_at', 'sha256'])
      && oneOf(row.dataset_origin, ['REAL', 'SYNTHETIC']) && typeof row.identity_verified === 'boolean'
      && Array.isArray(row.passages) && row.passages.every((passage) => record(passage) && strings(passage, ['id', 'locator', 'text'])))) {
    throw new Error('The web audit response does not match the supported contract.');
  }
  return value as unknown as WebAuditResponse;
}
function numericEntries(value: Record<string, unknown>, prefix = ''): [string, number | null][] {
  return Object.entries(value).flatMap(([key, item]) => {
    const name = prefix ? `${prefix} · ${key}` : key;
    if (item === null || (typeof item === 'number' && Number.isFinite(item))) return [[name, item] as [string, number | null]];
    return record(item) ? numericEntries(item, name) : [];
  });
}
export function readScorecard(value: unknown): ScorecardResponse | null {
  if (!record(value)) throw new Error('The scorecard response does not match the supported contract.');
  if (value.available === false) return null;
  const reportValues = Object.fromEntries(Object.entries(value).filter(([key]) => !['available', 'computed_at', 'generated_at', 'status', 'gold_status', 'format_version', 'evaluated_at', 'source_sha256', 'mode', 'requested_mode', 'fallback_reason', 'models', 'prompt_versions', 'policy_versions', 'limitations'].includes(key)));
  const metrics = numericEntries(record(value.metrics) ? value.metrics : record(value.totals) ? value.totals : reportValues);
  const date = typeof value.generated_at === 'string' ? value.generated_at : typeof value.computed_at === 'string' ? value.computed_at : null;
  if (!metrics.length && !date && value.available !== true) throw new Error('The scorecard response does not match the supported contract.');
  let provenance: ScorecardResponse['provenance'];
  if (value.mode !== undefined) {
    if (!oneOf(value.mode, ['fallback', 'replay', 'FALLBACK', 'REPLAY'])
      || (value.requested_mode !== undefined && !oneOf(value.requested_mode, ['fallback', 'replay', 'FALLBACK', 'REPLAY']))
      || (value.fallback_reason != null && typeof value.fallback_reason !== 'string')) throw new Error('The scorecard execution mode could not be read.');
    const list = (key: string): string[] => {
      if (value[key] === undefined) return [];
      if (!Array.isArray(value[key]) || !value[key].every((item) => typeof item === 'string')) throw new Error('The scorecard provenance could not be read.');
      return value[key];
    };
    provenance = { mode: String(value.mode).toUpperCase(),
      ...(typeof value.requested_mode === 'string' ? { requested_mode: value.requested_mode.toUpperCase() } : {}),
      ...(typeof value.fallback_reason === 'string' ? { fallback_reason: value.fallback_reason } : {}),
      models: list('models'), prompt_versions: list('prompt_versions'), policy_versions: list('policy_versions'), limitations: list('limitations') };
  }
  return { computed_at: date, status: typeof value.gold_status === 'string' ? value.gold_status : typeof value.status === 'string' ? value.status : 'Status not recorded', metrics: Object.fromEntries(metrics), ...(provenance ? { provenance } : {}) };
}
