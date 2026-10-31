import type { FieldKey, PassportViewField, RunStatus } from './types.ts';

export const FIELD_TITLES: Record<FieldKey, string> = {
  volume: 'Volume',
  skin_type: 'Skin type',
  key_ingredients: 'Key ingredients',
  notification_number: 'Notification number',
  responsible_company: 'Responsible company',
};
export const FIELD_KEYS = Object.keys(FIELD_TITLES) as FieldKey[];

export function reviewFindingTitle(fieldKey: string): string {
  if (fieldKey.startsWith('claim:ingredient:')) return 'Ingredient claim';
  if (fieldKey.startsWith('claim:')) return 'Claim — Phát biểu cần duyệt';
  return FIELD_TITLES[fieldKey as FieldKey] ?? fieldKey;
}

export type LabelTone = 'consistent' | 'single' | 'source-conflict' | 'conflicting' | 'unverified' | 'stale' | 'pending' | 'failed';
export interface BuyerLabel { text: string; tone: LabelTone }

/** docs/04 first-match order. The server's label never overrides stored state. */
export function buyerLabel(field: PassportViewField | null | undefined, runStatus: RunStatus | null): BuyerLabel {
  if (field?.freshness === 'STALE') return { text: 'Stale', tone: 'stale' };
  if (runStatus === 'RUNNING') return { text: 'Updating', tone: 'pending' };
  if (!field?.verdict) return { text: 'Not checked yet', tone: 'pending' };
  if (field.verdict === 'CONFLICTING') {
    return field.conflict_locus === 'WITHIN_SOURCE'
      ? { text: 'Conflict in source', tone: 'source-conflict' }
      : { text: 'Conflicting', tone: 'conflicting' };
  }
  if (field.verdict === 'SINGLE_SOURCE') return { text: 'Single source', tone: 'single' };
  if (field.verdict === 'CONSISTENT') return { text: 'Consistent', tone: 'consistent' };
  if (field.verdict === 'INSUFFICIENT' || field.verdict === 'UNCERTAIN') return { text: 'Not verified', tone: 'unverified' };
  if (runStatus === 'FAILED') return { text: 'Could not update', tone: 'failed' };
  return { text: 'Not verified', tone: 'unverified' };
}
