import type { PassportMetadata, PassportResponse, PassportView } from './types.ts';

/** Project a composite preview into the exact stored-result API shape. */
export function toPassportResponse(preview: PassportView): PassportResponse {
  return {
    product_id: preview.product_id,
    dataset_origin: preview.dataset_origin,
    last_checked_at: preview.last_checked_at,
    run_status: preview.run_status,
    disclaimer: preview.disclaimer,
    fields: preview.fields.map((field) => {
      if (field.verdict === null) throw new Error('A pending display row cannot be a stored result.');
      return {
        field_key: field.field_key, label: field.label, public_text: field.public_text,
        verdict: field.verdict, conflict_locus: field.conflict_locus, freshness: field.freshness,
        review_state: field.review_state, checked_at: field.checked_at,
        citations: field.citations.map((citation) => ({
          passage_id: citation.passage_id, source_kind: citation.source_kind,
          source_version: citation.source_version, locator: citation.locator, excerpt: citation.excerpt,
        })),
      };
    }),
  };
}

/** Restore display-only information supplied separately, without changing findings. */
export function withPassportMetadata(passport: PassportView, metadata?: PassportMetadata): PassportView {
  if (!metadata) return passport;
  return {
    ...passport,
    llm_mode: metadata.llm_mode ?? passport.llm_mode,
    fields: passport.fields.map((field) => ({
      ...field,
      hidden_citations: metadata.hidden_citations[field.field_key] ?? field.hidden_citations,
    })),
  };
}
