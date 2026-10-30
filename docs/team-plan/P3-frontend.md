# P3 — Frontend: Buyer · Operator · Reviewer · Observe · Receipt

> P3 làm cho giám khảo không chuyên **hiểu được trong 3 phút**. Ba ý cần truyền tải:
> - mỗi thông tin có căn cứ;
> - nguồn tự mâu thuẫn thì không đổ lỗi cho seller;
> - revoke chỉ làm STALE đúng field phụ thuộc, và agent đã đổi được gì.
>
> Buyer thấy ngôn ngữ đời thường. Operator và reviewer thấy toàn bộ glass box. UI phải đọc được ở 720p, vì video demo quay ở độ phân giải này.

## 0. Bạn sở hữu gì, phụ thuộc ai

- **Sở hữu:** `frontend/**`.
- **Cung cấp:** UI và các `data-testid` ổn định (README §7.4) cho E2E và video của P4.
- **Phụ thuộc:**
  - P1: REST (README §7.2) và `/openapi.json` để sinh type.
  - P1/P2: trace step names và `detail` keys (README §7.3).
  - Trước S1 làm hoàn toàn trên **mock**.
- **Stack:** Vite + React + TypeScript + react-router, viết **CSS thuần với design tokens** (CSS variables). Không thêm UI framework trừ khi cả đội đồng ý ở S0. Version ứng viên: react 19.3.1, react-router-dom 7.18.4, vite 8.3.5, typescript **5.9.3**; kiểm lại trên npm ngày thi.

## 1. Nhịp mỗi phase

1. Đầu phase: `git fetch --tags; git merge sync-<N-1>` trên branch `p3` (mỗi người một branch cho cả ngày).
2. `$phase-kickoff P3 <N>`. Phase 0 thì dán thẳng Prompt chính cho nhanh.
3. **T+20, sau mini-sync:** `git fetch --tags; git merge contract-<N>`, bấm Action `backend` để chạy backend của `contract-<N>` rồi sinh lại type từ `/openapi.json`. Route mới đã có shape thật (trả 501 hoặc dữ liệu ví dụ). Cập nhật mock theo đúng shape đó.
4. **Trước Sync, "xong" nghĩa là** build pass trên mock và type khớp OpenAPI của `contract-<N>`. Click path trên backend thật được kiểm ở Sync (P4 chạy), không chờ trong phase.
5. Thread 2 chạy Prompt phụ (E2E, quay video) trên file khác thread 1.
6. Luôn chạy `npm run build` trước khi push. T−20: `$self-review`.
7. **Ngay sau S2 và S3 (10 phút, trong lúc Codex của bạn chạy kickoff):** soát chéo expected answers P4 vừa viết (`fixtures/gold/dev/real.json`, `fixtures/gold/blind/expected-set1.json`). Bạn là "người thứ hai" theo AGENTS rule 11.
8. **Lần đầu sau S0:** chạy `powershell -ExecutionPolicy Bypass -File scripts\dev\setup_worktree.ps1` ở checkout Local để có backend venv (Action `backend` cần nó).

**Skill Codex dùng trong lane này** (cài ở `~/.agents/skills`, gõ trong ô chat của Codex):

| Khi nào | Gõ | Kết quả |
|---|---|---|
| Đầu mỗi phase | `$phase-kickoff P3 <N>` | Codex đọc section phase, cập nhật ExecPlan, hỏi nếu dính trigger, rồi chạy Prompt chính |
| Test đỏ hoặc verdict sai | `$trace-debug <tên test hoặc field>` | Tìm bước đầu tiên đi sai trong trace, viết test tái hiện, sửa đúng gốc lỗi (file của lane khác thì gửi CCR), ghi "Notable loop" vào CODEX_LOG |
| Xong sớm, bị kẹt, phải chọn cắt gì | `$brainstorm <options / cut / qa> <bối cảnh>` | Phương án xếp hạng kèm prompt dán được ngay, không viết code |
| T−20 mỗi phase | `$self-review` | Chạy test và build, quét hardcode, từ cấm, gold, secret, kiểm lane, contract, ExecPlan → `READY TO PUSH` hoặc `BLOCKED` |
| Phase 5 (P3-5b) và Phase 6 | `$mvp-demo` | Phase 5: P3 quay từng segment bằng kit theo storyboard của P4. Phase 6: P4 ghép; P3 sửa chỗ phụ đề che nội dung, panel bị cuộn ẩn, chữ nhỏ ở 720p rồi quay lại segment đó |

**Effort:** `medium`.

**Hướng thiết kế cố định từ Phase 0** để không phải làm lại:
- Buyer page theo kiểu trang sản phẩm của một marketplace: ảnh, tên, giá, shop, rồi thẻ "Product Truth Passport".
- Màu verdict: Consistent xanh lá · Single source xanh dương nhạt · Conflict in source tím, **không dùng đỏ**, vì không phải lỗi của seller · Conflicting cam · Not verified xám · Stale vàng, có ripple.
- Font hệ thống rõ ràng, cỡ chữ cơ bản 16px. Mọi panel đều readable ở 1280×720.

---

## Phase 0 — Khung app trên mock (T+0:00–0:30 · 10:00–10:30)

### Mục tiêu
App boot với 5 route và có role switcher. Buyer page render được từ `mock/passport.json` đúng shape `PassportResponse`. API client gửi `X-Demo-Role`.

### Must / Should / Could
- **Must:** scaffold, router, `types.ts`, `mock/passport.json`, `api/client.ts`, `usePoll`, layout + tokens, Buyer page đọc từ mock.
- **Should:** Operator shell (danh sách nút event lấy từ mock catalog).
- **Could:** script `npm run types` sinh type từ `http://localhost:8000/openapi.json` (`openapi-typescript`).

### Prompt chính P3-0 (effort: medium) — làm được ngay từ 10:05, không phụ thuộc skeleton backend
```text
You are the P3 (Frontend) Codex agent for Product Truth Passport, Phase 0 (T+0:05–0:30). AGENTS.md is loaded. Create
.agent/plans/P3.md from .agent/PLANS.md (Phase 0 milestone). You own frontend/** only.

GOAL
A Vite + React + TypeScript app with five routes, a role switcher and a buyer Passport rendered from a mock that has
exactly the backend's response shape, so the UI can be built in parallel and switched to the real API at Sync 1.

CONTEXT (batch-read)
- docs/05-contracts.md §2 (routes, passport response example), docs/04-data-model.md "Buyer label mapping" (evaluate
  top to bottom, first match wins) and enums, docs/06 "Public text templates" and forbidden words
- docs/team-plan/README.md §7.2 (routes by Sync), §7.3 (trace steps), §7.4 (data-testids you must provide),
  known UI risks (estimates): buyer UI ≠ operator UI; show what the agent changed; avoid jargon on buyer screens
- docs/DATASET-SPEC.md §3–§4 (the demo products and events; write your own realistic mock text from it — the mock
  lives in frontend/src/mock; app code may not contain product texts)

BUILD
1. Scaffold in frontend/: package.json with pinned versions (check them on npm today; TypeScript 5.9.x, not 7),
   vite.config.ts proxying /api → http://localhost:8000, strict tsconfig, index.html, src/main.tsx with react-router:
   "/" Operator control room, "/buyer/:productId" Buyer Passport, "/reviewer" Reviewer console, "/observe"
   Observability, "/orders/:orderId" Receipt. A top bar with role switcher (BUYER/SELLER/REVIEWER/OPERATOR stored in
   localStorage) and product switcher.
2. src/types.ts mirroring the backend models (PassportResponse, PassportField, Citation, ClaimFinding, AdmitResult,
   EventEnvelope, run + trace step, enums as string unions). src/mock/passport.json: a realistic passport for the DEMO
   product (5 fields covering CONSISTENT, SINGLE_SOURCE, CONFLICTING/WITHIN_SOURCE, INSUFFICIENT, STALE; citations with
   excerpts, one PRIVATE hidden count).
3. src/api/client.ts: fetch wrapper with base "/api", X-Demo-Role/X-Demo-Actor headers from the role switcher, typed
   functions per route (README §7.2 S1 row first), errors surfaced to the UI (no silent catch); VITE_USE_MOCK=1 serves
   the mock. src/usePoll.ts (interval polling with pause on hidden tab).
4. Design system in src/styles.css: CSS variables for colours (one per buyer label, never red for "Conflict in source"),
   spacing, radius, typography; light theme; readable at 1280×720; mobile layout works (single column).
5. BuyerPassport page from the mock: product header (image, name, brand, price, shop; "Official store" only when the
   data says so), the Passport card with one row per field: label chip, plain-language sentence, checked time, "View
   evidence" and "Why?" buttons (wired in Phase 1/3), origin badges (SYNTHETIC/REAL) and mode badge
   (REPLAY/FALLBACK/LIVE), disclaimer. data-testids from README §7.4.

CONSTRAINTS
- Intentional visual direction (marketplace product page + evidence card), not a generic admin template; no aggregate
  score/badge such as "Consistent ×5"; no forbidden words (rule 1) in any string.
- Labels are computed from verdict/locus/freshness/run status per docs/04 mapping in ONE function (labels.ts) used
  everywhere.

DONE WHEN
`npm run build` passes; I check in the browser (app Action `frontend`) that the buyer page renders from the mock at
/buyer/DEMO-PROD-01 and the other routes as shells — do not start the dev server yourself; report per AGENTS.md §6 (include a screenshot path if you took one).
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Bàn giao ở Sync 0
App boot · `types.ts` đã đối chiếu với `models.py` của P4. Nếu khác nhau thì ghi lại để xử lý ở S1.

---

## Phase 1 — Buyer + Evidence + Operator v1 trên API thật (T+0:30–1:45 · 10:30–11:45)

### Mục tiêu
Click path M1 chạy trên API thật:
- Operator bấm event, thấy outcome (ADMITTED/NOOP/DUPLICATE/REJECTED) và bộ đếm.
- Buyer xem 5 field, mở evidence thấy đoạn trích được highlight trong passage.
- Refresh buyer thì bộ đếm model call không đổi.

### Must / Should / Could
- **Must:** Buyer với API thật + evidence drawer · Operator v1 (catalog event, fire, toast outcome + stale_fields, counters, run list + bảng trace step) · `data-testid` đầy đủ cho S1.
- **Should:** sinh type từ OpenAPI · nhãn tạm thời (Not checked yet / Updating / Could not update).
- **Could:** ripple khi label đổi.

### Prompt chính P3-1 (effort: medium)
```text
You are P3, Phase 1 (T+0:30–1:45). Update .agent/plans/P3.md first. P1's S1 routes land during this phase: build against
the mock first, switch to the real API as soon as GET /api/products/{id}/passport answers, keep VITE_USE_MOCK as a flag.

GOAL
A buyer can read each field's status in plain language and open the exact evidence; an operator can fire fixture events
and watch outcomes, counters and runs — the Milestone 1 click path, on the real backend.

CONTEXT
- README §7.2 S1 routes, §7.3 trace step lanes, §7.4 testids; docs/05 passport response; docs/04 buyer label mapping;
  the backend's /openapi.json once available (generate src/api/schema.d.ts with openapi-typescript and adapt types.ts)

BUILD
1. Buyer: fetch passport (poll 2 s while any field is STALE/Updating, else 10 s); FieldRow (testids field-row-<field_key>,
   field-label-<field_key>, evidence-open-<field_key>; badges badge-origin, badge-mode) shows label chip, the
   public_text, checked time and badges; evidence drawer (GET …/fields/{f}/evidence): one card per citation with source
   kind/label, version, captured time, locator, the passage text with the excerpt highlighted (exact substring match,
   whitespace-tolerant), "+N private documents (reviewers only)" when hidden_citations > 0. For WITHIN_SOURCE conflicts
   show the two passages side by side with the same snapshot named once ("both from the brand page captured …").
2. Operator control room v1: event catalog (GET /internal/events/catalog) as buttons (testid event-btn-<name>), fire →
   toast with outcome, reason and stale_fields; counters panel (events by outcome, runs, model calls live/replayed/
   avoided, passport reads) from /internal/metrics with testid model-calls-counter; run list (GET /internal/runs) and a
   run detail table of trace steps (seq, step, actor, latency, tokens, error) colour-coded by lane prefix (README §7.3);
   reset button (POST /internal/demo/reset) with confirm.
3. Transient states: "Not checked yet" (no result), "Updating" (run RUNNING for the case), "Could not update" (run
   FAILED: subtext "This says nothing about the product."), "Stale" first (docs/04 order).
4. Errors visible (banner with route + status), never swallowed.

CONSTRAINTS
- Buyer view never shows model ids, JSON values, rule codes or hashes. Operator view may.
- Keep testids stable from now on (P4's E2E and video depend on them).

DONE WHEN
In phase: npm run build passes against the mock and the types generated from contract-<N>'s /openapi.json — do not
block on routes that still return 501.
At the Sync (P4 checks it on the merged code): `npm run build` passes; with backend running in fallback: fire 01-bootstrap-demo → buyer shows five fields with
evidence; fire 02 → NOOP toast; 03 → DUPLICATE; refresh buyer 3× → model-calls counter unchanged. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 2 — Reviewer + vòng đời + control room (T+1:45–3:00 · 11:45–13:00)

### Mục tiêu
- Reviewer xử lý queue: xem bằng chứng hai bên, lịch sử, approve/override/reject gắn với đúng một revision, xử lý được lỗi 409.
- Buyer thấy STALE có ripple khi revoke, và thấy số claim đang chờ duyệt trên đúng row.
- Operator có scenario stepper kèm caption để chạy demo.

### Must / Should / Could
- **Must:** Reviewer console · stale ripple · scenario stepper (Next) với caption · run status chip có PARTIAL + stop_reason.
- **Should:** mục claims: buyer thấy "N claims under review" trên row key_ingredients, reviewer thấy finding và form duyệt.
- **Could:** time-travel slider (`?as_of=`).

### Prompt chính P3-2 (effort: medium)
```text
You are P3, Phase 2 (T+1:45–3:00). Update .agent/plans/P3.md first.

GOAL
Make the lifecycle visible and the human decision real: stale ripple on revoke, a reviewer console bound to revisions,
and a scenario stepper the driver can click through on stage.

CONTEXT
- README §7.2 S2 routes (review queue, reviews 409/422, history, evidence upload, passport as_of), docs/06 review
  triggers, README §3 Sync click paths, the fixture events ("expect" notes
  are good caption sources — read them through the catalog API, do not import fixture files)

BUILD
1. Reviewer console (/reviewer): queue list (testid review-task-<field_key>) → case view: current result (verdict, locus,
   seller_attributable, review_state, case revision), evidence side by side, result history (versions with times and
   reasons), decisions list; form approve/override/reject (testids review-approve, review-override) with mandatory reason, the case revision sent with it; 409 →
   "The case changed since you opened it (revision N → M). Reload." and reload button; 422 → show the server's reason
   (NO_CITATION / FORBIDDEN_WORDING). After a decision assert on the decisions list (durable state), not the form.
2. Stale ripple: when a field's label changes, animate the row (yellow ripple for Stale, soft pulse otherwise); show
   "marked stale — no model call" chip when the run detail has stale:mark with 0 model calls.
3. Claims: buyer row key_ingredients shows a neutral "N claims under review" line when claims_under_review > 0 (no
   accusation); reviewer sees claim findings with citations (listing quote vs INCI passage) and can review them like
   fields.
4. Control room: scenario stepper (testid scenario-next) over an ordered list of fixture events (order from a small
   config in the frontend, captions from the catalog's expect text; keep the list editable for P4's storyboard); the
   live buyer passport beside it; run status chip (testid run-status) incl. PARTIAL with stop_reason and FAILED.
5. Upload evidence (SELLER role): small form to POST /cases/{id}/evidence with a fixture-like JSON or an image.

CONSTRAINTS
- Seller text quoted in reviewer views is marked as seller text (it may contain wording rule 1 forbids us to use).
- No business logic in the UI: labels from labels.ts, decisions validated by the backend.

DONE WHEN
In phase: npm run build passes against the mock and the types generated from contract-<N>'s /openapi.json — do not
block on routes that still return 501.
At the Sync (P4 checks it on the merged code): Build passes; with backend fallback: Next through 01 → 05 shows two fields Stale then Not verified with requests; 04 →
volume Conflicting → reviewer approves → decision listed; a stale revision gets the 409 message. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 3 — Glass box: Why?, waterfall, agent panel (T+3:00–4:15 · 13:00–14:15)

### Mục tiêu
- Mọi verdict có nút "Why?". Buyer xem 2–3 dòng dễ hiểu. Expert xem đủ trail: trigger → nguồn (sha) → claim → rule → publish gate → chain head → review.
- Waterfall của run tô màu theo lane.
- **Agent panel cho thấy agent đã đổi gì:** verdict trước/sau, passage được đặt kèm anchor, các budget meter.
- Có ô "Ask the evidence" cho reviewer.

### Must / Should / Could
- **Must:** Why? panel (buyer / expert) · agent panel trước/sau + budget meter · waterfall.
- **Should:** Ask the evidence (hiện các stage bm25/dense/fused) · dependency graph · chain badge.
- **Could:** link xuất OTel.

### Prompt chính P3-3 (effort: medium)
```text
You are P3, Phase 3 (T+3:00–4:15). Update .agent/plans/P3.md first.

GOAL
A glass box a judge can follow: why each verdict is what it is, what ran in which order, and — most important — what the
bounded agent changed and how code verified it.

CONTEXT
- README §7.2 S3 routes (explain, otel, observability, graph, chain, search), §7.3 (steps + detail keys:
  replayed, model, prompt_version, stop_reason, budget {used, cap}, before/after for agent:effect)
- Known UI risks (estimates): a long progress bar with no visible effect makes the agent look idle; wording that
  suggests code accepts nothing is misleading; show the before/after

BUILD
1. Why? panel (testid why-open-<field>): BUYER → 2–3 plain sentences built from the explain response (what was compared,
   which sources agreed/disagreed, why it is or isn't attributed to the seller); REVIEWER/OPERATOR → full trail timeline
   (trigger event → source snapshots with sha256 short + captured time + origin → claims with extractor, prompt version,
   mapped_by, quote → rules fired with outcome → publish gate checks → chain head → reviews).
2. Run waterfall: bars on t_ms offsets, lanes code/model/agent/gap/web by step prefix, nested agent tool spans,
   replayed calls marked, errors red, PARTIAL stop_reason shown at the end.
3. Agent panel (testid agent-panel): question/fields, budget meters (testid budget-meter-<kind>: model calls, tool calls,
   seconds vs caps), proposals list with per-passage outcome: "verified by code (anchor: <passage>)" / "needs reviewer" /
   "not accepted (reason)", and an EFFECT box from agent:effect: field, verdict before → after, passages added. If the
   agent changed nothing, say so plainly.
4. Ask the evidence (reviewer): query box → hits with highlighted text, source chips, and the stage ranks (bm25, dense,
   fused); a line saying "ranking only — no answer generated".
5. Dependency graph (reviewer): sources → fields (simple SVG/CSS layout, no heavy library), revoked/stale edges red
   dashed; chain badge (valid/broken + head short hash).

CONSTRAINTS
- Buyer never sees hashes, model ids, rule codes. Keep panels readable at 1280×720 (video).

DONE WHEN
In phase: npm run build passes against the mock and the types generated from contract-<N>'s /openapi.json — do not
block on routes that still return 501.
At the Sync (P4 checks it on the merged code): Build passes; after 09-catalogue-published the agent panel shows a verified placement and the skin_type before → after
(or an honest "no change"); Why? works for buyer and reviewer. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 4 — Receipt, marketplace, web audit, OCR, Observe (T+4:15–5:15 · 14:15–15:15)

### Mục tiêu
Cho thấy rõ các điểm khác biệt: nguồn tìm trên web có audit đầy đủ, receipt phát hiện thay đổi sau khi mua, marketplace đếm theo listing độc lập mà không lộ tên shop cho buyer, OCR box trên ảnh nhãn, trang Observe có số liệu thật.

### Must / Should / Could
- **Must:** Web search audit panel · Receipt page + nút buy · Observe dashboard.
- **Should:** `scripts/e2e.py` (Prompt phụ P3-4b; chuyển từ P4 sang vì P3 nắm testid). Phải green ở Phase 5.
- **Should:** marketplace panel · OCR box overlay trên ảnh nhãn · time slider.
- **Could:** panel learned vocabulary trên Observe (seed / learned, mapping gần đây). Nên làm nếu P2 làm stretch (c).

### Prompt chính P3-4 (effort: medium)
```text
You are P3, Phase 4 (T+4:15–5:15). Update .agent/plans/P3.md first.

GOAL
Show the differentiators clearly: sources found on the web with a full audit trail, buyer evidence receipts that detect
later changes, marketplace consensus without naming shops to buyers, OCR boxes on label images, and an observability
page with live counters and the scorecard.

CONTEXT
- README §7.2 S4 routes, docs/05 extended routes (orders, marketplace, web-search, image, eval metrics); receipts carry
  the chain head; marketplace findings never change the passport; retailer pages confirm, never accuse

BUILD
1. Web search audit (testid web-audit, operator/reviewer, on the case view and control room): queries → results (rank,
   title, domain, class chip OFFICIAL/RETAILER/LEAD, decision fetched/lead only/skipped + reason) → snapshots (url,
   captured time, sha256 short, passages count, "identity verified" or "confirm-only"). Buyer citations show the domain
   and capture time; "N REAL web sources" badge next to the SYNTHETIC listing badge.
2. Receipt: buy button on the buyer page (testid buy-button) → POST /orders → /orders/:id shows the frozen passport,
   snapshot hash, chain head, and a per-field diff then vs now (testid receipt-diff) with "changed since purchase" alert.
3. Marketplace: buyer → tally per field by independent listing clusters ("4 independent listings agree on 50 ml; 1
   differs"), no shop names; reviewer → shops, clusters, quotes (marked seller text), outliers with review links.
4. OCR: on image citations draw the returned boxes over the label image (GET /sources/{sv}/image?as_role=…), scaled to
   the displayed size.
5. Observe page: live counters from /internal/observability (verdict mix, model calls live/replayed/avoided by step,
   publish gate, agent/gap stop reasons, review queue, learned vocabulary), scorecard from /internal/eval/metrics when
   present ("not computed yet" otherwise), each number with its source and date.

CONSTRAINTS
- Buyer views never show shop names, model ids, JSON, rule codes or hashes; seller quotes are marked as seller text.
- Web audit and marketplace details only for REVIEWER/OPERATOR (the backend filters; the UI must not re-add them).
- Keep every data-testid of README §7.4 stable; no forbidden words in any string.

DONE WHEN
In phase: npm run build passes against the mock and the types generated from contract-<N>'s /openapi.json — do not
block on routes that still return 501.
At the Sync (P4 checks it on the merged code): Build passes; web audit renders for event 14 in replay; receipt diff appears after buy → revoke. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

### Prompt phụ P3-4b — E2E Playwright (effort: medium, thread 2 · từ đầu phase trên các trang đã có; thêm bước mới khi thread 1 xong trang mới)
```text
P3, Phase 4b. You own scripts/e2e.py (Python Playwright; dev deps in backend/requirements-dev.txt). It checks ports
8000/5173 answer and that GET /api/health reports LLM_MODE=replay and DEMO_RUN_DELAY_S ≥ 2 (else it exits asking me to start
both servers from the Codex app Actions `backend` and `frontend`); resets the demo; walks the click path of scripts/demo/storyboard.md (P4) — or, if
absent, the phase paths defined in scripts/sync_check.py (P4-1) — ONLY through the data-testids of README §7.4; asserts durable UI state: label per
field after each step, model-calls counter unchanged after 3 buyer refreshes, Stale visible after revoke then Not
verified, review decision present in the decisions list (assert on lists/history, never on a
transient form), agent panel shows a verified placement or an honest "no change", web audit has ≥1 snapshot; saves one
screenshot per step to scripts/demo/out/e2e/; prints PASS/FAIL per step; exit 1 on FAIL. Run it once against the merged
code and fix UI causes in frontend/** (CCR for backend causes).
Then scaffold scripts/demo/record_demo.py from the same steps (one function per storyboard scene; `--engine none`
works), so Phase 5 is only re-recording.
DONE WHEN: e2e.py runs end to end in replay and prints a PASS/FAIL line per step; record_demo.py --all --engine none runs.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 5 — Polish, wording, build tĩnh (T+5:15–6:00 · 15:15–16:00)

### Prompt chính P3-5 (effort: medium)
```text
You are P3, Phase 5 (freeze at T+6:00). No new features. (1) Run the full story in replay (backend LLM_MODE=replay,
DEMO_RUN_DELAY_S=3) at 1280×720 and fix layout issues: nothing important below the fold on the control room and buyer
pages, panels without inner scrollbars hiding content, captions not covering buttons, text ≥ 14 px. (2) Wording audit:
search all strings for forbidden words (EN+VI) and for overclaiming ("verified", "safe", "genuine", trust scores); buyer
copy in plain language. (3) Check every data-testid in README §7.4 exists exactly once per screen, and make scripts/e2e.py PASS in replay. (4) `npm run build`
and confirm dist/ works when served statically by the backend (tell P1/P4 the path). Report per AGENTS.md §6.
DONE WHEN: npm run build passes; e2e.py PASS in replay; no forbidden word found; every testid present.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Prompt phụ P3-5b — quay segment video (effort: medium, thread 2 · sau tag `rec-freeze`)
```text
P3, Phase 5b. You own scripts/demo/record_demo.py (moved from P4: it reuses your E2E steps). One function per scene of
scripts/demo/storyboard.md (P4 wrote it), using the mvp-demo kit imported from DEMO_KIT_DIR (~/.agents/skills/mvp-demo/
scripts): default to no voice/TTS/music, pass clips={}, use callouts and reading holds, camera-ready CSS (zoom on panels;
reserve subtitle space only if captions are actually used). Reset before each take (POST /api/internal/demo/reset), UI
driven only through data-testids, fast-forward uninteresting waits and hold on results. Keep narration.json={} unless
the user requests voice later. First, in the Local checkout whose backend the video uses: `git fetch --tags; git merge
rec-freeze` (recordings and the final storyboard) and restart the app Action `backend`. Finish and commit UI polish
before 15:35 so the UI does not change between takes. Check that the backend reports LLM_MODE=replay and DEMO_RUN_DELAY_S ≥ 2.
CLI: --scene <id> | --all, --engine none|silent|edge (default none). In the default none mode do not invoke tts(), beat(),
on_words() or finish(); use chip()/hold()/at(). edge requires an explicit user request and an optional package install.
Record into a folder outside the repo (DEMO_OUT, default $HOME\demo-segments; video files are never committed) and
hand it to P4 over a shared folder or USB; P4 assembles, checks and uploads. Recording may run until about 16:05.
DONE WHEN: every storyboard scene has a segment file; check_overlaps from the kit reports no problems.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

## Phase 6 — Hỗ trợ video + write-up (T+6:00–7:00)
- 6 screenshot sạch theo danh sách trong P3-6, gửi P4 trước **16:15**.
- Phase 5 (P3-5b) bạn đã quay các segment; giờ hỗ trợ P4 ghép video không giọng: CSS "camera-ready", zoom vào panel; chỉ chừa chỗ phụ đề nếu có dùng. Sửa lỗi UI chặn video trong phạm vi P3.

### Prompt chính P3-6 (effort: medium)
```text
You are P3, Phase 6 (T+6:00–7:00). Code is frozen except UI blockers found while recording. (1) With the backend in
LLM_MODE=replay and DEMO_RUN_DELAY_S=3, take 6 clean 1280×720 screenshots with Playwright into docs/results/screens/:
buyer passport (R2, or another REAL product if R2 was not captured), evidence drawer, conflict in source (R1, or its
labelled synthetic twin S2 if R1 was blocked) with Why?, reviewer queue, agent panel (before/after),
web audit panel. No secrets, no personal data, REPLAY/REAL/SYNTHETIC badges visible. (2) While P4 runs $mvp-demo, fix
only what blocks the video (subtitle overlap, hidden panels, text too small) and tell P4 which segment to re-record.
DONE WHEN: 6 screenshots in docs/results/screens/ sent to P4 before 16:15; no open video blocker.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

## Stretch backlog
1. Panel learned vocabulary.
2. Diff passport trước/sau một event.
3. Slider time travel.
4. Hiện bản nháp reviewer copilot (nếu P2 làm).

## Q&A prep (P3 trả lời)
- *Buyer có hiểu thành "hàng thật" không?* → Không có điểm tổng hay badge tổng. Mỗi field có câu trạng thái riêng, có disclaimer, có test chặn từ cấm.
- *Vì sao "Conflict in source" không màu đỏ?* → Vì không phải lỗi của seller. Màu khác với "Conflicting" để buyer không đổ lỗi nhầm.
- *Giám khảo kiểm chứng bằng cách nào?* → Bấm "View evidence" thấy đoạn trích gốc. "Why?" cho thấy toàn bộ đường đi của quyết định.
