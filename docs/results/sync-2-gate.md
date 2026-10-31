# S2 integration gate — 31 Oct 2026

Final gate status is recorded in docs/tracking/HANDOFF.md under sync-2.

## Inputs and recovery

Checked pushed heads: P4 47d3bdb (PR8), P1 4092531 (PR9), P2 07572e7
(PR11), P3 e840855 (PR10). PR11's head was verified using Git's pull-request ref;
the unauthenticated GitHub API was rate limited. No additional PR was created.
The main checkout was clean at entry; no textual merge conflict occurred.

P4-only merge trial: fresh phase1 baseline679 passed/44 skipped/+2 subtests;
post776 passed/1 failed/43 skipped/+2 subtests. Newly available REAL R2 exposed
AC-01 before P1/P2 implementation. The merge was aborted. P1 trial: fresh
baseline679/44/+2, post980/43/+2, no failing tests; aborted when review proved
the claims scope defect. All prior passing baseline nodes were retained.

Combined latest-head diagnostic: phase2 1047 passed, 2 failed, 14 skipped,
2 subtests passed; zero errors/deselected. Both failures had passed in the
P1 phase1 trial. Combined trial was aborted, preserving all lane commits.
P3 then passed its independent fresh phase1 baseline/post gate679/44/+2,
extra S2 wire contract+guards5, API build and Node51; merge e95ee38 is retained.

The user explicitly authorized immediate fixes and a passing tag push at T+3:00.
P1/P2/P4 were then integrated as one dependent backend bundle, retaining all
three original heads and applying the narrow corrections below. This order
deviation avoids accepting an intermediate combination with a known regression.
No assertion, gold label, original fixture, skip marker or pytest configuration
was changed to make the gate pass. PHASE advances only at the final S2 gate.

## First divergences and fixes

1. AC-01, key_ingredients: an INCI name remained a literal while highlights
   normalized its broader family, producing an artificial WITHIN_SOURCE result.
   Added two source-noted hyaluronate names to the existing family vocabulary.
   CIR Table1 definitions support family membership; this does not infer equal
   concentration, performance, or product composition. Source URL/date is in
   vocab_seed.json and docs07. New tests cover both names/casing and an unknown
   ingredient negative control. The retained REAL assertion is unchanged.
2. Gift trace: P2 filtered a gift quantity before P1's per-claim scope check, so
   the exclusion lost its GIFT_CONTEXT trace. The run now traces removed raw
   quantities using the existing volume/scope helpers and the stored passage id.
   No quantity/verdict special case; tests use unrelated quantities/languages.
3. Claims scope: expansion copied one MATCH observation onto all source passages.
   A real store→audit→policy→publish diagnostic published a CONFLICTING alcohol
   claim from a persisted MISMATCH passage. Audit now reuses infer_scope with
   current source-version metadata and placements for each expanded passage.
   MISMATCH is excluded; UNKNOWN/AGENT remain unresolved. Tests vary observation
   order and use real policy/publication. No model decides the outcome.

New regressions initially failed10/10. The first fixed run passed95/99: four new
publication checks exposed a missing revision in the test setup, and publication
correctly returned SUPERSEDED_RUN. Pinning that synthetic run to its context
revision fixed the setup without changing an assertion. Focused final gate99/99
passed, including the original failures, new10, normalization/claims and guards.
Three read-only reviewers rechecked the actual final corrections and found no
remaining blocker. An inherited blank final line in P1's ExecPlan is cosmetic.

Versions: policy-v1.6, claims-v2-passage-scope, fallback-v4,
coverage-v3-ingredient-family. Existing recordings are unchanged; old normalized
extraction caches are not reused. No route, schema signature, env switch or new
dependency was introduced. Pydantic2.14.2 and pytest9.2.0 official docs were checked.

## Reproduction

From backend with bundled Node24.22.1 on PATH, LLM_MODE=fallback,
WORKER_INLINE=1, OCR_ENABLED=0, WEB_SEARCH=off, AGENTS_TRACING=0 and
CONTEST_PHASE=2 (PowerShell process environment):

    .venv/Scripts/python -m pytest -q tests ../frontend/tests/test_backend_contract.py ../frontend/tests/test_s1_contract.py ../frontend/tests/test_s2_contract.py ../scripts/dev/render/tests --tb=short -rs
    .venv/Scripts/python -m pytest -q tests/test_guards.py
    .venv/Scripts/python ../scripts/check_fixtures.py
    .venv/Scripts/python ../scripts/sync_check.py 2 --mode fallback

Frontend: npm test; VITE_USE_MOCK=0 npm run build (set the environment in
PowerShell). Per-run logs and JUnit outcomes remain local under .git/s2-*.

All gold remains DRAFT. Full provider replay, fresh-image transcription, human
gold approval and the real browser click path are NOT VERIFIED by this offline
gate. P2's paid pass1 and canon hook, P3's time travel/claim-count display remain
reported follow-ups; no paid call or server was started here.
