# Integration handoff

## contract-1

Mini-sync contract gate passed at 10:50 ICT, 31 Oct 2026 (T+0:50).
PHASE remains 0. This is the shared Stage-A checkpoint, not S1/M1 completion.
All three contract lanes included; no phase-0 failures or regressions. Fetch tags
and merge contract-1 into each lane before explicitly continuing Stage B.

### Integrated checkpoints
- P4: 3c6f3c4 contract plus 108315e publication receipt and f3b7d8d gate preparation,
  merged via 205c76f. Fourteen phase(1) acceptance nodes and failure-only WAITING
  annotation; existing gating/guards/assertions unchanged. User approved direct
  public publish.gate testing for AC-16; do not patch its implementation.
- P1: 490255b contract plus d7df2b8 publication receipt and f9ea7a5 contract-only
  self-review tests, merged via d43efa0. Eleven S1 routes with response schemas,
  identity/role checks and 501 business stubs; 79 contract tests. Transport DTOs
  remain in api/contracts.py; shared PassportResponse is unchanged. Arrays for
  product/catalog/event/run lists; evidence {citations, hidden_citations}; run
  detail {run, steps}; optional presentation/metadata may be null. See docs05
  As-built and OpenAPI. P3 must handle null presentation explicitly.
- P2: 1abd79d documentation-only CONTRACT_NO_CHANGE, merged via 062c22c.
  Existing Budget/client/extract/normalize signatures retained; four-mode client,
  fallback extraction and normalization implementation remain Stage B.
- P3 was already included at sync-0; no late S0 lane to recover. Dataset and
  CI/Render worktrees were not integrated or modified by this mini-sync.

### Checks and limits
Fresh phase-0 baseline/post-merge suites including frontend wire-contract test:
P4 141→141 passed (0→14 future-phase skips), P1 141→220 passed (14 skips),
P2 220→220 passed (14 skips). Every run: 2 passing subtests, zero failed/errors/
deselected. Compared JUnit node/outcome evidence in .git/contract-1-*.xml before
each merge commit; all prior passing nodes retained. Final guards 4 passed;
fixture validator 9 files/0 errors; backend collection 233/no import errors.
No frontend edit/build, no server start or paid call. sync_check.py remains absent
and NOT VERIFIED at this phase-0 contract gate. Full S1 functional/live/replay and
browser behavior are NOT VERIFIED.

Diagnostic phase-1 acceptance: 1 passed (buyer POST ACL), 12 failed at explicit
501 stubs, 1 skipped (AC-01 real Foaming capture due P4-2b), zero deselected/errors.
These pending tests do not pass yet; required Stage-B code has not been merged:

| Pending node in backend/tests/test_acceptance.py | Missing work |
|---|---|
| test_demo_bootstrap | P1/P2 Stage B after 490255b/1abd79d |
| test_price_change_noop[changed0] | P1/P2 Stage B |
| test_price_change_noop[changed1] | P1/P2 Stage B |
| test_price_change_noop[changed2] | P1/P2 Stage B |
| test_duplicate_event_idempotent[02-price-change-03-duplicate-price-change] | P1/P2 Stage B |
| test_duplicate_event_idempotent[01-bootstrap-demo-01-bootstrap-demo] | P1/P2 Stage B |
| test_wrong_market_excluded | P1/P2 Stage B |
| test_buyer_read_only | P1/P2 Stage B |
| test_rejected_producer | P1 admission Stage B |
| test_old_run_no_overwrite | P1 public publish gate + P2 extraction Stage B |
| test_no_authenticity_claims | P1/P2 Stage B |
| test_citations_valid | P1/P2 Stage B |

Open CCR P1→P4: producer/type allowlist and non-material event-field settings in
config.py are needed for Stage B. No config change in this mini-sync. Collection
DTO promotion into models.py is unnecessary now: retain the concrete P1-owned
transport schemas for P3. Existing policy/budget contracts and WEB_SEARCH=off stay.

Reproduce from backend with CONTEST_PHASE=0, LLM_MODE=fallback, WORKER_INLINE=1,
OCR_ENABLED=0 and bundled Node 24 on PATH: `.venv/Scripts/python -m pytest -q tests
../frontend/tests/test_backend_contract.py`, then guards and check_fixtures.py.
For diagnostic pending targets use CONTEST_PHASE=1 and tests/test_acceptance.py.
No scope cut. Phase 1 deadline remains 11:45 ICT; continuation is a separate task.

## sync-0

Gate passed at 10:32 ICT, 31 Oct 2026 (T+0:32). Phase 0 complete; PHASE remains 0.
All lanes included; no WAITING tests, omitted lanes or scope cuts. Phase 1 ends 11:45 ICT.
This section is committed before tagging. Fetch tags and merge sync-0 into each lane.

### P4 — skeleton, fixtures and integration
- Shared settings/models/health/stubs and pinned Python environment were already on main.
- P4-0c e0e6291 already includes S1, four events, validator and five DRAFT labels; no second merge needed.
- Final gate: 141 Python tests + 2 subtests passed (140 backend + 1 frontend wire-contract test), guards 4/4, collection 140; zero failed/skipped/deselected.
- Fixture validator: 9 files, zero errors. Temporary-DB startup: health 200; 1 product, 1 case, 4 sources/versions, 14 passages; repeat seed returns False.
- Gold remains DRAFT pending human review. Prepared-before-event tools under _outside-repo remain intact.

### P1 — storage and trace
- Integrated origin/p1 235d002 via aba96f1: SQLite schema, generic seed/store, persistent trace, variant tests and docs04 As-built.
- Fresh baseline/post-merge: 66 → 80 passed, 2 subtests after merge; zero failed/skipped/deselected.
- Existing signatures retained; explicit DB overrides remain optional, defaults use current shared settings.
- Startup/seed now verified with the actual S1 fixture. Business routes/policy/publishing remain Phase-1 work; no S0 CCR.

### P2 — smoke and AI foundation
- Integrated origin/p2 685819d via bfe76f8: typed builder/client scaffold, model price data, capped smoke and shared run/agent budget.
- Fresh baseline/post-merge: 80 → 140 passed, 2 subtests; zero failed/skipped/deselected.
- P2's committed report records successful observations for all eight smoke categories, with the initial web SKIP and brand-domain FAIL preserved; alternate-domain web PASS. Gate did not repeat paid smoke.
- Retain MODEL_CALL_LIMIT / TOOL_CALL_LIMIT / RUN_DEADLINE; child codes unchanged. Keep WEB_SEARCH=off and existing run/agent caps. P2's measured model/effort recommendation is in docs07; local .env was not changed.
- P2 must use Python 3.11/3.12 for shared OCR setup; production four-mode parse remains S1 work.

### P3 — frontend mock
- Integrated origin/p3 d38c700 via c8e431f: five route shells, buyer mock, typed role-aware client, wire projection and approved charcoal/orange theme.
- Fresh backend baseline/post-merge: 140 → 140 passed, 2 subtests; zero failed/skipped/deselected. Additional strict wire test passes in the final 141-test gate.
- Node 24.22.1: 23 frontend tests pass; API and mock builds pass. VITE_USE_MOCK is now documented in shared README §7.5.
- S1 CCR P3→P1/P4: define collection DTOs and live mode/hidden-citation-count metadata. Current preview carries separate PassportMetadata; no Phase-0 backend schema change.

### Reproduction and limits
From backend, set CONTEST_PHASE=0, LLM_MODE=fallback, WORKER_INLINE=1, OCR_ENABLED=0,
then run `.venv/Scripts/python -m pytest -q tests ../frontend/tests/test_backend_contract.py`,
`-m pytest -q tests/test_guards.py`, `-m pytest --collect-only -q`, and
`.venv/Scripts/python ../scripts/check_fixtures.py`. Frontend requires Node >=24:
`npm ci --prefer-offline`, `npm test`, `npm run build`, then build with VITE_USE_MOCK=1.
The Windows system Node 22.15.1 produced 1 pass/5 loader failures; selecting installed
Node 24 resolved them without changing tests. This checkout used the bundled runtime
at C:/Users/Tran Hoang Phuc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin.
JUnit node/outcome evidence is local under .git/s0-*.xml; all baseline nodes were retained.
Three read-only self-review agents found no blocking rules/contracts/overfitting issue.
Pytest temp-cleanup warnings and two React Router bundler warnings are recorded, not suppressed.

NOT VERIFIED: scripts/sync_check.py does not exist at S0 and was skipped as allowed;
no automated browser E2E or new live API smoke in this gate. P3 reports prior human
mock visual approval. Human starts backend/frontend Actions for the local click path;
the agent started no server. Previous-tag review is inapplicable at S0.
