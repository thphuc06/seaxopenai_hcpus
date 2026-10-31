export type TraceLane = 'code' | 'model' | 'agent' | 'gap' | 'web' | 'other';

/** Prefix vocabulary follows README 7.3; unknown steps stay visible. */
export function traceLane(step: string): TraceLane {
  if (step === 'agent:web_scout' || step.startsWith('web:')) return 'web';
  if (step.startsWith('gap:')) return 'gap';
  if (step.startsWith('agent:') || step.startsWith('scope:')) return 'agent';
  if (step === 'extract' || step.startsWith('extract:') || step === 'canon:learn' || step === 'claims:audit') return 'model';
  if (['pin_revision', 'scope_check', 'publish', 'stale:mark', 'run:stop'].includes(step) || step.startsWith('policy:') || step.startsWith('publish:')) return 'code';
  return 'other';
}
