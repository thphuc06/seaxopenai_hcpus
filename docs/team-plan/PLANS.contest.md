# ExecPlans (`.agent/PLANS.md`)

An ExecPlan is the living design-and-progress document a Codex thread keeps while it builds one lane of this repo.
Format adapted from OpenAI's cookbook article "Using PLANS.md for multi-hour problem solving"; trimmed for a 7-hour,
4-lane build.

## Rules

- **One file per lane:** `.agent/plans/P1.md` … `P4.md`. Each phase adds a milestone section (`## Phase N — <title>`);
  earlier phases stay (they are the history the integrator and the write-up read).
- **Self-contained.** A teammate who has only this file and the working tree can continue the work. Define every term
  of art in plain words the first time you use it; name files by full repo path; name functions with signatures.
- **Living.** Update *Progress*, *Surprises & Discoveries* and *Decision Log* while you work, not at the end. Every
  Progress line has a time stamp (`T+h:mm`).
- **Behaviour, not code changes.** Acceptance is something a person can observe (a test name that passes, an API
  response, a screen), not "function X exists".
- **Honest.** Record what failed, what you could not verify, and what you cut.

## Template (copy for each phase)

```markdown
## Phase N — <title>  (T+a:aa–b:bb · lane Px)

### Purpose / Big picture
<2–4 sentences: what a user/judge can do after this phase that they could not before, and why it matters.>

### Progress
- [ ] (T+h:mm) <step>
- [x] (T+h:mm) <step> — <result, e.g. "test_revoke_stales_only_dependents passes">

### Surprises & Discoveries
- <unexpected behaviour, with the evidence (error text, test output, doc link)>

### Decision Log
- Decision: <what> · Rationale: <why> · Alternatives: <what was rejected> · (T+h:mm)

### Context and orientation
<Files and modules involved (full paths), what already exists from earlier phases/other lanes, contracts relied on
(README §7 rows), fixtures used.>

### Plan of work
<Ordered narrative of the edits: which file, what changes, why.>

### Concrete steps
<Exact commands to run (from which directory) and what their output should show. Write commands as indented blocks
(four spaces), not nested code fences.>

### Validation and acceptance
<Tests (names) and observable behaviours that prove the phase is done; which ones are gated by CONTEST_PHASE.>

### Interfaces and dependencies
<Signatures you expose (unchanged/extended), routes, trace steps, env switches; CCRs sent/received.>

### Idempotence and recovery
<Safe re-runs (seed reset, demo reset, replay), how to roll back a half-done step.>

### Artifacts and notes
<Short evidence as indented blocks: the failing then passing test output, a trace excerpt, a diff stat, a doc URL.>

### Outcomes & retrospective  (fill at the Sync)
- Delivered: … · Not delivered (cut / moved): … · Lessons for the next phase: …

Revision note: (T+h:mm) <what changed in this plan and why>
```

## Deviations from the cookbook (deliberate)
- One file per lane with one milestone per phase, instead of one plan per feature: seven 75-minute phases on four lanes.
- Contracts are referenced (`docs/team-plan/README.md` §7, frozen per phase and versioned in git) instead of restated,
  to keep plans short; everything else must be self-contained.
- Bullets are allowed in Progress and the Decision Log; the other sections stay prose.

## How the integrator uses the plans

At each Sync, P4 reads the four *Outcomes* and *Surprises* sections, copies two lines per lane into
`docs/tracking/DEVLOG.md`, and the *Decision Log* entries that change a contract into `docs/tracking/DECISIONS.md`.
The plans are also evidence for the write-up's "how Codex was used" section.
