import type { TraceStep, ExplanationResponse } from './types.ts';

// UI projection; wire models are generated from contract-3.
export interface Explanation {
  summary: string[];
  trail?: { stage: string; title: string; facts: string[] }[];
}
export function explanation(value: unknown): Explanation {
  const wire = object(value);
  if (wire.audience === 'BUYER' || wire.audience === 'EXPERT') return projectExplanation(wire as ExplanationResponse);
  if (!value || typeof value !== 'object' || !('summary' in value) || !Array.isArray(value.summary) || !value.summary.every((s: unknown) => typeof s === 'string')) throw new Error('The explanation response does not match the available contract.');
  const trail = 'trail' in value ? value.trail : undefined;
  if (trail !== undefined && (!Array.isArray(trail) || !trail.every((item: unknown) => item !== null && typeof item === 'object' && 'stage' in item && typeof item.stage === 'string' && 'title' in item && typeof item.title === 'string' && 'facts' in item && Array.isArray(item.facts) && item.facts.every((f: unknown) => typeof f === 'string')))) throw new Error('The explanation trail could not be read.');
  return { summary: value.summary, trail: trail as Explanation['trail'] };
}
export function projectExplanation(value: ExplanationResponse): Explanation {
  if (value.audience === 'BUYER') {
    if (!Array.isArray(value.summaries) || !value.summaries.every((s) => typeof s === 'string') || typeof value.public_text !== 'string') throw new Error('The public explanation could not be read.');
    return { summary: value.summaries.length ? value.summaries : [value.public_text] };
  }
  if (!('sources' in value) || !Array.isArray(value.sources) || !Array.isArray(value.claims) || !Array.isArray(value.rules) || !Array.isArray(value.publish_checks) || !Array.isArray(value.reviews)) throw new Error('The expert explanation could not be read.');
  return { summary: [], trail: [
    { stage: 'trigger', title: 'Trigger event', facts: [value.trigger_event_id, `Result ${value.result_id}`] },
    { stage: 'sources', title: 'Stored citations', facts: value.sources.map((s) => `${s.source_version_id} · ${s.origin} · ${s.captured_at} · ${s.sha256.slice(0, 12)}`) },
    { stage: 'claims', title: 'Extracted claims', facts: value.claims.map((c) => `${c.passage_id} · ${c.extractor} · ${c.prompt_version} · ${c.mapped_by ?? 'Mapping not recorded'}\n${c.quote ?? 'Unreadable'}`) },
    { stage: 'rules', title: 'Policy rules', facts: value.rules.map((r) => `${r.rule} · ${r.outcome} · ${r.detail}`) },
    { stage: 'publication', title: 'Publish gate', facts: value.publish_checks },
    { stage: 'chain', title: 'Chain head', facts: [value.chain_head?.slice(0, 12) ?? 'Not recorded'] },
    { stage: 'reviews', title: 'Reviews', facts: value.reviews.map((r) => `${r.decision} · ${r.created_at} · ${r.reason}`) },
  ] };
}
export function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export function text(value: unknown): string {
  return typeof value === 'string' ? value : typeof value === 'number' || typeof value === 'boolean' ? String(value) : '';
}
export function nonnegative(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}
export function waterfall(steps: TraceStep[]) {
  const ordered = steps.map((s) => ({ ...s, t_ms: nonnegative(s.t_ms) ?? 0, latency_ms: nonnegative(s.latency_ms) ?? 0 })).sort((a, b) => a.t_ms - b.t_ms || a.seq - b.seq);
  const end = Math.max(1, ...ordered.map((s) => Math.max(0, s.t_ms) + Math.max(0, s.latency_ms)));
  return ordered.map((step) => ({ step, left: Math.max(0, step.t_ms) / end * 100, width: Math.max(0, step.latency_ms) / end * 100 }));
}
export function latestBudget(steps: TraceStep[], kind: string) {
  for (const step of [...steps].sort((a, b) => b.seq - a.seq)) {
    const meter = object(object(object(step.detail).budget)[kind]);
    const used = nonnegative(meter.used), cap = nonnegative(meter.cap);
    if (used !== null && cap !== null) return { used, cap };
  }
  return null;
}

/** TraceWriter records t_ms when the step completes, including timed spans. */
export function completedWaterfall(steps: TraceStep[]) {
  return waterfall(steps.map((step) => ({ ...step, t_ms: Math.max(0, (nonnegative(step.t_ms) ?? 0) - (nonnegative(step.latency_ms) ?? 0)) })));
}
export function scopePlacement(step: TraceStep) {
  const d = object(step.detail);
  const identifier = (value: unknown) => typeof value === 'string' && value.trim() ? value : '';
  const passage = identifier(d.passage_id) || identifier(step.input_refs?.[0]);
  const anchor = identifier(d.anchor_passage_id) || identifier(step.output_refs?.[0]);
  const code = step.step === 'scope:validate' && step.actor === 'code';
  return { passage, anchor, verified: code && d.accepted !== false && (d.accepted === true || d.verified === true) && Boolean(passage && anchor), rejected: code && d.accepted === false };
}
