# Recorded Codex build evidence

Git snapshot: `6f6e7ea30c131b2059da9562985b0aabf7ae4644`.

Captured1November2026 at18:34 ICT, before adding the current repository-closeout receipt to CODEX_LOG. This is a dated snapshot, not a live count; later log/plan changes require a new report.

This report counts recorded receipts, not unique tasks, people, sessions or productivity. A task can have multiple implementation/review/publication receipts. No test totals are summed across runs.

| Lane | Logged receipts | Accepted | Edited | Rejected | S-prefix commits |
|---|---:|---:|---:|---:|---:|
| P1 | 12 | 9 | 3 | 0 | 21 |
| P2 | 7 | 4 | 3 | 0 | 20 |
| P3 | 15 | 11 | 4 | 0 | 14 |
| P4 | 27 | 15 | 12 | 0 | 37 |

Parsed 61 receipt rows. Malformed/unrecognized table rows: none.

## Application history

Non-merge, non-root commits touching backend/, frontend/ or scripts/. Prepared _outside-repo/ tooling and the repository initialization commit are excluded. Times are Git committer timestamps; they are not coding-duration measurements.
Application-path commits: 61.
Runtime/script commits: 50; excludes tests, phase-control files and scripts/dev setup.
- First runtime/script change: 2026-10-31T10:00:26+07:00, `43f444f170a3eb5bcf8ece2679c8b66ca8389649`, S0 P4: skeleton, frozen contracts, stubs (codex).
- Latest runtime/script change: 2026-10-31T16:39:24+07:00, `5eff409bef5215eef32ebb22a0964ae539a18b93`, S5 P1: check pinned web context atomically before source ingestion (codex).

## Plan evidence

Explicit Decision markers and discovery paragraphs are text counts, not independently verified decisions or findings.

| Plan | Decision markers | Discovery paragraphs/bullets |
|---|---:|---:|
| P1.md | 14 | 21 |
| P2.md | 27 | 28 |
| P3.md | 55 | 18 |
| P4.md | 8 | 20 |

## Review and fix-loop receipts

The following are matching log rows, not a count of distinct review findings or resolved bugs:
- CODEX_LOG.md:9 — P4, edited: sync-gate4 integration and quick repairs.
- CODEX_LOG.md:13 — P4, accepted: publish reviewed Phase4 lane checkpoint.
- CODEX_LOG.md:14 — P4, edited: Phase4 Local integration, S4 operational verifier, three self-reviews and trace CCRs.
- CODEX_LOG.md:15 — P4, edited: sync-gate4 contract; three reviews and deadline repair.
- CODEX_LOG.md:16 — P4, edited: sync-gate3, integration corrections and three read-only reviews.
- CODEX_LOG.md:20 — P4, edited: S3 self-review and evaluator corrections.
- CODEX_LOG.md:21 — P4, edited: sync-gate3 contract and three read-only reviews.
- CODEX_LOG.md:22 — P4, edited: sync-gate 2, authorized integration fixes, three read-only reviews.
- CODEX_LOG.md:24 — P4, edited: Phase 2 Stage B: B0/eval/S2 harness and three read-only reviews.
- CODEX_LOG.md:25 — P4, accepted: sync-gate 2 contract + three read-only reviews.
- CODEX_LOG.md:29 — P4, edited: Phase 1 B + CI/Render merge + self-review (3 read-only agents).
- CODEX_LOG.md:31 — P4, accepted: sync-gate 0 + self-review (3 read-only agents).
- CODEX_LOG.md:32 — P1, edited: final self-review + S0 handoff.
- CODEX_LOG.md:34 — P3, edited: self-review + authorized Phase-0 delivery.
- CODEX_LOG.md:47 — P1, edited: S1 Stage B implementation and self-review.
- CODEX_LOG.md:52 — P1, edited: quick self-review + mini-sync PR.
- CODEX_LOG.md:55 — P2, edited: P2-1 Stage B + self-review (3 read-only agents).
- CODEX_LOG.md:61 — P3, edited: Phase 1 self-review with three read-only explorers.
- CODEX_LOG.md:65 — P3, edited: kickoff readiness and local Python path repair.
- CODEX_LOG.md:73 — P4, accepted: sync-gate 1 and automatic self-review (3 read-only agents).

## Unavailable measurements

- Exact chat/thread count: NOT VERIFIED; Git and Markdown do not enumerate sessions.
- Exact skill invocation count: NOT VERIFIED; mentions and planned commands are not executions.
- Distinct /review findings: NOT VERIFIED; use linked gate/review receipts and avoid deduplicating by guesswork.
- Model/token/cost totals: not inferred from logs; use the run accounting reports.

## Reproduction

For a new measurement, run `python scripts/codex_stats.py --output docs/results/codex-usage-new-snapshot.md` from this checkout, choosing an unused dated filename. Inputs are HEAD history, docs/tracking/CODEX_LOG.md and .agent/plans/P1–P4.md at execution time. Working-tree document edits are included, so current counts can differ from this frozen report. Always pass `--output`; the script's default would overwrite the historical contest report.
