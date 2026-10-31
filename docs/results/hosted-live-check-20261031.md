# Hosted LIVE verification — 31 October 2026, 16:25–16:27 ICT

User requested a server check after Render deployment. One existing REAL Foaming
bootstrap event was submitted through the public Sites proxy; no reset, duplicate
submission, env mutation, recording or additional model run was performed.

Both Render and Sites health endpoints returned live / phase4 / policy-v2.1 with
configured extract/agent/cheap model gpt-6.1-sol. The deployed backend now starts.

Run `run_b754deaaec8e47938373038bb1a2ddda`, case REAL-CASE-R2, event REAL-EVT-15,
job job_ef7572bb6e144fa7bece8f694ed559bf:

- Admission: ADMITTED. POST completed in about100 seconds; no HTTP retry.
- Mode LIVE,13 model calls,52718 input tokens,9544 output tokens.
- Trace:17 LLM step entries (not17 unique calls); zero replayed steps and zero
  fallback mode/extractor steps. Code steps remain code, as designed.
- Web audit:2 LIVE queries,2 stored REAL snapshots. Source-level errors include
  WEB_CAPTUREERROR, HTTP_STATUS_403 and WEB_PAGE_LIMIT; no blocked page invented.
- Terminal status **PARTIAL**, stop_reason **WEB_CAPTUREERROR**. This is not a
  successful complete-flow gate. Four public fields were published: volume,
  skin_type,key_ingredients,notification_number. responsible_company was absent.
  Further diagnosis of the missing field was not part of this server probe.
- Buyer evidence endpoints returned6 volume passages and9 skin-type passages.
  Three additional passport reads left jobs1/runs1/live calls13/replayed calls0
  unchanged. No source or gold result was edited to change the outcome.

Raw run/trace saved locally at `.git/hosted-live-run-20261031.json`; no API key was
read or logged. No claim about exact provider billing is made from token counts.

## UI deployment difference

Render frontend asset `/assets/index-DFqCMqrn.js` contains web-audit,receipt-diff
and agent-panel testids. Sites still serves `/assets/index-BviinFXb.js`, which
contains none of those three. The Sites API proxy reaches the new backend, but
its frontend is older. This is source/asset inspection, not a browser interaction
test. Prefer the Render URL for the current UI until Sites is republished.

Render: https://product-truth-passport-demo.onrender.com
Sites: https://product-truth-passport-vn.pointykayak.chatgpt.site

## Outcome

Actual OpenAI calls and Web Search work online; a complete five-field LIVE demo
has not passed this check. Keep PARTIAL and source fetch failures visible. The
measured processing time alone exceeds90 seconds, so a90-second video needs an
explicitly disclosed shortened wait or a separate result-inspection segment.
No deployment, gate, commit or push was performed during this probe.
