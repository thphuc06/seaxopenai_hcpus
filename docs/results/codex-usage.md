# Recorded Codex build evidence

Git snapshot: `9f55d9e99504273dba987dd3274a9f600a0b4378`.

This report counts recorded receipts, not unique tasks, people, sessions or productivity. A task can have multiple implementation/review/publication receipts. No test totals are summed across runs.

| Lane | Logged receipts | Accepted | Edited | Rejected | S-prefix commits |
|---|---:|---:|---:|---:|---:|
| P1 | 11 | 8 | 3 | 0 | 17 |
| P2 | 6 | 4 | 2 | 0 | 14 |
| P3 | 14 | 10 | 4 | 0 | 6 |
| P4 | 22 | 14 | 8 | 0 | 30 |

Parsed 53 receipt rows. Malformed/unrecognized table rows: none.

## Application history

Non-merge, non-root commits touching backend/, frontend/ or scripts/. Prepared _outside-repo/ tooling and the repository initialization commit are excluded. Times are Git committer timestamps; they are not coding-duration measurements.
Application-path commits: 42.
Runtime/script commits: 34; excludes tests, phase-control files and scripts/dev setup.
- First runtime/script change: 2026-10-31T10:00:26+07:00, `43f444f170a3eb5bcf8ece2679c8b66ca8389649`, S0 P4: skeleton, frozen contracts, stubs (codex).
- Latest runtime/script change: 2026-10-31T15:14:26+07:00, `3fe5302c82e878281d45049e2c71d64984b63afa`, S4 P4: repair deadline wait race and preserve checkpoint records.

## Plan evidence

Explicit Decision markers and discovery paragraphs are text counts, not independently verified decisions or findings.

| Plan | Decision markers | Discovery paragraphs/bullets |
|---|---:|---:|
| P1.md | 13 | 19 |
| P2.md | 27 | 19 |
| P3.md | 43 | 15 |
| P4.md | 7 | 19 |

## Review and fix-loop receipts

The following are matching log rows, not a count of distinct review findings or resolved bugs:
- CODEX_LOG.md:5 — P4, accepted: publish reviewed Phase4 lane checkpoint.
- CODEX_LOG.md:6 — P4, edited: Phase4 Local integration, S4 operational verifier, three self-reviews and trace CCRs.
- CODEX_LOG.md:7 — P4, edited: sync-gate4 contract; three reviews and deadline repair.
- CODEX_LOG.md:8 — P4, edited: sync-gate3, integration corrections and three read-only reviews.
- CODEX_LOG.md:12 — P4, edited: S3 self-review and evaluator corrections.
- CODEX_LOG.md:13 — P4, edited: sync-gate3 contract and three read-only reviews.
- CODEX_LOG.md:14 — P4, edited: sync-gate 2, authorized integration fixes, three read-only reviews.
- CODEX_LOG.md:16 — P4, edited: Phase 2 Stage B: B0/eval/S2 harness and three read-only reviews.
- CODEX_LOG.md:17 — P4, accepted: sync-gate 2 contract + three read-only reviews.
- CODEX_LOG.md:21 — P4, edited: Phase 1 B + CI/Render merge + self-review (3 read-only agents).
- CODEX_LOG.md:23 — P4, accepted: sync-gate 0 + self-review (3 read-only agents).
- CODEX_LOG.md:24 — P1, edited: final self-review + S0 handoff.
- CODEX_LOG.md:26 — P3, edited: self-review + authorized Phase-0 delivery.
- CODEX_LOG.md:39 — P1, edited: S1 Stage B implementation and self-review.
- CODEX_LOG.md:44 — P1, edited: quick self-review + mini-sync PR.
- CODEX_LOG.md:47 — P2, edited: P2-1 Stage B + self-review (3 read-only agents).
- CODEX_LOG.md:53 — P3, edited: Phase 1 self-review with three read-only explorers.
- CODEX_LOG.md:57 — P3, edited: kickoff readiness and local Python path repair.
- CODEX_LOG.md:65 — P4, accepted: sync-gate 1 and automatic self-review (3 read-only agents).

## Unavailable measurements

- Exact chat/thread count: NOT VERIFIED; Git and Markdown do not enumerate sessions.
- Exact skill invocation count: NOT VERIFIED; mentions and planned commands are not executions.
- Distinct /review findings: NOT VERIFIED; use linked gate/review receipts and avoid deduplicating by guesswork.
- Model/token/cost totals: not inferred from logs; use the run accounting reports.

## Reproduction

Run `python scripts/codex_stats.py` from this checkout. Inputs are HEAD history, docs/tracking/CODEX_LOG.md and .agent/plans/P1–P4.md at execution time. Working-tree document edits are included; rerun after integration for submission numbers.
