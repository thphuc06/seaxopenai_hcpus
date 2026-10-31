# P4 LIVE demo — 31 October 2026

## Source handoff review16:35 ICT
Existing final MP4 is unchanged. Recorder source now rejects drift between archived and current run/revision/Passport/audit, rejects unfinished web receipts and derives optional factual captions from receipt data. Recorder tests22+9 pass. Full backend review1624 pass/2 fail/+2 subtests found an eval timestamp collision (writer repaired with unique exclusive archives) and a disabled-web test inheriting the local on flag (offline commands now specify WEB_SEARCH=off). User explicitly stopped further tests and requested branch publication; the focused post-repair run was interrupted, so a fresh all-green backend suite is NOT claimed. This does not alter the earlier actual video/runtime evidence below.

## Web-enabled follow-up requested16:21 ICT

Only runtime flag WEB_SEARCH changed off→on; app code, budgets and model IDs remain unchanged. Initial combined restart command was auto-review rejected; after the user's renewed explicit restart request, verified listener30464 was the uvicorn child of the owned launcher39776, no run was active, and the targeted stop/restart succeeded. New launcher35408. Earlier video, DB before discovery, first-run JSON and all source/gold inputs remain preserved.

Existing POST /api/cases/REAL-CASE-R2/web-search initiated a real revision2 run. The frontend has an audit viewer but no search button, so the recorder called the authorized operator API and labels that trigger on screen. No invented UI or query result.

Run run_fae8702567c04ebaa13bd3e4b34719e3:16:22:53–16:23:56 ICT,63.09s, **LIVE / PARTIAL / HTTP_STATUS_403**. It made9 token-bearing LIVE calls: query planning1, hosted web_search2, candidate selection2, extraction2 and coverage retries2. Every provider step is replayed=false; no FALLBACK/REPLAY mode in the trace. Usage35,539 input/5,431 output tokens. Estimate$0.125388 token cost+$0.02 for2 hosted searches = **$0.145388 additional**, **$0.216138 total** including the initial run. Official rates checked31Oct: [OpenAI pricing](https://developers.openai.com/api/docs/pricing). These are uncached standard-rate estimates, not invoices.

Two new REAL snapshots passed identity checks and were fetched/stored with hashes and capture times:
- cerave.com.vn product page:19 passages, captured during this run.
- pharmacity.vn product page:25 passages, captured during this run.

Long Chau and Guardian fetches returned403 and remain visible as SKIP/HTTP_STATUS_403 in the audit. No retries or edits to make these pages appear fetched. Two new snapshots are not two additional independent source families: the refreshed brand page repeats the existing brand family; Pharmacity adds one. Code-published skin_type now states3 independent families, versus2 before web discovery. Ingredient conflict and missing notification/company evidence remain. Volume stays SINGLE_SOURCE. PARTIAL is retained rather than presented as a completed clean run.

Evidence folder: scripts/demo/out/live-p4-20261031/web-first, including before.db (SQLite backup), passport-before/after.json, audit-before/after.json, first-web-run.json, original web-discovery footage and final recut. The first90-second version remains in take-b375bf49. Web-enabled final delivered16:27 ICT at [demo.mp4](../../scripts/demo/out/live-p4-20261031/demo.mp4), also retained at web-first/final/demo.mp4. Timeline90.00s/container90.03s,H.264 High/yuv420p1280x720/30fps,AAC LC mono48kHz,max volume−91dB. Full decode passed;0 timeline overlap problems. Inspected45 frames at2s intervals and12 key frames. Normal-speed human playback/team sign-off remains unverified.

Post-web recut only reads stored state: live model calls13→13, replay0→0, runs/jobs2→2, admitted events2→2. Five field evidence exports pass excerpt-in-passage checks. Original first run, REAL fixture files, gold DRAFT, blind first results, Sites and prepared kit remain unchanged. WEB_SEARCH stays on for the local backend; no further discovery requested after this one run.

Offline `python scripts/demo/test_web_recorder.py`:7 passed,0 failed/skipped, including partial-but-real discovery, unrelated source identity, replay/fallback rejection and preventing a mere search/no snapshot from being described as extra sources. Fresh `pytest -q tests/test_guards.py --tb=short` with LLM_MODE=fallback:4 passed,0 failed/skipped/deselected. Prior13 recorder tests and61 acceptance/guards remain applicable to unchanged application code; no redundant full-suite/gate. git diff --check passes. Only ignored backend/.env flag and P4 scripts/docs changed; no application or frontend edit/build.

## Initial video evidence (preserved)

Started16:09 ICT (T+6:09) on Local p4, already containing sync-4. P4 is the sole video owner by current user instruction. No sync-gate, commit/push or public upload is authorized.

Runtime preflight16:12: health live, gpt-6.1-sol extract/agent, policy-v2.1, PHASE4, delay0. Frontend uses real API. Isolated SQLite path: scripts/demo/out/live-p4-20261031/passport.db. User explicitly authorized hidden server startup after the initial Actions request. Existing shared DB and Sites are retained.

Selected REAL source case: CeraVe Foaming Facial Cleanser236ml, captured31Oct under fixtures/real/r2-foaming-cleanser. No invented source event/revoke. Gold remains DRAFT and neither source snapshots nor first-run blind files are changed.

Cost authorization: user explicitly said credits are plentiful and authorized LIVE spending. Estimate $0.20–$2 per run, up to three paid attempts; actual measured usage pending. Official standard rates checked31Oct: [gpt-6.1-sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), $2/M input and $10/M output. This is an estimate, not provider billing.

Offline kickoff collection: CONTEST_PHASE=5 `pytest -q -m phase --co` selected272/1626, deselected1354. No phase(5) markers found; collection does not prove execution. Focused `pytest -q tests/test_guards.py tests/test_acceptance.py -k 'foaming or buyer_read_only or citations_valid or buyer_explain or guards'`:8 passed,0 failed/skipped,53 deselected; existing Windows temporary-directory cleanup warnings retained.

First watchable cut exported16:17 ICT:90.0s,1280x720, silent,1.9MB, at scripts/demo/out/live-p4-20261031/take-b375bf49/demo.mp4. Original segments and cut remain intact. Read-only refinement finished16:19; final stable copy at16:20 is [demo.mp4](../../scripts/demo/out/live-p4-20261031/demo.mp4),2,037,868 bytes. Refined take: scripts/demo/out/live-p4-20261031/take-b375bf49/refined/demo.mp4.

Actual LIVE run: run_92bb74ce2d0e4be08095b52c741a5498,16:13:14–16:13:48 ICT (34.30s), WAITING_REVIEW, no stop reason. Four provider calls (two extract, two coverage retry),16,280 input tokens and3,819 output tokens, all token-bearing trace steps modeLIVE/replayed=false. Standard uncached estimate **$0.07075**; not provider billing. One paid attempt only. No web or scope-agent model call was needed. The gap controller attempted the existing MOCK registry; it supplied no notification evidence. Do not describe that as a live regulatory lookup.

Actual fields: volume SINGLE_SOURCE; skin_type CONSISTENT; key_ingredients CONFLICTING/NEEDS_REVIEW; notification_number and responsible_company INSUFFICIENT. These are the original code-published outputs and remain unchanged. The video shows the unresolved fields; it does not claim that every field passed or that a reviewer approved them.

The original live-click capture had a recorder wait bug: admission returns external event_id while run.trigger_event_id is a storage id. Backend completed normally; P4 stopped the recorder and remuxed its truncated WebM into a separate recovered.mkv without changing frames. Original raw file remains. The first40s are used; raw seconds5–39 are played in4s with the visible fast-forward chip. The tail after completion/recorder wait is cut. Subsequent stored-result scenes were recorded after this repair, with no new model call. Recorder now resolves event_id through events/log and accepts legitimate WAITING_REVIEW/WAITING_EVIDENCE terminal results rather than demanding COMPLETED.

CCR P4→P3: scripts/e2e.py Journey.fire uses the same external event_id versus stored trigger_event_id comparison and requires COMPLETED; use events/log.run_id and assess published terminal states for the intended scene. Legacy P3 replay helper is unchanged and not used by this video.

Read-only scene receipt: before/after model_calls live4/replayed0, runs1/jobs1/events ADMITTED1; Passport reads4→11. All returned public evidence excerpts were checked as substrings of their stored passages. Raw first-run.json, passport.json, per-field evidence JSON and read-check.json are preserved in the take folder.

Refinement receipt: reads12→16, model calls4→4, runs/jobs1→1 and admission counts unchanged. It scrolls to the listing quote, the policy-rule section and the trace token table; no source/result text changes. WEB_SEARCH remains off. The footage does not demonstrate finding/fetching fresh sources or a scope-agent effect.

Media QA16:19–16:20: full video/audio decode passed; H.264 High/yuv420p,1280x720,30fps; AAC LC mono48kHz; duration90.02s; max audio volume−91dB (silent track). Assembly overlap check:0 problems/0 voice clips. Inspected45 sampled frames at2s intervals across all90s, plus9 key-hold frames; quotes and LIVE/WAITING_REVIEW evidence remain visible. Full normal-speed human playback/team review remains NOT VERIFIED. Media log/contact sheets are in the refined folder. No public upload.

Final offline scope at16:18 ICT: CONTEST_PHASE=5, LLM_MODE=fallback, WORKER_INLINE=1 `pytest -q tests/test_acceptance.py tests/test_guards.py --tb=short`: **61 passed,0 failed/skipped/deselected**,38 existing dependency/temp cleanup warnings; log under scripts/demo/out/live-p4-20261031/acceptance.log. `test_live_recorder.py`:13 passed,0 failed/skipped. No frontend source change/build required. No full-suite/freeze claim.

Disclosure: local running app, isolated seeded demo dataset with REAL captured source text, no source edits or altered results. Recording-only CSS hides empty shopping metadata/image placeholders and adjusts typography/spacing; it does not change findings, quotes, provenance or trace. Navigation loads are trimmed and model wait is visibly labelled as fast-forwarded. Silent AAC track; no voice/TTS/music/pitch slides. Prepared demo kit predates the event.
