import type { FieldKey, PassportField, PassportResponse } from '../types.ts';
import { FIELD_KEYS } from '../labels.ts';
import { toPassportResponse } from '../passportView.ts';

// Provisional presentation boundary until P1/P4 publish contract-4. Not generated wire DTOs.
export interface ReceiptDiff { field_key: FieldKey; before: PassportField | null; after: PassportField | null; changed: boolean }
export interface ReceiptResponse {
  id: string; product_id: string; created_at: string; snapshot: PassportResponse;
  snapshot_hash: string | null; chain_head: string | null;
  changed_since_purchase: boolean; diff: ReceiptDiff[];
}
export interface WebResult {
  rank: number; title: string; domain: string; url: string;
  classification: 'OFFICIAL' | 'RETAILER' | 'LEAD'; decision: string; reason: string;
}
export interface WebSnapshot {
  url: string; captured_at: string; sha256: string; passages_count: number;
  identity_verified: boolean; confirm_only: boolean;
}
export interface WebAuditResponse {
  case_id: string; searches: { query: string; results: WebResult[] }[]; snapshots: WebSnapshot[];
}
export interface ScorecardResponse {
  computed_at: string | null; status: string; metrics: Record<string, number | null>;
}

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const strings = (value: Record<string, unknown>, keys: string[]) => keys.every((key) => typeof value[key] === 'string');
const nullableText = (value: unknown) => value === null || typeof value === 'string';
const fieldKey = (value: unknown) => typeof value === 'string' && FIELD_KEYS.some((key) => key === value);
const count = (value: unknown) => typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 2 ** 53 - 1;
const field = (value: unknown) => value === null || (record(value)
  && fieldKey(value.field_key) && strings(value, ['label', 'public_text', 'review_state', 'verdict', 'freshness'])
  && ['CONSISTENT', 'SINGLE_SOURCE', 'CONFLICTING', 'INSUFFICIENT', 'UNCERTAIN'].includes(String(value.verdict))
  && ['CURRENT', 'STALE', 'UNKNOWN'].includes(String(value.freshness))
  && nullableText(value.checked_at) && nullableText(value.conflict_locus)
  && Array.isArray(value.citations) && value.citations.every((citation) => record(citation)
    && strings(citation, ['passage_id', 'source_kind', 'locator', 'excerpt']) && count(citation.source_version)));
const uniqueFields = (values: unknown[]) => new Set(values.map((value) => record(value) ? value.field_key : null)).size === values.length;

export function readReceipt(value: unknown): ReceiptResponse {
  if (!record(value) || !strings(value, ['id', 'product_id', 'created_at']) || !record(value.snapshot)
    || !strings(value.snapshot, ['product_id', 'dataset_origin', 'disclaimer']) || !Array.isArray(value.snapshot.fields)
    || value.snapshot.product_id !== value.product_id || !nullableText(value.snapshot.last_checked_at) || !nullableText(value.snapshot.run_status)
    || !value.snapshot.fields.every((item) => item !== null && field(item)) || !uniqueFields(value.snapshot.fields) || !Array.isArray(value.diff)
    || !uniqueFields(value.diff)
    || !value.diff.every((row) => record(row) && fieldKey(row.field_key) && typeof row.changed === 'boolean' && field(row.before) && field(row.after)
      && (row.before === null || (record(row.before) && row.before.field_key === row.field_key))
      && (row.after === null || (record(row.after) && row.after.field_key === row.field_key)))
    || typeof value.changed_since_purchase !== 'boolean' || !nullableText(value.snapshot_hash) || !nullableText(value.chain_head)) {
    throw new Error('The receipt response does not match the supported contract.');
  }
  const receipt = value as unknown as ReceiptResponse;
  // Retain only the public stored Passport schema, excluding accidental expert/display extras.
  return { ...receipt, snapshot: toPassportResponse(receipt.snapshot) };
}
export function readWebAudit(value: unknown): WebAuditResponse {
  if (!record(value) || typeof value.case_id !== 'string' || !Array.isArray(value.searches) || !Array.isArray(value.snapshots)
    || !value.searches.every((search) => record(search) && typeof search.query === 'string' && Array.isArray(search.results)
      && search.results.every((row) => record(row) && strings(row, ['title', 'domain', 'url', 'classification', 'decision', 'reason'])
        && ['OFFICIAL', 'RETAILER', 'LEAD'].includes(String(row.classification)) && count(row.rank) && Number(row.rank) > 0))
    || !value.snapshots.every((row) => record(row) && strings(row, ['url', 'captured_at', 'sha256']) && count(row.passages_count) && typeof row.identity_verified === 'boolean' && typeof row.confirm_only === 'boolean')) {
    throw new Error('The web audit response does not match the supported contract.');
  }
  return value as unknown as WebAuditResponse;
}
export function readScorecard(value: unknown): ScorecardResponse | null {
  if (value === null) return null;
  if (!record(value) || !nullableText(value.computed_at) || typeof value.status !== 'string' || !record(value.metrics)
    || !Object.values(value.metrics).every((item) => item === null || (typeof item === 'number' && Number.isFinite(item)))) {
    throw new Error('The scorecard response does not match the supported contract.');
  }
  return value as unknown as ScorecardResponse;
}
