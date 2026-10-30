# P1 — Backend core: dữ liệu, luật, API

> P1 xây "bộ não bằng code": nhận event, quản lý version và revision, chạy run, áp policy có version, chặn mọi thứ qua publish gate, và phục vụ toàn bộ REST cho UI.
> Model không bao giờ quyết định verdict. Toàn bộ phần quyết định nằm trong code của P1.

## 0. Bạn sở hữu gì, phụ thuộc ai

- **Sở hữu:**
  - `backend/app/{db,seed,store,trace,worker,chain,context}.py`
  - `backend/app/events/**`, `backend/app/api/**`
  - `backend/app/pipeline/{run,policy,compare,publish,gaps,marketplace,scheduler}.py`
  - `backend/app/connectors/registry.py`
  - test: `test_policy, test_events, test_publish, test_staleness, test_reviews, test_chain, test_scope, test_gaps, test_glassbox, test_orders, test_marketplace`
- **Cung cấp:**
  - Cho P2: `RunContext`, `TraceWriter`, `store.add_source_version`, `compare.*`, `policy.decide`, `SourceObs`.
  - Cho P3: toàn bộ REST (README §7.2). Thêm `response_model` để P3 sinh type từ `/openapi.json`.
  - Cho P4: `seed.load_product_dir()`.
- **Phụ thuộc:**
  - P2: `extract_source_version`, `normalize.*`, `Budget`, `scope_resolution.resolve_all`, `claims_audit.audit`, `retrieval.search`, `web_sources.discover`, `ocr.boxes_for`. Trước khi P2 xong, P1 dùng stub do P4 tạo.
  - P4: `models.py`, `config.py`, `main.py` (muốn thêm field hay route mới thì gửi CCR cho P4).

## 1. Nhịp mỗi phase

1. Đầu phase: `git fetch --tags; git merge sync-<N-1>` trên branch `p1` (mỗi người một branch cho cả ngày).
2. `$phase-kickoff P1 <N>`. Phase 0 thì dán thẳng Prompt chính cho nhanh.
3. **Commit hợp đồng trước, push trước T+20:** commit đầu tiên của phase chỉ gồm route và hàm mới ở dạng stub (route có `response_model`, trả 501 hoặc dữ liệu ví dụ; hàm đúng signature README §7.1), message `S<N> P1: contract`. P4 merge riêng commit này ở mini-sync, P3 sinh type từ đó. Sau mini-sync, `git fetch --tags; git merge contract-<N>` (Phase 1: có luôn test nghiệm thu phase 1 của P4).
4. Thread 2: chạy Prompt phụ, **chỉ viết test hoặc sửa file khác thread 1**. Bug tìm được ghi vào ExecPlan để thread 1 sửa.
5. T−20: `$self-review` rồi push (trước T−10). Push commit contract chỉ cần pytest và `test_guards.py`.

**Skill Codex dùng trong lane này** (cài ở `~/.agents/skills`, gõ trong ô chat của Codex):

| Khi nào | Gõ | Kết quả |
|---|---|---|
| Đầu mỗi phase | `$phase-kickoff P1 <N>` | Codex đọc section phase, cập nhật ExecPlan, hỏi nếu dính trigger, rồi chạy Prompt chính |
| Test đỏ hoặc verdict sai | `$trace-debug <tên test hoặc field>` | Tìm bước đầu tiên đi sai trong trace, viết test tái hiện, sửa đúng gốc lỗi (file của lane khác thì gửi CCR), ghi "Notable loop" vào CODEX_LOG |
| Xong sớm, bị kẹt, phải chọn cắt gì | `$brainstorm <options / cut / qa> <bối cảnh>` | Phương án xếp hạng kèm prompt dán được ngay, không viết code |
| T−20 mỗi phase | `$self-review` | Chạy test và build, quét hardcode, từ cấm, gold, secret, kiểm lane, contract, ExecPlan → `READY TO PUSH` hoặc `BLOCKED` |

**Effort:** `high` cho phase có policy (1, 2), `medium` cho các phase còn lại.

---

## Phase 0 — Nền móng (T+0:00–0:30 · 10:00–10:30)

### Mục tiêu
Có DB đủ schema cho cả ngày, seed generic nạp được mọi product fixture, `store.add_source_version` idempotent, `TraceWriter` ghi được trace.

### Must / Should / Could
- **Must:** `db.py` (đủ bảng), `seed.reset()` + `seed.load_product_dir()` + `seed.seed_if_empty()`, `trace.py`.
- **Should:** `store.py` (idempotent theo sha256) + test.
- **Could:** chỉ mục FTS5 cho passages.

### Prompt chính P1-0 (effort: medium) — chạy từ 10:05, dán thẳng (không cần kickoff)
```text
You are P1 (Backend core), Phase 0 (T+0:05–0:30). AGENTS.md is loaded; create .agent/plans/P1.md from .agent/PLANS.md
and update it as you go. db.py, seed.py, store.py and trace.py are NEW files you create (P4 does not stub them).

GOAL
A SQLite store with the full schema for the whole day, a generic seed that loads any product fixture folder, an
idempotent source-version writer, and a trace writer — so that every later phase only adds behaviour, never tables.

CONTEXT (batch-read)
- docs/04-data-model.md: "Tables" AND "Extended schema" (build all of them now)
- docs/DATASET-SPEC.md §2 (snapshot, product, event, registry, marketplace formats) and §7 (which fixtures exist when).
  Fixtures are generated on the day by P4: at S0 only the first synthetic product (S1) and events 01–03/08 exist; more
  arrive at S1–S4 (fixtures/{synthetic,real,blind}/<product>/, fixtures/events/, fixtures/marketplace/<product_id>/,
  fixtures/synthetic/registry/mock_registry.json). Your unit tests build their own inputs; never depend on fixture text.
- backend/app/{config,models}.py are P4's and land on main around 10:20 (P4 commits the skeleton directly on main): until then take DB path and fixtures dir as
  parameters, then `git fetch; git merge origin/main` and read them from settings. backend/app/context.py is yours (P4 creates the stub — keep the
  RunContext signature of README §7.1). README §7.1 rows for store/trace

BUILD
1. backend/app/db.py: connect() (row factory, foreign keys, WAL, utf-8), transaction() context manager, init_db()
   idempotent, dumps/loads JSON helpers, now_iso(). Tables: everything in docs/04 incl. the as-built extras (passage_scopes,
   extraction_cache, vocab, ocr_lines, marketplace_findings, orders, web_searches, products.web_json, field_results
   explain_json/notes_json/stale_reason/stale_at/confirmed_run_id/confirmed_at/reviewed_by/prev_hash/chain_hash/chain_seq,
   runs stop_reason/usage_json/budget_json/error, trace_steps detail/t_ms) plus contest additions: embeddings(passage_id
   PK, source_version_id, model, content_hash, vector_json, created_at), passages_fts (FTS5: text, passage_id,
   source_version_id), products(+price_vnd, shop_name, official_store, image_path) taken from listing data.
2. backend/app/store.py: add_source_version(snapshot, *, case_id, origin, raw_path=None) -> SourceVersionRef:
   sha256 over the raw bytes (or canonical JSON), same source_id + same sha → return the existing version (no new row,
   rule 10); newer version → mark previous is_current=0 / SUPERSEDED; insert passages + FTS rows; afterwards call the
   hooks retrieval.search.index_source_version(sv_id) and pipeline.ocr.index_image(sv_id) inside try/except that only
   traces the error (hooks are P2's; stubs exist). passages(sv_id), current_sources(case_id).
3. backend/app/seed.py (also seed_if_empty() -> bool: init_db, then reset() only when no product row exists — P4's
   startup hook in main.py calls it): load_product_dir(path, *, case_id_override=None) — generic for any folder with product.json +
   *.v1.json (version 1 only; later versions arrive through events), picks up a sibling image (same stem .png/.jpg) as
   raw_path for PACKAGING_IMAGE, copies listing commerce fields (price_vnd, shop_name, official flag if present) to the
   product row, skips (with a logged warning) any folder whose files contain the uppercase marker "TODO" (case-sensitive: a key like
   "image_todo" in the main DEMO label must not skip it). reset(): fresh DB, init_db, load
   every product folder (a folder with product.json) under fixtures/synthetic and fixtures/real — whatever exists
   (blind sets are loaded only by scripts/blind_eval.py). Nothing product-specific in code (no ids, no names):
   everything comes from the files.
4. backend/app/trace.py: TraceWriter(run_id) with step(...) and timed(...) exactly as README §7.1; seq per run; t_ms =
   offset from the run start (survives re-instantiation for the same run).
5. Tests (phase 0): seed loads all synthetic products with revision 0; re-seeding is idempotent; add_source_version with
   identical content returns the same id and adds no passages; a TODO folder is skipped; trace rows have increasing seq.

CONSTRAINTS
- Only your files. models/config are P4's: request missing fields via CCR (end of report).
- No product-specific logic anywhere (AGENTS §4). utf-8 for every open. No heredoc edits.

DONE WHEN
`pytest -q` (phase 0) green; `python -c "from app import seed; seed.reset()"` loads every product folder that exists (at S0: the S1 product from P4-0c);
report per AGENTS.md §6 incl. product/case/source counts.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Done-check S0
`.venv/Scripts/python ../scripts/seed.py` (khi P4 đã có script) hoặc chạy `seed.reset()` · `pytest -q`.

### Rủi ro dự kiến (phòng hờ)
- Seed crash khi listing không có `scope`: dùng `s.get("scope") or {}`.
- Không được chạy fixture còn `TODO`.

---

## Phase 1 — Xương sống: Event → Passport (T+0:30–1:45 · 10:30–11:45)

### Mục tiêu
Operator bấm "Bootstrap" thì event được admit, job chạy, claim (fallback) được chuẩn hóa, policy quyết định, publish gate cho qua, kết quả được ghi theo version, và Buyer thấy 5 field có citation. Event giá → NOOP, event lặp → DUPLICATE, producer lạ → REJECTED. Đọc passport không tạo ra bất cứ thứ gì.

### Must / Should / Could
- **Must:**
  - `events/admit.py`, `worker.py`, `pipeline/run.py`;
  - `policy.py` R1–R11 + REQ + templates + explain trail;
  - `compare.py`, `publish.py`;
  - API S1 (README §7.2), gồm `GET /api/internal/metrics` (passport_reads, model calls live/replayed) vì P3 và AC-13 cần nó;
  - AC phase 1 phần của P1 xanh.
- **Should:** `response_model` cho mọi route.
- **Could:** run re-confirm, tức là quyết định không đổi thì giữ nguyên `result_version` và chỉ ghi `confirmed_run_id`.

### Prompt chính P1-1 (effort: high)
```text
You are P1 (Backend core), Phase 1 (T+0:30–1:45). Update .agent/plans/P1.md (Phase 1 milestone) first; keep it living.

GOAL
The event → run → passport backbone with code-decided, cited, versioned results. After this phase an operator can fire
01-bootstrap-demo and a buyer sees five fields with labels and citations (LLM_MODE=fallback), and the Phase 1 tests in
backend/tests/test_acceptance.py pass.

CONTEXT (batch-read)
- docs/05-contracts.md §1 (envelope + admission rules in order), §2 (routes), passport response
- docs/06-policy-rules.md (ordered rules 1–11, field evidence requirements incl. the REQ notification rule, review triggers, public text
  templates, forbidden words), docs/04-data-model.md (buyer label mapping, dependencies), docs/03-architecture.md (run
  lifecycle, invariants)
- Known risks (planning estimates — verify, do not assume): a revoke must not be masked by the label still printing
  the number (REQ); public text should lead with the agreed value; company legal-form variants; skin-type
  compatibility is directional
- backend/app/{models,config,context,budget}.py, pipeline/{extract,normalize}.py (P2: stubs/fallback today),
  backend/tests/test_acceptance.py (phase 1 targets), README §7.1–7.3

BUILD
1. events/admit.py — admission in the documented order: producer allowlist + role per event type (allowlist as data in
   config, not scattered literals) → REJECTED; idempotency key seen → DUPLICATE with zero side effects; LISTING_CHANGED
   with changed_fields ⊆ non-material set → NOOP; otherwise mark dependents STALE (results whose depends_on contains the
   source; same transaction), bump case.revision, enqueue one job per case (coalesce: a QUEUED job for the case gets its
   target revision updated instead of a new job). Return AdmitResult with stale_fields. Record every event row with its
   outcome and reason.
2. worker.py — asyncio queue started by the app; WORKER_INLINE=1 runs the job inside the request (tests);
   DEMO_RUN_DELAY_S delays the start (stage pacing). One job at a time per case.
3. pipeline/run.py — run(job): create run row (mode, models, prompt versions, policy version, budget caps), RunContext
   with Budget.from_settings(), pin the case revision, load current source versions + passages, extract each usable
   source via extract.extract_source_version(sv_id, ctx) (cached by P2), compute source scope (metadata today; inference
   comes in Phase 2), public-field policy pass → claims_audit hook (Phase 1 stub returns []; in Phase 2 it delegates
   each claim:* finding to this same policy.decide) → publish gate → write field_results: append-only
   result_version per field, depends_on = sources used (INSUFFICIENT results also depend on the sources their field
   requirement names, so a new document reopens them), explain_json = the rule trail, public_text from templates.
   Same decision as the current version → keep result_version, set confirmed_run_id/confirmed_at (no new row).
   Run status precedence: FAILED (no result could be produced) > PARTIAL (budget/deadline stop_reason) >
   WAITING_REVIEW (any NEEDS_REVIEW) > WAITING_EVIDENCE (open request) > COMPLETED. Store usage from ctx.budget.usage()
   at the END of the run (counts every model call incl. later steps). Trace each step with README §7.3 names.
4. pipeline/compare.py — compatible(field, claim, ref) DIRECTIONAL (listing ALL is not supported by reference {DRY};
   claim ⊆ reference or reference ALL), agree(field, a, b) symmetric for reference-vs-reference, same_volume(a, b,
   tol=0.01) (P2's scope pre-pass and anchor check import it — keep the name), volume within 1%,
   identifiers exact after normalisation, key_ingredients ⊆ highlights ∪ INCI of the reference. Name the direction in
   the function names/docstrings. compare works on already-normalised values (P2's normalize produces
   them; your tests build them directly) — never parse raw text here, never a second unit regex (AGENTS §4).
5. pipeline/policy.py — POLICY_VERSION="policy-v1"; SourceObs dataclass; decide(field_key, observations, product, gaps,
   reviews) -> FieldDecision implementing rules 1–10 in order: access, validity (REVOKED/SUPERSEDED excluded but kept in
   history), scope (UNKNOWN → at most UNCERTAIN; MISMATCH excluded with reason), SELF-CONFLICT FIRST (incompatible values
   inside one source version → CONFLICTING/WITHIN_SOURCE, seller_attributable false, NEEDS_REVIEW, that source not used
   against the listing for this field), compare, "not mentioned ≠ negated", independence by source family (listing
   included) → SINGLE_SOURCE, CONSISTENT needs ≥2 independent families + scope MATCH, LISTING_VS_SOURCE → NEEDS_REVIEW,
   missing → INSUFFICIENT + Gap; field requirements: notification_number/responsible_company need an ACTIVE
   NOTIFICATION_DOC (Phase 3 adds REGISTRY_RECORD) among the cited sources. Every rule appends a RuleStep
   (rule id as in docs/06, outcome, detail) — this is the "Why?" trail. Public texts from the docs/06 templates and
   they lead with the agreed value, e.g. "50 ml — consistent across 2 independent sources checked: …".
6. pipeline/publish.py — gate(decision, run, case): each citation's passage exists in its source version, excerpt ⊆
   passage text (one contiguous excerpt after NFC + whitespace collapse, docs/05 §3; same rule as extraction), source ACTIVE, forbidden wording absent (regex from docs/06, EN+VI), run's
   pinned revision == case.revision (else trace SUPERSEDED_RUN, nothing written), non-INSUFFICIENT needs ≥1 citation.
   Blocked → trace publish:blocked with reason; never publish partially.
7. api/ — X-Demo-Role / X-Demo-Actor dependency checked on every route (403 when the role may not call it). Routes of
   README §7.2 row S1, with response_model. Passport for BUYER: PRIVATE citations removed and counted in
   hidden_citations; buyer labels per docs/04 mapping (STALE first, … , FAILED → "Could not update"); disclaimer; reads
   increment a passport_reads counter only — never create jobs/runs/events/model calls (rule 6). Evidence route: public
   passages for BUYER, all for REVIEWER/OPERATOR. demo/fire/{name} loads fixtures/events/<name>.json (payload.snapshot paths are relative to fixtures/) and
   admits it; demo/reset calls seed.reset(). GET /internal/events/catalog lists the fixture events as {name, type,
   product_id, resource, expect} (P3 uses `expect` as stage captions); GET /internal/events/log lists recent events with
   outcome, reason, stale_fields and the run they enqueued.
8. Tests (yours): test_policy.py (one test per rule incl. directional skin type, family independence, self-conflict
   before compare, REQ, scope mismatch, not-mentioned-not-negated, value-led text), test_events.py (NOOP, DUPLICATE,
   REJECTED, coalescing, SUPERSEDED_RUN), test_publish.py (each gate failure). Use synthetic inputs built in the test,
   not the demo fixtures, for unit tests.

CONSTRAINTS
- The model never sets a verdict: policy reads normalised claims only. No model calls in policy/publish/admission.
- No product ids, names or demo texts in app code (tests/test_guards.py checks). Producer allowlist, non-material fields,
  forbidden words: closed sets in config/data with a comment on their source.
- Only your files; CCR to P4 for models/config changes, to P2 for normalize/extract behaviour.

DONE WHEN
- `$env:CONTEST_PHASE=1; .venv/Scripts/python -m pytest -q` green incl. test_acceptance phase 1 (from contract-1); `.venv/Scripts/python ../scripts/sync_check.py 1` PASS at the Sync.
- Manual: uvicorn + Operator fire 01 → GET passport shows the S1 expectations of docs/DATASET-SPEC.md §4 (volume
  CONSISTENT, skin_type SINGLE_SOURCE, key_ingredients CONSISTENT, notification_number and responsible_company
  CONSISTENT; the other-market page excluded by scope). Acceptance tests that need P2's unmerged code may be WAITING.
- Report per AGENTS.md §6.

IF UNSURE
- Rule semantics: docs/06 wins; a gap in the docs that changes a verdict → ask me (trigger 5) with your default.
```

### Prompt phụ P1-1b — kiểm chéo policy trên input lạ (effort: medium, thread 2 · bắt đầu khi thread 1 đã commit compare.py và policy.py)
```text
P1, Phase 1b. Write property-style tests for compare.py and policy.py on inputs not taken from the fixtures: unit
variants (473ml, 473 ml, 16 fl oz, 0.473 L), Vietnamese and English skin phrases via normalize (P2), passage order
shuffled, two references disagreeing with each other (ACROSS_SOURCES), listing copied from the brand page (same family),
legal-form variants of a company (Cty TNHH, Công ty CP, JSC, Co., Ltd). Expected verdicts derive from docs/06 only.
You are thread 2: write tests only (backend/tests/test_policy_props.py); do NOT edit compare.py or policy.py — a failing
case goes into the ExecPlan "Surprises" list for thread 1, a normalize gap into a CCR to P2. Never weaken a test.
DONE WHEN: the new test file runs; every failure is listed with its input and the rule from docs/06 it violates.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Bàn giao ở Sync 1
Các route S1 đã chạy, có `response_model` → báo P3 chuyển sang API thật · `policy-v1` · README §7.3 step names đã dùng.

### Rủi ro dự kiến (phòng hờ)
- Revoke không đổi gì vì nhãn bao bì vẫn in số công bố → cần REQ.
- Câu "Consistent across 2 sources" không nói đồng ý về giá trị gì.
- `compatible` đối xứng với wildcard ALL làm sai chiều.
- INSUFFICIENT không có depends_on nên không bao giờ stale.

---

## Phase 2 — Mâu thuẫn nguồn + vòng đời sự kiện (T+1:45–3:00 · 11:45–13:00)

### Mục tiêu
Vòng đời "wow": revoke làm **ngay lập tức** (không job, không model) 2 field notification STALE, sau đó re-assess thành INSUFFICIENT kèm evidence request. Seller upload S1-up: company về CONSISTENT, notification_number mới khác listing → CONFLICTING + NEEDS_REVIEW; các field còn lại theo bằng chứng. Listing đổi volume → CONFLICTING → reviewer duyệt đúng một revision. Có PARTIAL khi hết budget. Thread 2 làm scope inference khi thiếu metadata và copy detection (P1-2c).

### Must / Should / Could
- **Must:**
  - ingest version mới + revoke + STALE trong admission;
  - re-assess; gaps → evidence_requests (mở/đóng);
  - reviews API (approve/override/reject, 409, override qua gate) + queue + history;
  - upload evidence; PARTIAL từ budget;
  - `policy.decide` xử lý `claim:*` theo CL; P1 sở hữu verdict, review_state và public_text cuối cùng;
  - AC phase 2 phần của P1 xanh.
- **Should (thread 2, Prompt phụ P1-2c):** scope inference R3 (sửa lỗi ccTLD) + passage-level · copy detection R7c.
- Đã chuyển đi: hash chain → P1-3b (Phase 3, thread 2) · time travel `as_of` → stretch backlog · sync docs → P1-5.

### Prompt chính P1-2 (effort: high)
```text
You are P1, Phase 2 (T+1:45–3:00). Update .agent/plans/P1.md first.

GOAL
Event-driven freshness and the human review loop: a source event stales exactly the dependent fields inside admission
(no job, no model), the following run re-assesses them, evidence requests open and close by themselves, and a reviewer
decision binds to one result + case revision. (Scope inference and copy detection run in thread 2 as P1-2c; the hash
chain moves to Phase 3.)

CONTEXT
- docs/05 §1–§2 (admission per event type, reviews,
  evidence routes), docs/06 (R3 inferred, R3p, R7c, REQ, IMG, CL, review triggers, override rule R11+), docs/04 (tables)
- Known risks (estimates): budget must cover the whole run; overrides must pass the publish gate; hash only immutable
  columns; time travel recomputes freshness; generic ccTLDs (.co, .io) are not markets
- fixtures/events/04..10 (payload.snapshot paths relative to fixtures/, expect notes), backend/tests/test_acceptance.py phase(2)
- P2's Budget/BudgetExceeded (README §7.1) and claims_audit.audit signature

BUILD
1. Admission per event type (one transaction each): LISTING_CHANGED material / SOURCE_CHANGED / EVIDENCE_ADDED with
   payload.snapshot → store.add_source_version as the new current version (out-of-order guard: an older resource.version
   never replaces a newer one → NOOP with reason), mark dependents STALE with stale_reason + stale_at, bump revision,
   enqueue. SOURCE_REVOKED → source status REVOKED, dependents STALE, bump, enqueue. EVIDENCE_ADDED (role SELLER via
   seller-portal or REVIEWER) also stales results that have an open gap/request for the named fields. Admission has no
   run yet: store stale_fields on the event row, and make the run it enqueues write `stale:mark` as its FIRST trace step
   (detail {event_id, fields, model_calls: 0, admitted_at}) so the UI can show "marked stale — no model call".
2. Re-assessment: revoked sources excluded from conclusions (kept in history); a field whose only support was revoked
   becomes INSUFFICIENT with freshness CURRENT after the run. Gaps → evidence_requests (requested_from SELLER, reason from
   the gap); IMG rule: an UNREADABLE image claim opens "a clearer photo of the label" request; requests close
   (FULFILLED) when the field is no longer insufficient/unreadable.
3. Reviews: GET /review/queue (open tasks with field, reason_code, current verdict), POST /cases/{id}/reviews {result_id,
   case_revision, decision APPROVE|OVERRIDE|REJECT, reason, override?} → 409 if case_revision ≠ current; OVERRIDE writes
   a REVIEWED result version that goes through publish.gate (no citation → only INSUFFICIENT allowed → else 422
   NO_CITATION; forbidden wording → 422); a new case revision supersedes earlier reviews (SUPERSEDED). GET
   /cases/{id}/history (result versions, events, reviews, requests). POST /cases/{id}/evidence (SELLER/REVIEWER upload of
   text or image → stored under fixtures/uploads/ → EVIDENCE_ADDED through admission; seller uploads get their own
   family and PRIVATE visibility).
4. Budget outcome: catch BudgetExceeded from any step → keep code-verified results, run PARTIAL with stop_reason
   (from the exception), trace run:stop. A model error in an optional step must not fail the run (P2 traces it); a model
   error before any claim exists for a required source → that field INSUFFICIENT with gap MODEL_ERROR, run PARTIAL.
5. Claim policy (pipeline/policy.py, P1 owns the implementation): extend the existing
   decide(field_key, observations, product, gaps, reviews) -> FieldDecision to handle claim:<kind>:<detail> using
   SourceObs normalised by P2's claims_audit.audit(ctx, listing_obs, observations). Implement docs/06 CL here:
   free-from vs INCI (seed patterns → CONFLICTING; model-only membership → UNCERTAIN), concentration plausibility from
   INCI order + regulatory_limits.json, and treatment wording → review. P1 alone sets the final verdict, review_state
   (all non-consistent claim findings → NEEDS_REVIEW), rule trail and neutral public_text. P2 extracts and quote-checks
   findings, delegates each to policy.decide, then returns those FieldDecision rows unchanged. Keep SourceObs,
   FieldDecision and both public signatures unchanged. Run order stays public-field policy → claims_audit (delegating
   claim policy) → the same publish gate; buyers see only a neutral count until review.
6. Tests: test_staleness (AC-06 incl. same result_version for unaffected fields and 0 model calls at admission),
   test_reviews (AC-15, override gate, supersede), and test_policy CL cases using normalised SourceObs, including
   model-only family membership, non-consistent review gating and neutral public text.

CONSTRAINTS
- Admission never calls a model and never runs policy; it only records, stales, bumps and enqueues.
- Review/override paths go through the same publish gate as runs (rule 2). Every rule change bumps POLICY_VERSION
  (AGENTS §3 rule 3) with a note in docs/tracking/DECISIONS.md.

DONE WHEN
`CONTEST_PHASE=2 pytest -q` green for your tests and AC-06/09/12/15/17 (with P2's budget); `sync_check.py 2` PASS;
manual: fire 05-revoke-notification → passport shows STALE on exactly two fields before the run finishes
(DEMO_RUN_DELAY_S=3), then INSUFFICIENT + request. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Prompt phụ P1-2c — scope inference + copy detection (effort: high, thread 2 · từ đầu phase, file riêng)
```text
P1, Phase 2c (thread 2, files: backend/app/pipeline/scope.py — new — and its tests; thread 1 owns policy.py and calls
your functions). Implement and test:
1. Scope inference (docs/06 R3) when a source has no scope metadata: the product's own evidence kinds are in scope;
   market from a country-code TLD only when the TLD is a real market code and not in a generic list kept as data
   (co, io, ai, me, tv, …; review M6); a page naming one size → in/out by that size (use normalize.volumes_in +
   compare.same_volume); several sizes → passage-level (needs_scope_resolution=True on the decision; Phase 3 resolves);
   none → product level. Policy uses passage_scopes rows when present (MATCH used, MISMATCH excluded, AGENT used but
   forces NEEDS_REVIEW).
2. Copy detection (R7c): if every listing passage stating the field is a near-copy (5-char shingle Jaccard ≥ 0.8,
   passage ≥ 30 chars) of one reference source, the listing joins that family for this field; explain says so.
3. Expose infer_scope(source, product) -> ScopeDecision and listing_copies_reference(listing_passages, reference) ->
   bool; thread 1 wires them into policy.decide. Tests in backend/tests/test_scope.py: .co/.io domains are not markets,
   a page naming exactly one other size, a page with several sizes → passage level, copied listing joins the family.
DONE WHEN: test_scope.py green; the two functions are documented in the ExecPlan for thread 1.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Rủi ro dự kiến (phòng hờ)
- Override publish CONSISTENT mà không có citation.
- Không bao giờ set PARTIAL (review H3).

---

## Phase 3 — Gap controller + glass box (T+3:00–4:15 · 13:00–14:15)

### Mục tiêu
- Field notification thiếu hồ sơ → code tự đi các hop: lấy số từ nhãn → tra mock registry → so người giữ số với công ty → dừng với stop reason rõ ràng.
- Mọi verdict giải thích được ("Why?"), có trace export OTel, có số liệu observability, dependency graph, kiểm chain.
- Gắn bước agent (scope resolution của P2) vào run, ghi lại "agent đã đổi gì".

### Must / Should / Could
- **Must:** `gaps.py` + `connectors/registry.py` · explain endpoint lọc theo role · gắn `scope_resolution.resolve_all` vào run (pass 2) + trace `agent:effect` · observability counters.
- **Should (thread 2, Prompt phụ P1-3b):** hash chain + `GET /cases/{id}/chain` · graph · search route. **Could:** OTel export.
- **Could:** revoke đối chiếu thêm với registry ("registry lists this number as revoked").

### Prompt chính P1-3 (effort: high)
```text
You are P1, Phase 3 (T+3:00–4:15). Update .agent/plans/P1.md first.

GOAL
(1) A code-decided multi-hop gap controller with explicit stop reasons; (2) a glass box: every published verdict
explainable without re-running anything, filtered by role; (3) the agent step wired into the run so its effect on a
verdict is recorded and visible.

CONTEXT
- docs/06 "Gaps" row + REQ with registry (gap controller over a mock registry); the "Why?" decision trail (glass box)
- docs/05 §2 Phase 3 routes (explain, otel, observability, graph, chain, search)
- fixtures/synthetic/registry/mock_registry.json (SYNTHETIC, fictional numbers), events 12-bootstrap-sun-fluid,
  09-catalogue-published
- README §7.1 (scope_resolution.resolve_all, retrieval.search signatures), §7.3 step vocabulary

BUILD
1. connectors/registry.py: lookup(number) → record or None from the mock file (labelled MOCK/SYNTHETIC in every output).
2. pipeline/gaps.py close_gaps(ctx, decisions, observations): for gap NO_ACTIVE_NOTIFICATION_DOC → hop1 join key (a
   notification number from a validated claim on the label/listing; none → stop NO_JOIN_KEY) → hop2 registry lookup
   (≤2 lookups, already checked → ALREADY_CHECKED, missing → NOT_FOUND) → the record becomes a REGISTRY_RECORD source
   version via store.add_source_version (cited like any source; REVOKED record → source REVOKED + note "the registry lists
   this notification number as revoked") → hop3 compare holder with responsible_company claims (compare.*) → re-run
   policy for the two fields → stop GAP_CLOSED / REVOKED_IN_REGISTRY. Each hop traced gap:hop<n>:<name>, counted against
   ctx.budget (take_tool), idempotent across runs. REQ now accepts an ACTIVE REGISTRY_RECORD (bump POLICY_VERSION, note).
3. run.py: after policy pass 1, if any decision needs_scope_resolution → scope_resolution.resolve_all(ctx, observations,
   fields) (P2) → reload passage scopes → policy pass 2 → for every field whose verdict changed, trace agent:effect with
   {field, before, after, passages, decided_by}. Then gaps.close_gaps. BudgetExceeded anywhere → PARTIAL as in Phase 2.
4. Glass box routes (role-filtered in the backend, never in the UI only):
   - GET /products/{id}/fields/{f}/explain → trigger event → source snapshots (sha256, captured_at, origin) → claims
     (extractor, prompt_version, mapped_by, quote) → rule trail (explain_json) → publish gate checks → chain head →
     reviews. BUYER: public sources only, plain-language rule summaries, no model ids / JSON / hashes / rule codes;
     REVIEWER/OPERATOR: everything.
   - GET /internal/observability → verdict mix, model calls live/replayed/avoided (cache hits, NOOP, DUPLICATE) by step,
     publish gate pass/blocked, agent and gap stop reasons, learned vocabulary counts (seed vs model, recent mappings),
     review queue size/age.
5. Tests: test_gaps (sun fluid closes the gap; revoked registry record; no join key), test_glassbox (buyer explain has
   no private source/model id/rule code; reviewer explain complete; observability counts a NOOP as avoided), run test
   that a verdict changed by scope resolution produces agent:effect.

CONSTRAINTS
- Hops are decided by code; the model never chooses a registry or a verdict here. Registry output is always labelled
  MOCK. Buyer reads still create nothing (rule 6) — explain is a pure read.

DONE WHEN
In phase: your tests and the phase(3) acceptance tests that need only P1 are green (`$env:CONTEST_PHASE=3`). At the
Sync, once P2's scope resolution is merged: the full phase(3) suite and sync_check.py 3 PASS; manual: Why? for skin_type
after 09-catalogue-published shows the code pre-pass and the agent effect. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Prompt phụ P1-3b — hash chain, graph, search (effort: medium, thread 2 · từ đầu phase, file riêng)
```text
P1, Phase 3b (thread 2, files: backend/app/chain.py, backend/app/api/observe.py routes below, tests). Implement:
1. chain.py: per case, each new result version gets chain_seq, prev_hash, chain_hash = sha256 over immutable columns
   (field_key, result_version, case_revision, verdict, conflict_locus, public_text, citations_json, explain_json,
   seller_attributable, review_state at creation, policy_version, created_at); reviews create new chained rows instead of
   mutating hashed columns. verify(case_id) → {valid, rows, head | broken_at}.
2. GET /cases/{id}/chain (verify), GET /cases/{id}/graph (sources → fields that depend on/cite them; revoked/stale
   marked), GET /cases/{id}/search?q=&mode= (REVIEWER/OPERATOR; calls retrieval.search with allowed_sv_ids = the case's
   usable sources; returns hits + stages; never an answer). Tell thread 1 to call chain.append() when it writes a result.
3. Could, only if 1–2 are green: GET /internal/runs/{id}/otel → OTLP/JSON spans per the OpenTelemetry GenAI conventions
   (invoke_agent, execute_tool, chat; no content).
DONE WHEN: test_chain (valid after the story; broken after tampering explain_json in the DB) and route tests green.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Rủi ro dự kiến (phòng hờ)
- Hash chain báo invalid dù không ai sửa, vì có cột thay đổi theo thời gian.
- Bộ đếm usage chỉ tính extraction, bỏ sót agent và các step sau (review H2). Phải tính khi run kết thúc.
- Nhãn "mock" phải hiện ở mọi chỗ registry xuất hiện.

---

## Phase 4 — Receipt, marketplace, web policy (T+4:15–5:15 · 14:15–15:15)

### Mục tiêu
- Đơn hàng "đóng băng" Passport thành receipt có hash. Khi có thay đổi sau lúc mua thì báo cho buyer.
- Marketplace consensus đếm theo listing độc lập.
- policy-v2 cho trang web: retailer chỉ xác nhận, không tố cáo.

### Must / Should / Could
- **Must:** orders/receipts + diff · policy-v2 (R7w, R9w, R4w) + `POST/GET /cases/{id}/web-search` · marketplace scan + consensus.
- **Should:** `GET /sources/{sv}/image?as_role=` + OCR boxes trong evidence (dùng `ocr.boxes_for` của P2)
- **Could (stretch, chọn 1 nếu dư giờ):** (a) **scheduler theo priority**: `POST /internal/scheduler/tick` chọn case theo điểm = rủi ro (event mới, field CONFLICTING/INSUFFICIENT, tuổi kết quả) × độ "nóng" (lượt đọc passport); chạy nền, trace lý do chọn. (b) **reference store cấp product**: nguồn tham chiếu gắn với product (case_id NULL), extraction một lần cho mọi listing.

### Prompt chính P1-4 (effort: medium)
```text
You are P1, Phase 4 (T+4:15–5:15). Update .agent/plans/P1.md first.

GOAL
Buyer evidence receipts with tamper evidence, marketplace consensus over independent seller listings, and policy-v2 so
web pages found by P2's Web Scout can confirm but never accuse.

CONTEXT
- docs/06 rows R7w, R9w, R4w (web rules); docs/05 routes orders/marketplace/web-search; receipts carry the chain head;
  known risks: consensus ≠ compatibility, per-seller errors must stay per seller
- fixtures/marketplace/<PRODUCT_ID>/*.json (REAL retailer pages for the real product R1, or SYNTHETIC sellers —
  docs/DATASET-SPEC.md R5); README §7.1 web_sources.discover, ocr.boxes_for

BUILD
1. Orders: POST /orders {product_id} → store the buyer-visible passport JSON, its sha256, case_revision and chain head;
   GET /orders, GET /orders/{id} → receipt + per-field diff "then vs now" + changed_since_purchase flag; verify the stored
   hash on read.
2. Marketplace: POST /internal/marketplace/{pid}/scan (OPERATOR) ingests the seller listing files for that product
   OUTSIDE any case (never changes the passport), extracts them via extract.extract_source_version (one failing seller →
   trace marketplace:seller_skipped and continue), clusters copies (union-find on 5-char shingle Jaccard ≥ 0.8), groups
   values by EQUALITY (not compatibility), majority by independent clusters, flags only values incompatible with the
   majority as outliers → review tasks. GET /products/{pid}/marketplace: BUYER gets the tally by independent clusters, no
   shop names or quotes; REVIEWER gets shops, clusters, quotes (marked as seller text), outliers.
3. Web rules (POLICY_VERSION → "policy-v2", note in DECISIONS): kind WEB_PAGE; R7w a web page whose passages for the
   field are near-copies of another reference joins its family; R9w a WEB_PAGE disagreeing with the listing never makes a
   seller conflict → NEEDS_REVIEW if other independent sources still agree, else UNCERTAIN, never seller_attributable;
   between references a disagreeing retailer page is dropped with a note; R4w a WEB_PAGE stating several values for a
   field is not used for it (note only). Identity: a page P2 marks identity_verified=false may only confirm.
4. POST /cases/{id}/web-search (OPERATOR) admits WEB_SEARCH_REQUESTED (idempotency key = case + revision); the run calls
   web_sources.discover(ctx) before extraction when the event asks for it (and once per case for products with
   web.enabled while public fields are not consistent), then extracts the new sources. GET /cases/{id}/web-search
   (REVIEWER/OPERATOR) returns queries → results (domain, class, decision, reason) → snapshots (url, sha256, captured_at,
   passages) from the web_searches table P2 writes. Buyer reads never search.
5. SHOULD — Evidence route (if OCR is retained): include OCR boxes for image citations via ocr.boxes_for(sv_id, excerpt) and serve label images at
   GET /sources/{sv}/image?as_role= (role check from the query because <img> cannot send headers; PRIVATE images only
   for REVIEWER/OPERATOR).
6. Tests: test_orders (receipt diff after revoke; hash verification fails after tampering), test_marketplace (copies
   count once, incompatible outlier → review, buyer view has no shop names), test for R9w with a fake WEB_PAGE source
   (never seller-attributable), buyer GET never triggers web search.

CONSTRAINTS
- Marketplace findings never change the passport. Web pages are stored only as code-fetched, hashed snapshots
  (rule 2) — P2 does the fetching; you only apply policy and expose audit data.

DONE WHEN
`CONTEST_PHASE=4 pytest -q` green; sync_check.py 4 PASS; report per AGENTS.md §6 incl. POLICY_VERSION.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 5 — Hardening & freeze (T+5:15–6:00 · 15:15–16:00)

### Prompt chính P1-5 (effort: medium)
```text
You are P1, Phase 5 (feature freeze at T+6:00). No new features. (1) Run CONTEST_PHASE=4 pytest -q and
scripts/sync_check.py 1..4 in LLM_MODE=replay after P2's final record pass; fix root causes of any failure in your files
(CCR for others). (2) Time the full demo story in replay and report the slowest steps. (3) Sync docs 03 (as built
module map), 04, 05, 06 with the code — add/refresh an "As built (contest)" subsection in each with every table,
column, route, enum value and rule that exists in code but not in the doc (remove nothing); confirm POLICY_VERSION
matches the rules and every bump is in DECISIONS.md.
(4) Ensure every route has a response_model and the OpenAPI schema loads. (5) If frontend/dist exists, mount it as a
static fallback at "/" (CCR to P4 if main.py must change). Report per AGENTS.md §6 with the remaining known issues.
DONE WHEN: CONTEST_PHASE=4 pytest -q and sync_check.py 1–4 green in replay; docs "As built (contest)" committed.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Prompt phụ P1-5b — scorecard (effort: medium, thread 2 · sau tag `rec-freeze`)
```text
P1, Phase 5b. You own scripts/metrics.py and the route that serves its output. Build the scorecard beyond accuracy
(docs/09 "Scorecard beyond accuracy"): runs in-process on a temp DB in LLM_MODE=replay (fallback if recordings are
missing, labelled), replays the demo story, compares with fixtures/gold/dev (scripts may read gold; app code may not) and
writes docs/results/metrics.md + docs/results/metrics.json: decision quality (accuracy, macro-F1, conflict
precision/recall, seller false-blame rate, abstention, selective accuracy vs coverage), citation validity by code (quote
⊆ passage, locator exists), freshness (event → STALE, event → re-assessed, from timestamps), efficiency (model calls
live/replayed/avoided by cache/NOOP/DUPLICATE, tokens, cost by step with prices from backend/app/data/model_prices.json),
and the metamorphic results of P2's tests (do not generate variants here — P2-1b owns them). Header states
mode, models, prompt/policy versions, gold status, date. Add GET /internal/eval/metrics (OPERATOR/REVIEWER) returning the
JSON, or {"available": false} when the file does not exist. Test: route works with and without the file.
DONE WHEN: metrics.md + metrics.json written from the frozen recordings; the route test is green.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

## Phase 6 — Write-up + trực lỗi (T+6:00–7:00)

- Viết đoạn "Architecture & policy" (≤150 chữ) cho write-up: event → run → policy/publish gate, staleness theo dependency, revision guard, chain. Gửi P4 trước **16:20**.
- Chạy thử README trên máy sạch hoặc venv mới: tạo `.env` từ `.env.example`, `LLM_MODE=replay`, mở app.
- Chỉ sửa blocker khi P4 đồng ý: commit trên branch `p1`, push, P4 merge bằng `$sync-gate 6`.

### Prompt chính P1-6 (effort: medium)
```text
You are P1, Phase 6 (T+6:00–7:00). Code is frozen: change code only for a blocker the human approves, on your lane
branch, which P4 merges with $sync-gate 6. (1) Draft the "Architecture & policy" paragraph for the write-up (≤ 150 words, plain English, no forbidden
words): event → admission (idempotency, material filter, dependency staleness) → run (pinned revision, one budget) →
versioned policy and the publish gate (citations checked by code) → result chain and reviews bound to one revision.
Every claim must point to a file or test that proves it (list them under the paragraph). (2) Follow README.md "how to
run" on a fresh venv in a temp folder with LLM_MODE=replay and report each step that fails, with the fix. Send both to
P4 before 16:20.
DONE WHEN: paragraph (≤ 150 words) with its proof list delivered; README run steps verified or fixes reported.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

## Stretch backlog (theo thứ tự giá trị)
1. Scheduler theo priority (tăng điểm cho direction Autonomous).
2. Time travel `GET /products/{id}/passport?as_of=` (freshness tính lại từ `stale_at`).
3. Reference store cấp product: giảm số model call cho mỗi listing.
4. Revoke đối chiếu thêm với registry.
5. Diff view cho passport trước/sau một event.

## Q&A prep (P1 trả lời)
- *Vì sao code quyết định chứ không phải model?* → Policy có version, mỗi rule có test, explain trail, publish gate. Model chỉ đề xuất.
- *Scale lên hàng triệu listing?* → Event-driven, chỉ stale field phụ thuộc, extraction cache theo source version, reference store cấp product, scheduler theo priority. Buyer đọc không bao giờ kích hoạt tính toán.
- *Brand page sai thì sao?* → Self-conflict check chạy trước so sánh listing, không đổ lỗi seller, reviewer xem.
- *Reviewer duyệt bản cũ?* → Gắn `(result_id, case_revision)`, trả 409, revision mới thì review cũ thành SUPERSEDED.
- *Có sửa được lịch sử không?* → Hash chain gồm cả explain, blame và review_state. Đây là tamper-evident, không phải tamper-proof.
