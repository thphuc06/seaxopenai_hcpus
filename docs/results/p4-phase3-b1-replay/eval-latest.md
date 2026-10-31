# B0 / B1 / candidate evaluation

Generated: 2026-10-31T06:26:44.926302+00:00
Mode: fallback; requested: fallback; gold: DRAFT; labelled by: draft:codex
Models: FALLBACK; prompts: extract-v1; policies: policy-v1.6
Baseline: b0-v1; gold SHA256: d071ab0d0c0ffb6985d1fd75f50459d09043c362d0503876c963c131d28e3871

## Scores by gold review status

| Gold | System | Correct/total | False blame/eligible | Abstentions | Correct/expected abstentions |
|---|---|---:|---:|---:|---:|
| DRAFT | B0 | 1/5 | 0/5 | 0 | 0/0 |
| DRAFT | B1 | 5/5 | 0/5 | 0 | 0/0 |
| DRAFT | candidate | 5/5 | 0/5 | 0 | 0/0 |
| REVIEWED | B0 | 0/0 | 0/0 | 0 | 0/0 |
| REVIEWED | B1 | 0/0 | 0/0 | 0 | 0/0 |
| REVIEWED | candidate | 0/0 | 0/0 | 0 | 0/0 |

## Checkpoints

| Event | Gold | B0 | B1 | Candidate | Calls | Tokens in/out | Latency ms | Outcome / stops |
|---|---|---:|---|---:|---:|---:|---:|---|
| 01-bootstrap-demo | DRAFT | 1/5 | 5/5 (REPLAY) | 5/5 | 0 | 0/0 | 625.00 | ADMITTED;  |

## B1 usage

- 01-bootstrap-demo: model=gpt-6.1-sol; 1 calls; 0/0 tokens; REPLAY.

## Disagreements and preconditions

- 01-bootstrap-demo / volume: expected CONSISTENT; B0 SINGLE_SOURCE; B1 CONSISTENT; candidate CONSISTENT.
- 01-bootstrap-demo / key_ingredients: expected CONSISTENT; B0 SINGLE_SOURCE; B1 CONSISTENT; candidate CONSISTENT.
- 01-bootstrap-demo / notification_number: expected CONSISTENT; B0 SINGLE_SOURCE; B1 CONSISTENT; candidate CONSISTENT.
- 01-bootstrap-demo / responsible_company: expected CONSISTENT; B0 SINGLE_SOURCE; B1 CONSISTENT; candidate CONSISTENT.

## Limits

- DRAFT scores are exploratory diagnostics, not human-reviewed accuracy.
- B0 uses candidate-stored claims; upstream scope/extraction filtering is shared, not an independent extraction baseline.
- B0 adds zero model calls. Usage is counted once per newly observed candidate run; NOOP/DUPLICATE do not reuse prior usage.
- Literal expected labels are scored; preconditions and alternative gold scenarios are not inferred from candidate output.
- Only five public fields are scored; expert claim findings and isolated image scenarios have separate acceptance tests.
- False-blame attribution is unscored for expected conflicts without an explicit attribution invariant.
- B1 is an unpublished single-call diagnostic over source passages, with separate usage. NOT_RUN/errors/caps are unscored, never zero-accuracy claims.

Candidate totals: 0 calls, 0/0 tokens in/out, 625.00 ms.
