# Contract-3 gate — 31 Oct 2026

Completed retained phase2 gate at13:42 ICT. PHASE remains2; no S3 completion claim.
User explicitly excludes uncommitted P4 Stage-B work. All79 WIP files were saved
in stash b2cd7055155ea18e76dece60102b9caea6b5e665 with a byte-hash manifest and
original P4 plan under .git. Existing p4 commit30627cb was pushed before integration.

| Gate | Passed | Failed/errors | Skipped | Deselected | Passing subtests |
|---|---:|---:|---:|---:|---:|
| Fresh main baseline before P1 |1044|0|14|0|2|
| P1 cb9f05f post-merge |1090|0|14|0|2|
| Fresh accepted-main baseline before P2 |1090|0|14|0|2|
| P2 e8eb571 post-merge / final combined suite |1090|0|14|0|2|
| Separate guards |4|0|0|0|0|

All14 skips are unchanged future-phase markers:9 phase3 and5 phase4. No current
phase WAITING failure. Node/outcome comparisons report0 missing/regressed passing
nodes for both merges. P1 accepted as6c3e661; P2 accepted as6e73f1f. Both merges
used --no-commit --no-ff and committed only after the applicable checks passed.

From backend, set process-local CONTEST_PHASE=2, LLM_MODE=fallback,
WORKER_INLINE=1, OCR_ENABLED=0, WEB_SEARCH=off, AGENTS_TRACING=0 and
OPENAI_AGENTS_DISABLE_TRACING=1. Each of the four suite runs used:

    .venv/Scripts/python -m pytest -q --tb=short -rs --basetemp=.venv/contract-3-<stage> --junitxml=../.git/contract-3-<stage>.xml

Stages are pre-p1, post-p1, pre-p2 and post-p2. Additional final checks:

    .venv/Scripts/python -m pytest -q tests/test_guards.py --tb=short --basetemp=.venv/contract-3-guards
    .venv/Scripts/python ../scripts/check_fixtures.py
    .venv/Scripts/python ../scripts/sync_check.py 2 --mode fallback

Fixture validator53/53; isolated sync path26/26. No frontend change, so no build
required. No provider request, server startup, dependency update, test/fixture/gold
edit, PHASE change or scope cut. P4 has no new shared contract; P3 is already in main.
Six P1 routes are authorized501 stubs, not working S3 features. P2 adds a plan only.
Tagged HANDOFF records contracts, limits and remaining owner work. Review/logs and
WIP restoration follow publication without moving the tag.
