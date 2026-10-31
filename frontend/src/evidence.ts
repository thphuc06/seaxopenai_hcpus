import type { EvidencePassage, PassportResponse } from './types.ts';

export interface HighlightPart { text: string; highlighted: boolean }

/** NFC and whitespace matching while retaining every original source character. */
export function highlightExcerpt(text: string, excerpt: string): HighlightPart[] {
  const starts: number[] = [];
  const ends: number[] = [];
  let normalized = '';
  for (const item of new Intl.Segmenter('und', { granularity: 'grapheme' }).segment(text)) {
    for (const character of item.segment.normalize('NFC')) {
      const value = /\s/u.test(character) ? ' ' : character;
      if (value === ' ' && normalized.endsWith(' ')) {
        ends[ends.length - 1] = item.index + item.segment.length;
        continue;
      }
      normalized += value;
      for (let unit = 0; unit < value.length; unit++) {
        starts.push(item.index); ends.push(item.index + item.segment.length);
      }
    }
  }
  const quote = excerpt.normalize('NFC').replace(/\s+/gu, ' ').trim();
  const index = quote ? normalized.indexOf(quote) : -1;
  const start = starts[index];
  const end = ends[index + quote.length - 1];
  if (index < 0 || start === undefined || end === undefined) return [{ text, highlighted: false }];
  return [
    { text: text.slice(0, start), highlighted: false },
    { text: text.slice(start, end), highlighted: true },
    { text: text.slice(end), highlighted: false },
  ];
}

export function groupEvidence(citations: EvidencePassage[]): EvidencePassage[][] {
  const groups = new Map<string, EvidencePassage[]>();
  for (const citation of citations) {
    const key = JSON.stringify([citation.source_kind, citation.source_label, citation.source_version, citation.captured_at, citation.source_url ?? null]);
    const group = groups.get(key) ?? [];
    group.push(citation); groups.set(key, group);
  }
  return [...groups.values()];
}

export function passportPollInterval(passport: PassportResponse | null): number {
  return passport?.run_status === 'RUNNING' || passport?.fields.some((field) => field.freshness === 'STALE') ? 2_000 : 10_000;
}
