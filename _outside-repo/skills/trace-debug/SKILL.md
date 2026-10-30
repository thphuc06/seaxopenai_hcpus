---
name: trace-debug
description: Diagnose a wrong verdict or a failing acceptance test in the Product Truth Passport app from its run trace and decision trail, find the first step where reality diverges from the spec, write a failing test at the lowest level, and fix the root cause in the owning lane (or file a CCR). Also produces the "Codex fix loop" log entry. Use when a field shows an unexpected label, a test like test_hydrating_self_conflict fails, or someone says "why is this verdict", "debug the trace", "sao field này sai".
---

# Trace-driven debugging (the Codex fix loop)

Goal: fix causes, not symptoms. Leave behind evidence a judge can read: failing test → trace inspected → diagnosis → minimal fix → human approval → green.

## Rules
- Expected behaviour comes from the specs (`docs/06-policy-rules.md`, `docs/05-contracts.md`), the fixture's `expect` note, or gold (tests and scripts only). Never take it from the current output.
- **Never** edit a gold label, an expected file, a fixture or a test assertion to make it pass. If you believe the expectation is wrong, stop and ask the human.
- Reproduce in `LLM_MODE=fallback` or `replay`, never `live`.

## Steps
1. **Reproduce.** Run `cd backend; .venv/Scripts/python -m pytest -q -x -k <test>`, or reproduce through the API/in-process: reset, fire the events in order, read the passport as REVIEWER. Write down observed vs expected for the field: verdict, locus, scope, review_state, seller_attributable, freshness.
2. **Find the run.** In-process (FastAPI `TestClient`, as `scripts/sync_check.py` does) call `GET /api/internal/runs` (filter by case), or query the DB; do not start uvicorn yourself (the human can start it from the app Action `backend`): `runs` for the case, ordered by start time. Then load the run's trace steps and `GET /api/products/{pid}/fields/{field}/explain` as REVIEWER.
3. **Walk the decision path in order. Stop at the first divergence.**
   1. Event admitted? Check outcome, reason and stale_fields. Was the revision bumped?
   2. Sources: are the current versions ACTIVE with the expected sha? Is a revoked or superseded one still being used?
   3. Claims for the field: which passage, which quote, readability, extractor (model, fallback or replay), prompt version, mapped_by. Did any claim get dropped (`INVALID_LOCATOR`, injection)?
   4. Scope: source scope and reason, passage scopes (`decided_by`, anchor).
   5. Policy trail (`explain_json`): which rule produced the verdict, and what its inputs were.
   6. Publish gate: was the result blocked, and why?
   7. Was a result version written or re-confirmed? Was a run superseded?
   8. UI: did the label mapping (`labels.ts`) show something different from the API?
4. **Classify and route the cause:**
   - fixture or data problem → P4;
   - extraction, normalisation or vocabulary → P2;
   - scope, policy, gate, admission or route → P1;
   - agent placement → P2;
   - UI mapping → P3;
   - expectation possibly wrong → human.
5. **Write the smallest failing test that shows the cause**, at the lowest level. Use a unit test in the owner's test file, with a synthetic input built in the test rather than demo text. If the owner is another lane, put the test and the fix proposal in a CCR.
6. **Fix the root cause** (only in your lane). Prefer a mechanism over a special case. Then re-run:
   - the new test and the original failing test;
   - the whole current-phase suite;
   - one blind product that exercises the same rule (`scripts/blind_eval.py`, from Phase 3 on; before that, a variant
     input built in the test), to check the fix is not overfitted.
7. **Log the loop** in `docs/tracking/CODEX_LOG.md` under "Notable loops":
   ```
   ### Loop <n> — <title>
   Failing test: <name> · Run inspected: <run id> (steps <seq…>)
   Diagnosis: <first divergent step and why, 1–2 lines>
   Fix: <files, summary> · Test added: <name>
   Human reviewer + decision: <name, approved/edited>
   Rerun: <suite result>, blind check: <result>
   ```
8. **End** with the AGENTS.md §6 report.
