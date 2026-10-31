# Integration handoff

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
