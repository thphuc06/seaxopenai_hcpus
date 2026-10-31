import type { TraceStep } from './types.ts';

// Provisional frontend contract, to be aligned with P1's contract-3 OpenAPI.
export interface Explanation {
  summary: string[];
  trail?: { stage: string; title: string; facts: string[] }[];
}
export function explanation(value: unknown): Explanation {
  if (!value || typeof value !== 'object' || !('summary' in value) || !Array.isArray(value.summary) || !value.summary.every((s: unknown) => typeof s === 'string')) throw new Error('The explanation response does not match the available contract.');
  const trail = 'trail' in value ? value.trail : undefined;
  if (trail !== undefined && (!Array.isArray(trail) || !trail.every((item: unknown) => item !== null && typeof item === 'object' && 'stage' in item && typeof item.stage === 'string' && 'title' in item && typeof item.title === 'string' && 'facts' in item && Array.isArray(item.facts) && item.facts.every((f: unknown) => typeof f === 'string')))) throw new Error('The explanation trail could not be read.');
  return { summary: value.summary, trail: trail as Explanation['trail'] };
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
