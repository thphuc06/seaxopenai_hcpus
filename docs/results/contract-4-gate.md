# Contract 4 gate — 31 Oct 2026

P4 Local, phase3 fallback/inline with OCR, web and tracing disabled. PHASE stays3;
this checkpoint does not complete Phase4 implementation. No server or provider
request was started by this gate. Original gold and first-run results are unchanged.

## Validation strategy

The initial unchanged-main full suite reported1340 passed,1 failed,5 future-phase
skips,+2 passing subtests,0 collection errors/deselections. The failed node was
test_llm_client.py::test_expired_deadline_blocks_api_and_recording: output usage0
instead of10. Its failure receipt is preserved in .git/contract-4-p4-check.xml.
P2's separately reported evaluator timeout did not reproduce in this full run.

The user explicitly authorized P4 to repair the P2 client. The fix captures an
absolute monotonic wait deadline before worker submission, retaining elapsed
scheduling time, usage accounting and post-response deadline rejection. Existing
assertions remain intact; new live/record variants check usage, error trace and
absence of recording writes. Client/budget/guards:52 passed,0 failed/skipped/
deselected. Read-only review found no blocker in the fix or P1/P2 contracts.

The user then explicitly instructed reusing completed checks and publishing as
soon as possible. The redundant second full baseline was stopped and is not
claimed as a completed suite. Reuse the1340 passing nodes, execute the repaired
client/budget/guards and the P1 affected/new contract suites, and check fixtures
and the phase3 story. This is incremental evidence, not one green full-suite run.
No assertion, phase marker, fixture, gold label or gate configuration was changed.

## Integration

P4 repair/records3fe5302 accepted via392a9e9. P1 contract0539dc7 introduces nine
typed S4 route operations and transport schemas; authorized calls remain501
until Stage B. P2 contractf17affe changes only its plan; web/OCR signatures remain
unchanged. All prior lanes were in sync-3, so no late branch is required. No
frontend code or lockfile changes; no frontend rebuild is needed.

Fixture validation:98 files,0 failed. In-process sync_check3 fallback:29 PASS,
0 FAIL/SKIP. P1 affected/new contracts plus S3 wire:225 passed,0 failed/skipped/
deselected in140.75s. P1 accepted viaa27790d; P2 documentation via78b2b7e reuses
the unchanged code's checks. Union of initial baseline and superseding focused
JUnit outcomes:1367 passed,5 future-phase skips,0 unresolved failures/errors;
two passing subtests remain separately recorded. Gate passed15:20 ICT.

## Reproduction and limits

From backend use .venv/Scripts/python, CONTEST_PHASE=3, LLM_MODE=fallback,
WORKER_INLINE=1, OCR_ENABLED=0, WEB_SEARCH=off, AGENTS_TRACING=0 and
OPENAI_AGENTS_DISABLE_TRACING=1. Node24 is on PATH for the existing wire test.

    .venv/Scripts/python -m pytest -q tests/test_llm_client.py tests/test_llm_budget.py tests/test_guards.py
    .venv/Scripts/python -m pytest -q tests/test_orders_contract.py tests/test_skeleton.py tests/test_events_contract.py tests/test_reviews_contract.py tests/test_glassbox_contract.py tests/test_guards.py ../frontend/tests/test_s3_contract.py
    .venv/Scripts/python ../scripts/check_fixtures.py
    .venv/Scripts/python ../scripts/sync_check.py 3 --mode fallback

JUnit receipts are .git/contract-4-fix.xml and .git/contract-4-p1.xml; stdout is
saved alongside each receipt. Dedicated basetemp paths isolate runs. The initial
full invocation emitted27 Windows temp-cleanup warnings; these are not hidden.
Provider replay, browser interaction and S4 functional implementation are NOT
VERIFIED by this checkpoint. Existing R3 projection, paid indexing and fresh-image
follow-ups remain with their owners. No scope cut or WAITING classification.
