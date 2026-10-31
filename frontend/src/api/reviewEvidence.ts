import type { Citation, EvidenceResponse } from '../types.ts';

function sameCitation(a: Citation, b: Citation): boolean {
  return a.passage_id === b.passage_id && a.source_kind === b.source_kind && a.source_version === b.source_version && a.locator === b.locator && a.excerpt === b.excerpt;
}

/** A response for a different product/version must never decorate this result. */
export function matchingReviewEvidence(citations: Citation[], candidate: EvidenceResponse): EvidenceResponse | null {
  if (!citations.length || !citations.every((citation) => candidate.citations.some((passage) => sameCitation(citation, passage)))) return null;
  return { citations: candidate.citations.filter((passage) => citations.some((citation) => sameCitation(citation, passage))), hidden_citations: candidate.hidden_citations };
}
