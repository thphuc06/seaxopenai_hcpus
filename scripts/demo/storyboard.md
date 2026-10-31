# Product Truth Passport — running-app storyboard

## Current web-enabled cut — requested16:21 ICT

One real Web Search run follows the initial LIVE comparison. P4 keeps the original cut and first-run evidence. The web run found/stored2 new REAL snapshots, adding1 independent source family;2 other fetches returned403. Run PARTIAL is shown, not concealed. All post-search Passport/evidence/Why scenes are freshly recorded from revision2.

| Timeline | Actual scene | Disclosure / evidence |
|---|---|---|
|0:00–0:05|Original REAL product before comparison|Original first-take footage|
|0:05–0:13|Original LIVE bootstrap click/wait|Wait sped up with visible label|
|0:13–0:17|Original stored result|WAITING_REVIEW shown|
|0:17–0:22|Web Search API request and real wait|API trigger explicitly labelled; no fabricated UI button|
|0:22–0:42|Query audit →403 skips →new snapshots →stored source text|4s query,5s blocked-page audit,5s snapshot metadata,6s source reading|
|0:42–0:52|Updated Passport|Skin-type3 independent families; unresolved fields retained|
|0:52–1:10|Evidence including fresh web passage|8s first quote then brand-source comparison; actual text/locator|
|1:10–1:20|Why policy rules|Code counts source families and checks publication|
|1:20–1:30|Web run trace|LIVE/PARTIAL/HTTP_STATUS_403; search/fetch/snapshot steps visible|

Recorder: record_web_demo.py; source take web-first. Finalized16:27 ICT: timeline90.00s, encoded90.03s,H.264/AAC1280x720/30fps, silent. Full decode passes,0 assembly overlaps;45 sampled frames plus12 key frames inspected. File scripts/demo/out/live-p4-20261031/demo.mp4 now points to this web-enabled version; original cut remains under take-b375bf49. Post-web recording creates no extra event/job/run/model call. Human normal-speed playback/team sign-off remains unverified. No new app feature, budget increase, source edits, approval claims, public upload or commit/push. See docs/results/live-demo.md for runtime measurements.

## First P4 LIVE cut — 31 October16:12 ICT (preserved)

The user's current90-second LIVE instruction supersedes the historical160-second replay handoff below. P4 alone records/assembles. No synthetic revoke, public upload, sync-gate or commit/push. Preserve the previous storyboard as planning history.

| Target time | Running-app scene | Callout and reading hold | Proof |
|---|---|---|---|
|0:00–0:10|REAL Foaming product before comparison|Sản phẩm REAL · Đối chiếu từng thông tin|Original captured product and unprocessed Passport|
|0:10–0:26|Operator fires real bootstrap LIVE|Đang xử lý LIVE · Đoạn chờ được tua nhanh|Full wait retained in raw take; provider trace checked before use|
|0:26–0:38|Buyer Passport|Kết quả riêng cho từng trường; missing evidence remains visible|Actual stored field results|
|0:38–1:02|Skin-type evidence drawer|Hold first quote11s, then next passage|Stored quote/locator/source version; no text replacement|
|1:02–1:16|Expert Why dialog|Luật đã áp dụng; hold decision trail7s before scrolling|Code decision trail from API|
|1:16–1:30|Operator trace and model counter|Model trích xuất, code quyết định; stored reads|LIVE marker, token steps and unchanged model count across reads|

As made16:20 ICT: timeline90.00s, encoded duration90.02s (AAC/container rounding),1280x720/H.264/AAC/30fps. The table above is the measured scene schedule; the LIVE section contains10s of original click/wait footage followed by6s of the stored WAITING_REVIEW result. Brand quote is held11s; the listing section then remains visible to1:02. Why focuses actual policy rules and publish gate. Trace shows token-bearing calls, followed by unchanged model-call counters.

Final local file: `scripts/demo/out/live-p4-20261031/demo.mp4`. First cut `take-b375bf49/demo.mp4` and refined cut `take-b375bf49/refined/demo.mp4` remain separate. Original raw and recovered live-click video, first-run JSON and per-field evidence are retained. Decode of the complete final file passes;45 sampled frames across the full duration plus key-hold contact sheets were inspected. Normal-speed human playback review remains outstanding; no claim of team sign-off.

Local isolated database and UUID takes live under `scripts/demo/out/live-p4-20261031`. P4 adapter: `record_live_demo.py`; P3's replay recorder remains intact. Web search is off; optional web/receipt/agent-effect scenes are absent because this take has not established them. OpenAI LIVE extracted from two stored REAL snapshots; code compared the extracted claims. See `docs/results/live-demo.md` for evidence/disclosure. `narration.json` remains `{}`.

## Historical replay storyboard (preserved)

Drafted 31 October 2026, P4 Phase 3. Planned duration **160 seconds**, with **20 seconds reserve** under the team's 3:00 brief. Silent: no voice, TTS or music; `narration.json` stays `{}`. This is a storyboard, not a recorded or team-reviewed video.

Phase4 independent audit, 31 October 15:12 ICT, baseline `e0a8e3b` (includes sync-3): S3 in-process gate and UI source selectors now exist. The published S3 gate is evidence of behavior; this audit is source inspection, not a new browser rehearsal. Web/receipt scenes remain pending S4 integration and replay. Final recording readiness is deliberately not claimed before those checks.

At sync-4, receipt and web-audit routes/UI are integrated and the offline paths pass. P3 supplies buy-button, receipt-diff, web-audit and review-reason selectors plus E2E/recorder scaffolding. The preserved live-agent-probe report demonstrates an actual provider call, code anchor check and field effect; scene6 still needs its corresponding replay take. Scene7 and receipt insertion now await browser/replay rehearsal. R3/R4 source diagnostics pass; original sources and gold remain unchanged. All three marketplace pages conservatively abstain in fallback, so do not present them as a populated consensus scene.

Show the app and system flow. No pitch slides, market statistics, benchmark tables or Codex slides. The live pitch/write-up carries those topics. The title is a short overlay over the running app, not a separate slide.

## Readiness and recording setup

App: `http://localhost:5173`, API `http://localhost:8000/api`. The human starts the Local `backend` and `frontend` Actions. Use the app's demo Buyer, Operator and Reviewer roles; no personal login or production account. S3 in-process validation passed at sync-3; browser choreography and actual scene timing remain to be rehearsed. Agent and Why implementations are integrated, but actual recorded agent effect remains pending. Web and receipt scenes remain conditional on S4 gates and recordings.

Before each independent take, reset through the Operator reset flow/API, then fire that scene's prerequisites. Never assume a reset retains previously fired events. Recording target: `LLM_MODE=replay`, `DEMO_RUN_DELAY_S=3`, frozen matching recordings and API frontend (`VITE_USE_MOCK=0`). P3 records after `rec-freeze`; P4 does not start a server or record now. A replay miss is a failed take, not permission to substitute a model answer. A separately approved FALLBACK scene must display that provenance explicitly.

Keep the applicable REAL/SYNTHETIC and REPLAY badges visible. Registry scenes carry MOCK. Use `data-testid` from README §7.4; missing controls go to P3 as CCR, not fragile text selectors. Never expose keys, headers, internal account identifiers or raw JSON in the buyer view. Source words appear only in their cited source panel.

## Scene plan

| Scene / time | Action and prerequisites | Short callouts | Evidence and hold | Readiness |
|---|---|---|---|---|
| 1 · 0:00–0:05 | Open Buyer passport shell with title overlay. | Product Truth Passport · Đối chiếu từng trường | App remains visible; provenance badge. 2s hold. | S2 UI; browser rehearsal pending |
| 2 · 0:05–0:25 | Fresh reset. Operator `event-btn-01-bootstrap-demo`; follow control room/trace to stored result. | Sự kiện → trích xuất → luật → bằng chứng | `run-status`, `model-calls-counter`, model/code steps. Hold published state 3s. | Core and S3 waterfall integrated; replay take pending |
| 3 · 0:25–0:47 | Independent reset + `event-btn-15-bootstrap-real-foaming`. Buyer `evidence-open-skin_type`; show quote/locator/capture date, then reload passport three times. | Mỗi trường có nguồn trích dẫn · Mở lại không gọi model | REAL + REPLAY. Use Operator counter before/after without technical detail in Buyer. Hold quote 4s. Deep Domain AI corner chip. | REAL capture and S2 tests exist; record/browser pending |
| 4 · 0:47–1:07 | Reset + `event-btn-14-bootstrap-real-hydrating`. Open `why-open-skin_type`, then ingredient evidence. If REAL scene cannot be replayed, use event11 synthetic twin and label SYNTHETIC. | Mâu thuẫn trong nguồn · Không quy cho người bán | Two stored passages disagree within one source. Hold each 3s. Deep Domain AI. | S2 verdicts pass; S3 Why integrated; replay take pending |
| 5 · 1:07–1:27 | Reset + event01, then `event-btn-05-revoke-notification`. Keep 3s delay; watch exactly two dependent fields go stale, then the new conclusion/request. | Nguồn đổi → trường phụ thuộc cũ đi · Cần tài liệu mới | Notification/company ripple; volume remains current. Show request after run. MOCK registry as applicable. Autonomous & Adaptive AI. | S2 lifecycle passes; timed take pending |
| 6 · 1:27–1:49 | Reset + event01, then `event-btn-09-catalogue-published`. `agent-panel`: sized lines, size-less line, proposed anchor, code check, skin-type before/after, `budget-meter-*`. | Agent đề xuất vị trí · Code kiểm tra đoạn neo | Actual recorded `agent:effect` must change the field. Hold anchor and changed result 4s each. Autonomous & Adaptive AI. | S3 scope/code/anchor path integrated; provider recording pending; do not label a code-only effect as model adaptation |
| 7 · 1:49–2:07 | Reset + real Hydrating event14 only after Web Scout gate; open `web-audit`, inspect captured domain/time or explicit blocked-page reason. | Tìm nguồn → kiểm tra phạm vi → lưu dẫn chứng | REAL + REPLAY; use actual audit outcome. A blocked fetch is shown as blocked. Autonomous & Adaptive AI. | S4 conditional; fallback scene below if not retained |
| 8 · 2:07–2:22 | Reset + `event-btn-13-bootstrap-clear-serum`. Reviewer claim findings and cited INCI; Buyer shows only neutral count if wired. | Tuyên bố được đối chiếu với INCI · Người duyệt xử lý phần chưa rõ | Use a demonstrated free-from discrepancy. Concentration stays unresolved while regulatory data remains provisional; do not claim a numeric limit was validated. Deep Domain AI. | S2 audit exists; count/recording pending |
| 9 · 2:22–2:40 | Fresh review scenario: event01 → event04; open `review-task-volume`, approve one current revision; event07 changes that evidence. Receipt diff only after S4 order/receipt gate, with purchase before the change. | Duyệt gắn với một phiên bản · Bằng chứng mới, kết quả mới | Reviewer approval and later revision. Hold 4s. Receipt, if available, uses `receipt-diff`; no checkout/payment fiction. | Review S2; receipt S4 conditional |

## Selector and prerequisite handoff (audited before contract-4)

Every event selector uses the fixture stem without `.json`; the API catalog returns the stem and Operator renders `event-btn-${event.name}`. Use independent takes, with the human-approved reset/prerequisites outside the recorded scene as described above. Do not infer a working recording selector from a text label.

| Scene | Exact retained fixture order | Source-backed selector(s) | Outstanding proof |
|---|---|---|---|
| 1 | none | `badge-origin`, `badge-mode` | Show provenance supplied by stored data; do not invent REPLAY on an empty shell |
| 2 | `01-bootstrap-demo` | `event-btn-01-bootstrap-demo`, `run-status`, `model-calls-counter` | S3 waterfall exists; actual replay and browser timing pending |
| 3 | `15-bootstrap-real-foaming` | `event-btn-15-bootstrap-real-foaming`, `evidence-open-skin_type`, `field-label-skin_type` | REAL capture available; provider recording and three-reload browser take pending |
| 4 | `14-bootstrap-real-hydrating` (alternate independent take: `11-bootstrap-hydra`) | `event-btn-14-bootstrap-real-hydrating`, `event-btn-11-bootstrap-hydra`, `why-open-skin_type`, `evidence-open-key_ingredients` | Why is delivered in S3; replay/rehearsal pending |
| 5 | `01-bootstrap-demo` → `05-revoke-notification` | `event-btn-05-revoke-notification`, `field-label-notification_number`, `field-label-responsible_company`, `field-label-volume` | Revoke is SYNTHETIC; record transient stale state with configured delay |
| 6 | `01-bootstrap-demo` → `09-catalogue-published` | `event-btn-09-catalogue-published`, `agent-panel`, `budget-meter-model_calls`, `budget-meter-tool_calls`, `budget-meter-seconds` | S3 code/anchor tests pass; paid whole-story agent effect still requires a recording. Code-only prepass must not be described as a model effect |
| 7 | conditional `14-bootstrap-real-hydrating` plus owner's S4 trigger | `web-audit` is absent at this baseline | Wait for actual S4 contract, UI and audit; fallback remains the documented Why take |
| 8 | `13-bootstrap-clear-serum` | `event-btn-13-bootstrap-clear-serum`; Reviewer uses dynamic `review-task-<field_key>` | Select the actual persisted claim key; no hardcoded invented claim id. Buyer claim count remains optional/unverified |
| 9 | `01-bootstrap-demo` → `04-volume-change` → revision-bound approval → `07-injection-listing` | `event-btn-04-volume-change`, `review-task-volume`, `review-approve`, `event-btn-07-injection-listing` | Reason field needs stable selector; receipt `buy-button`/`receipt-diff` remain absent. Receipt choreography must purchase before the change and use the final owner contract |

Source audit: `frontend/src/components/PassportCard.tsx` (field/evidence/Why/provenance), `StatusBadge.tsx` (labels), `RunGlassbox.tsx` (agent and three root-budget meters), `frontend/src/pages/Operator.tsx` (event/run/counter), `Reviewer.tsx` (task/approve) and `backend/app/api/events.py` (fixture stem). The meters currently describe the recorded root Budget; child-agent values are not assumed.

CCR P4→P3: `frontend/src/pages/Reviewer.tsx` · need: `data-testid="review-reason"` on the required reason textarea and `data-testid="review-decision"` on the decision select · why: scene9 cannot complete approval using stable testids alone · snippet: add those attributes without changing behavior. Until delivered, scene9 is pending/cut-first; do not select by visible text. P3's `scripts/e2e.py` and `scripts/demo/record_demo.py` are absent in this baseline and remain owner deliverables.

## Cuts and alternate take (retained)

Preserve scenes 3–6. If above 160s, cut scene9 first, shorten scene2, then cut scene8. Do not speed through quotes or the anchor check. Scene7 can use an 18s evidence/Why inspection from a passed S3 route if Web Scout is cut at Sync; update this storyboard and recording list to the actual retained scope. Scene9 can end after revision-bound review if receipts are cut. Pending scenes are not claims of implementation.

Keep 1.5–2.5s pauses around clicks, 3–4s on important evidence, camera focus readable at 720p. Record waits in full; only shorten them with an explicit fast-forward mark and disclose it. Final durations are measured from actual captures, not assumed from this draft.

## Handoff and disclosure

P3 owns `record_demo.py`, selectors and segments; P4 owns this timing/callout plan and final assembly. Handoff needs a two-minute team review, real-browser rehearsal, checked replay scenes and an actual before/after anchor effect. No video or audio generated in this phase.

Prepared tooling: `_outside-repo/skills/mvp-demo` was present before the event and is declared separately from contest application code. This storyboard and future `scripts/demo` application recordings are contest work. Final description discloses synthetic cases, the mock registry, replay mode, shortened waits and any cut scenes. No synthetic voice is used.
