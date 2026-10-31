# Live API route probe — 31 Oct 2026, 14:48–14:49 ICT

The user authorized a real OpenAI run and switching the local application out of
fallback. The text flow completed through the actual FastAPI routers using
TestClient and the actual OpenAI Responses provider. No provider mocks or replay
responses were used. Input sources were existing SYNTHETIC demo fixtures.

## Successful text flow

| Event | Run | Mode | Status | Model calls | Input/output tokens | Elapsed |
|---|---|---|---|---:|---:|---:|
| 01-bootstrap-demo | run_8d48997eed5d4b92a47002371a93ea78 | LIVE | COMPLETED | 3 | 2695 / 1790 | 15.67s |
| 09-catalogue-published | run_300479e268674b0999b44b0796445da6 | LIVE | COMPLETED | 2 | 2140 / 1334 | 11.66s |

Both runs have null stop_reason. The second includes a real agent:scope_single
request (1161 input / 206 output tokens), model proposals, code anchor validation,
and agent:effect. Code accepted one grounded placement and retained one unsupported
placement as UNKNOWN. Within that run, volume and skin_type changed from UNCERTAIN
to CONSISTENT after scope resolution and code policy evaluation.

Final public fields: volume, skin_type, notification_number and responsible_company
are CONSISTENT; key_ingredients remains UNCERTAIN. All are CURRENT / AUTO_DRAFT.
This is an execution diagnostic, not a gold-based accuracy evaluation.

42 HTTP requests returned200 in the successful probe, covering health, event
catalog/fire, runs/trace, buyer passport/evidence/explain, reviewer history, chain,
graph, BM25 search, review queue, metrics and observability. Both chain checks
returned valid=true. Buyer reads changed no event/job/run/trace/claim/result counts
and made no provider calls. Repeating the bootstrap returned DUPLICATE with no new
work or provider call. No review submission or evidence upload was exercised.

## Initial attempt and spending

An earlier attempt retained PARTIAL LIVE run_7f1b5924ee7640b6a6b5ff7b2de4269a
after two successful Responses requests (1954 input / 1191 output tokens).
The existing diagnostic PassLedger refused an image request with
VISION_TOKEN_COST_NOT_VERIFIED before sending it. This was a diagnostic spending
guard limitation, not an observed OpenAI image rejection. An OPERATOR history read
returned403 as designed; the successful probe used REVIEWER.

The second attempt used LLM_VISION=0, so the model read stored text/transcript
passages. It did not call the fallback extractor for published claims. OCR and web
were off, replay_freeze was false, and the run deadline remained120s.

Both attempts shared one ledger: 7 actual provider attempts, USD1.232422 of
conservative reservations, within30 attempts / USD2. Measured usage totals6789
input /4315 output tokens, estimated USD0.056728 at the configured standard rates;
the successful text flow alone is USD0.040910. These are estimates, not invoices.
Rates checked against the [official model page](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

## Local state and limitations

backend/.env now has LLM_MODE=live; it remains ignored/untracked. LLM_VISION=1,
WEB_SEARCH=off and REPLAY_FREEZE=0 remain unchanged in that file. Restart an already
running backend to load the mode change. Existing live processes were not restarted.
The probe used separate databases, leaving backend/passport.db untouched.

Evidence: .git/live-flow-20261031/report.json (initial),
.git/live-flow-20261031/text/report.json (complete), shared ledger.jsonl,
and .git/live-flow-20261031/text/live.db. The local runner is .git/live_probe.py;
it refuses to rerun against its existing database to prevent accidental repeat spend.

The core Phase3 flow has the needed routes. This does not mean every planned route
is complete: /api/internal/runs/{run_id}/otel still returns501; orders router is
empty; planned Phase4 marketplace/web-search/image routes are absent here.
Fresh image processing, hosted/browser interaction and paid hybrid retrieval remain
NOT VERIFIED. No application code, fixture, gold, policy or public contract changed.

Offline verification: from backend, LLM_MODE=fallback WORKER_INLINE=1 OCR_ENABLED=0,
python -m pytest -q tests/test_guards.py tests/test_run_s3.py tests/test_agent_scope.py
--tb=short: 38 passed,0 failed/skipped/deselected,26 existing Windows temp-cleanup
warnings. Installed: openai3.42.0, FastAPI0.162.0, Pydantic2.14.2, httpx0.28.1.
