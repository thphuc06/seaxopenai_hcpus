import type { RunDetail } from '../types.ts';
import { latestBudget, object, text, completedWaterfall, scopePlacement } from '../glassbox.ts';
import { traceLane } from '../trace.ts';

function Values({ value }: { value: unknown }) {
  if (Array.isArray(value)) return <ul>{value.map((item, i) => <li key={i}><Values value={item} /></li>)}</ul>;
  if (value && typeof value === 'object') return <dl>{Object.entries(value).map(([key, item]) => <div key={key}><dt>{key}</dt><dd><Values value={item} /></dd></div>)}</dl>;
  return <span>{text(value) || 'Not recorded'}</span>;
}
export function RunGlassbox({ detail }: { detail: RunDetail }) {
  const steps = detail.steps.map((s) => ({ ...s, detail: object(s.detail) })).sort((a, b) => a.seq - b.seq);
  const agentSteps = steps.filter((s) => s.step.startsWith('agent:') || s.step.startsWith('scope:'));
  const effects = steps.filter((s) => s.step === 'agent:effect' && s.actor === 'code');
  const start = steps.find((s) => s.step === 'agent:start');
  const proposals = agentSteps.filter((s) => ['agent:proposal', 'scope:validate'].includes(s.step));
  const placements = proposals.filter((s, index) => {
    const passage = scopePlacement(s).passage;
    return !passage || !proposals.slice(index + 1).some((later) => later.step === 'scope:validate' && later.actor === 'code' && scopePlacement(later).passage === passage);
  });
  return <div className="run-glassbox">
    <section aria-label="Run waterfall"><h3>Run waterfall</h3><p>Offsets from run start · milliseconds</p>
      <ol className="waterfall">{completedWaterfall(steps).map(({ step, left, width }) => <li key={step.id} className={`${step.step.startsWith('agent:tool:') ? 'nested-span' : ''} ${step.error ? 'span-error' : ''}`}>
        <span>{step.step}{step.detail.replayed === true && <b className="plain-badge">REPLAY</b>}</span><div className="span-track"><span className={`span-bar lane-${traceLane(step.step)}`} style={{ marginLeft: `${left}%`, width: `${width}%` }} /></div>
        <small>{step.t_ms} ms + {step.latency_ms} ms{step.error && ` · ${step.error}`}</small>
      </li>)}</ol>{!steps.length && <p>No steps recorded.</p>}
      {detail.run.stop_reason && <p className="stop-reason">{detail.run.status} · {detail.run.stop_reason}</p>}
    </section>
    <section data-testid="agent-panel" className="agent-panel"><p className="eyebrow">Bounded agent</p><h3>What changed?</h3>
      {start ? <><p>{text(start.detail.question) || 'Question not recorded'}</p><Values value={start.detail.fields} /></> : <p>No agent start recorded for this run.</p>}
      <h4>Run budget</h4><div className="budget-grid">{(['model_calls', 'tool_calls', 'seconds'] as const).map((kind) => {
        const budget = latestBudget(steps, kind);
        return <div key={kind} data-testid={`budget-meter-${kind}`}><strong>{kind.replaceAll('_', ' ')}</strong>{budget ? <><p>{budget.used} / {budget.cap}</p>{budget.cap > 0 && <progress aria-label={kind.replaceAll('_', ' ')} max={budget.cap} value={Math.min(budget.used, budget.cap)} />}{budget.used > budget.cap && <p>Recorded usage exceeds cap</p>}</> : <p>Budget not recorded</p>}</div>;
      })}</div>
      <h4>Proposals and code checks</h4><ol className="decision-trail">{placements.map((step) => {
        const d = step.detail;
        const placement = scopePlacement(step);
        return <li key={step.id}><strong>{placement.passage || 'Passage not recorded'}</strong><p>{placement.verified ? `verified by code (anchor: ${placement.anchor})` : placement.rejected ? `not accepted (${text(d.reason) || 'reason not recorded'})` : 'needs reviewer'}</p>{d.proposals !== undefined && <Values value={d.proposals} />}</li>;
      })}</ol>{!agentSteps.some((s) => ['agent:proposal', 'scope:validate'].includes(s.step)) && <p>No proposals or code checks recorded.</p>}
      <div className="agent-effect"><h4>Effect recorded by code</h4>{effects.length ? effects.map((step) => <article key={step.id}><strong>{text(step.detail.field) || text(step.detail.field_key) || 'Fields'}</strong><div className="effect-comparison"><div><h5>Before</h5><Values value={step.detail.before} /></div><span aria-hidden="true">→</span><div><h5>After</h5><Values value={step.detail.after} /></div></div><p>{step.detail.passages_added !== undefined ? 'Passages added' : 'Scope passages'}</p><Values value={step.detail.passages_added ?? step.detail.passages} />{step.detail.changed === false && <p>No change recorded.</p>}</article>) : <p>No effect record available; a change cannot be confirmed.</p>}</div>
      {agentSteps.filter((s) => s.step === 'agent:stop').map((s) => <p className="stop-reason" key={s.id}>Agent stopped: {text(s.detail.stop_reason) || 'reason not recorded'}</p>)}
    </section>
  </div>;
}
