# Development log — 31 Oct 2026

## P4 Phase 2 Stage B — local implementation (12:00 ICT, T+2:00)

User authorized continuation after verifying contract-2/2811f3b was already in clean
p4/f6955ce. Delivered pure B0, isolated offline eval with separate DRAFT/REVIEWED
metrics, immutable timestamped reports, and S2 operational path. No sync-gate,
cross-lane BUILD merge, commit/push, model provider call or gold change in this task.
Existing PHASE remains 1. P4-2b real capture/blind drafting remains separate.

Owned tests and original evaluator smoke: 110 passed, zero failed/skipped/deselected.
Final phase-1 regression: 747 passed, 44 skipped, 2 subtests; zero failures/errors/
deselections. Three read-only reviewers rechecked the fixes with no remaining P4
blocker. Fixture validator: 37/37. Final phase-2 suite: 757 passed, 16 owner-WAITING
failures, 18 skipped, 2 subtests passed, zero errors/deselections. Full S2 acceptance
still awaits P1/P2 BUILD; the exact ledger is retained in P4 ExecPlan, without test changes.

Report: docs/results/eval-latest.md and .json, all 13 checkpoints, raw DRAFT B0
16/65 versus candidate 51/65; false-blame 2/57 versus 0/57, reviewed 0/0. Scores include
literal preconditions, including a future registry path, and are not S2 success.
Unexpected rejected events 06/09/10 are marked errors; eval exits 1. S2 sync path
passes all 17 S1 steps then fails revoke re-assessment. Replay diagnostic hits
REPLAY_MISS, retains that attempt and clearly restarts fallback; full replay remains
unverified. See docs09 for baseline shared-extraction and scoring limitations.

## contract-2 — published 11:49:48 ICT (T+1:49)

Explicit early mini-sync; main and contract-2 remote SHA verified as 2811f3b.
PHASE remains 1. All contract lanes included; no WAITING failure, regression,
omitted lane or cut. S2 remains unfinished. Tagged HANDOFF contains the receipt.

- P4: Done — saved prior Stage-A plans, pushed f8808e3, ran ordered gates and
  published handoff. Blocked — none for this checkpoint. Surprise — Windows
  switch briefly failed to unlink P4.md; verified the file exactly matched
  committed contract-2, restored only that file to p4 HEAD and retried the
  fast-forward successfully. No work discarded. Decision — retain PHASE=1 and
  DRAFT gold. Next — B0/eval and S2 sync path on separate continuation.
- P1: Done — c1d7a5a adds four typed S2 route stubs, role gates and 39 contract
  cases; docs05 carries payloads. No S1 gate failure. Next — Stage B lifecycle,
  reviews/evidence and carried budget/reset CCRs.
- P2: Done — 15bcca4 records unchanged shared contracts; no application delta.
  Decision — preserve Budget/parse/extract/audit signatures. Next — Stage B
  vision/retry/claims and P1 reset identity coordination.
- P3: existing S1 work retained; no contract merge or frontend change required.
  Next — consume generated S2 DTOs from contract-2.

Checks: phase1 P4 baseline/post 640/640; P1 640/679; P2 679/679 passed.
Every run: 44 skipped, 2 passing subtests, 0 failed/errors/deselected. Per-node
JUnit comparison shows no lost/regressed pass. Final guards 4, fixtures 37,
sync path 17 all passed. Skips: 43 future-phase nodes plus AC-01 real R2 pending
P4-2b. No new build required. Final cleanup warnings: 23, Windows WinError 145.

Three read-only reviewers found no introduced rules/contracts/overfitting blocker.
Preserved prior user waiver of separate /review; review-base points to sync-1
locally. UI remains human-run via Actions. CCR P4→P1: reconcile stored
evidence_requests CLOSED with history DTO OPEN/FULFILLED before implementing
history; do not blindly serialize closed rows. This is a Stage-B integration
note, not a failing behavior of intentional 501 stubs.
NOT VERIFIED: S2 completion, browser path, full-story replay, human gold approval.

## sync-1 — 11:33:58 ICT (T+1:33), complete for S1 scope

Published main and sync-1 at be91b3bd0051568d4795801b438409326ac51dc3;
remote SHA and tagged HANDOFF/PHASE=1 verified. Returned p4 to the tag. User chose
automatic review, waived separate /review and explicitly prohibited Phase 2 kickoff.
Three read-only reviewers confirmed the final tag has the reviewed code, no S1
blocker and unchanged DRAFT gold. review-base is local-only at sync-0.

- P4: Done — acceptance/helpers, auxiliary dataset and CI/Render package integrated;
  ordered gate, tagged handoff and operational logs. Blocked — no S1 gate blocker.
  Surprise — system Node remains 22; bundled Node 24.22.1 is required. Decision —
  retain all plan history, 13 DRAFT gold checkpoints and existing fixture deferral.
  Next — human combined UI click path/gold review; no next-phase work in this task.
- P1: Done — admission/jobs/run/policy/publication and eleven S1 routes. Blocked —
  no S1 failure. Surprise — budget exhaustion with zero results selects FAILED;
  Phase-2 test already requires PARTIAL. Decision — explicit P1 CCR in ISSUES,
  retain assertions; policy-v1.1/ACROSS_SOURCES recorded in D008. Next — owner fix
  at S2 and source-ID/reset recording agreement with P2.
- P2: Done — four modes, complete replay key, fallback/extract/cache, normalization
  and robustness tests. Blocked — no S1 failure. Surprise — lane's successful
  capped record required a Windows terminal-encoding fix, documented with regression.
  Decision — count only reported one paid call (USD0.00749); gate used none.
  Next — shared reset-story replay is not established by isolated listing replay.
- P3: Done — buyer evidence/private filtering/polling, Operator events/counters/runs,
  generated API types and API build. Blocked — no S1 failure. Surprise — npm ci
  reports 3 moderate advisories; two existing Router warnings persist. Decision —
  no forced pin changes; set VITE_USE_MOCK=0 for human integrated Actions check.
  Next — human combined UI click path; earlier 501 WAITING is superseded by this gate.

Fresh phase-0 baseline→post-merge: P4 220→276 passed (14→57 skips), P1 288→394
(57→156 skips), P2 394→527 (156 skips), P3 527→527 (156 skips). The P1 baseline
adds 12 newly available hosted-adapter tests. Every run adds 2 passing subtests;
zero prior passing nodes lost, failures/errors/deselections or merge conflicts.
JUnit node/outcome evidence remains local in .git/s1-*.xml.

Final phase-1 combined suite: 640 passed, 44 skipped, 2 subtests, 0 failed/errors/
deselected. Skips: 43 future-phase tests and AC-01 R2 Foaming capture due S2.
Separate guards 4 passed; fixture validator 37/37; sync_check 1 fallback 17/17 PASS;
frontend npm test 37 passed and API build passed after npm ci. No omitted lanes,
WAITING failures or new cuts. No assertion/fixture label changed by this gate.
The original gold checkpoint and all prior ExecPlan text survived integration.

NOT VERIFIED in this gate: human browser path, hosted deployment, full reset-story
replay and human gold approval. P3's prior offline browser report is retained as
lane evidence, not rerun here. No servers or model calls started. Later logs do
not move sync-1; Phase 2 remains pending an explicit new instruction.

## contract-1 — 10:50 ICT (T+0:50), contract gate passed

- P4: phase-1 acceptance checkpoint and reporting support integrated; direct
  publish.gate AC-16 test authorized by user. Stage B tests/scripts remain next.
- P1: typed S1 routes/DTOs, role checks and 79 contract tests integrated through
  f9ea7a5. Business handlers explicitly return 501. Producer configuration CCR
  goes to P4 Stage B; keep transport DTOs in api/contracts.py for P3.
- P2: 1abd79d confirms CONTRACT_NO_CHANGE; shared interfaces exist, production
  client modes/extraction/normalization remain next.
- Fresh baseline/post-merge: P4 141→141, P1 141→220, P2 220→220 passed, each +2
  subtests. After P4, 14 phase-1 skips; zero phase-0 failures/errors/deselections.
  Per-node comparisons retain all prior passing tests. Guards 4; fixtures 9/9;
  backend collection 233. No conflicts or omitted contract lane.
- Diagnostic S1 acceptance: 1 passed, 12 failed at 501, 1 missing-real-fixture
  skip; no S1 completion claim. Exact pending nodes in tagged HANDOFF contract-1.
- PHASE stays 0. No Stage B, CI/Render, dataset, frontend, paid smoke or server
  work in this task. sync_check absent/NOT VERIFIED. No scope cut.

## sync-0 — 10:32 ICT (T+0:32), complete

- P4: Done — ordered lane merges, handoff/tag 62f759a and p4 published. Blocked — none.
  Surprise — system Node 22 below frontend requirement. Decision — use bundled Node 24;
  PHASE stays 0. Next — Phase-1 acceptance contract, fixtures and human gold review.
- P1: Done — generic storage/seed/trace and actual S1 startup. Blocked — none.
  Surprise — settings defaults/Python 3.11 fixes already in lane. Decision — preserve
  signatures. Next — events, policy, publication and business routes.
- P2: Done — smoke report, builder/client stub, shared budgets. Blocked — none in S0.
  Surprise — alternate-domain web succeeded after brand-domain failure. Decision — keep
  WEB_SEARCH=off/current caps. Next — four-mode client/extraction; Python 3.11/3.12 for OCR.
- P3: Done — five routes, mock passport, transport and approved theme. Blocked — none.
  Surprise — Node 22 failed five test modules; Node 24 passes unchanged tests.
  Decision — document VITE_USE_MOCK. Next — S1 metadata/collection contracts, API integration.

Baseline/post merge: P1 66→80, P2 80→140, P3 140→140 passed; all prior nodes retained.
Final Python 141 passed + 2 subtests, guards 4, collection 140, Node 23, fixtures 9/9;
all final suites 0 failed/skipped/deselected. API/mock builds pass. Temporary DB:
health 200, product/case/source/version/passage counts 1/1/4/4/14; repeat seed False.
Python 3.11.1 / Node 24.22.1; no pins changed. Windows temp-cleanup and two bundler
directive warnings remain visible. Three self-review agents found no blocker.
No cuts, omitted lanes or WAITING. sync_check.py absent and NOT VERIFIED at S0;
no browser E2E/new paid smoke/server start. P2 live evidence comes from its report.
No previous-tag review at S0. Human starts backend/frontend Actions for local click path.
Handoff is included in sync-0; later logs do not move the tag. Phase 1 ends 11:45 ICT.

- 10:04 ICT (T+0:04): P4-0c created the first S1 synthetic dataset, four events and
  DRAFT bootstrap labels. Validator 9/9 files passed; 29 new tests passed; full suite
  66 passed with two pytest temp-cleanup warnings. No pipeline run or model call.
  P1 can load fixtures/synthetic/s1-gentle-cleanser after merging this delivery.

- 09:49 ICT (T-0:11): user confirmed organizers permit coding now; started P4-0.
- Prepared materials: docs, prompts, plan templates and tools under `_outside-repo/skills`
  existed before the event. Application implementation begins in this task.
- Phase 0: Python 3.13 dependency attempt rejected by RapidOCR metadata. Use Python
  3.11 (available locally); setup accepts 3.11/3.12. S0 integration remains pending.
- 10:01 ICT (T+0:01): skeleton 43f444f pushed to main; remote SHA verified. Pytest
  37 passed, 0 failed/skipped/deselected, including 4 guards. Dependency consistency,
  contract imports and idempotent Windows PowerShell 5.1 setup passed. Local environment
  file includes backend/frontend/tests/sync_check Actions; UI appearance unverified.
