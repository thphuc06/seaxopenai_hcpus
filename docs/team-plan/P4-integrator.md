# P4 — Integrator: skeleton, contract, test nghiệm thu, eval, merge, video, nộp bài

> P4 giữ nhịp cho cả đội. Ở Phase 0, P4 dựng xương và đóng băng hợp đồng để ba lane kia code song song mà không đụng nhau. Từ Phase 1, P4 viết trước test nghiệm thu làm "đích" cho mọi người, merge ở mỗi Sync, đo kết quả (eval/blind/metrics), gom bằng chứng Codex leverage, làm video và nộp bài.
> Người nên đảm nhận: người nắm toàn bộ spec và các rủi ro đã dự kiến.

## 0. Bạn sở hữu gì, phụ thuộc ai

- **Sở hữu:**
  - Gốc repo: `AGENTS.md`, `.agent/PLANS.md`, `.agent/plans/P4.md`, `.gitignore`, `.worktreeinclude`, `.codex/**` (cấu hình local environment của app), `README.md`. `scripts/dev/**`.
  - Backend shared: `backend/{requirements.txt,requirements-dev.txt,.env.example,pytest.ini}`, `backend/app/{config,models,main}.py`, `backend/app/pipeline/baseline.py`, `backend/tests/{conftest.py,PHASE,test_acceptance.py,test_guards.py}`.
  - `fixtures/**`.
  - Scripts: `scripts/{seed,demo_reset,check_fixtures,sync_check,eval,blind_eval,codex_stats}.py`, `scripts/demo/**` trừ `record_demo.py`. (Đã chia lại: `scripts/metrics.py` thuộc P1, `scripts/e2e.py` và `scripts/demo/record_demo.py` thuộc P3. P4 chỉ chạy các script này.)
  - `docs/**` (gồm `docs/tracking/*` mới cho ngày thi), trừ mục "As built (contest)" của docs 03–06 (P1) và docs 07 (P2).
  - Branch `main`, các tag `sync-N`, GitHub repo, gói nộp bài.
- **Cung cấp cho mọi lane:** contract trong `models.py` và `config.py`, stub interface (README §7.1), cơ chế `CONTEST_PHASE`, test nghiệm thu, các tag Sync.
- **Phụ thuộc:**
  - P1: `seed.load_product_dir()`, các route REST.
  - P2: `llm.client.parse` (cho B1 và judge), `scripts/record_all.py`.
  - P3: các `data-testid` (README §7.4) cho E2E và video.

## 1. Nhịp mỗi phase của P4

1. Đầu phase: `git fetch --tags; git merge sync-<N-1>` trên branch `p4` (Phase 0: làm thẳng trên `main`, tạo `p4` sau S0), rồi `$phase-kickoff P4 <N>`. Phase 0 thì dán thẳng Prompt chính.
2. Trong phase: thread 1 chạy Prompt chính, thread 2 chạy Prompt phụ (chủ yếu là dataset).
3. **T+20 (Phase 1–4): mini-sync hợp đồng** bằng `$sync-gate <N> contract`. Merge riêng commit contract của P4 (Phase 1: test nghiệm thu phase 1), P1, P2 và lane nào trễ Sync trước; mỗi commit đều có test trước khi commit merge. Tag `contract-<N>`, báo mọi lane `git merge contract-<N>`.
4. **Gold do Codex soạn, người duyệt theo lô**, làm trong lúc các thread code đang chạy:
   - Phase 2: Codex soạn `fixtures/gold/dev/real.json` sau P4-2b và bảng blind `fixtures/gold/blind/expected-set1.json`;
   - Mỗi nhãn kèm locator/bằng chứng và lý do ngắn; P4 hoặc một người được giao đọc, chỉnh và duyệt cả lô;
   - Phase 2–3: duyệt `demo-story.json`, real và blind; P3 có thể soát chéo nếu còn thời gian, không bắt buộc hai người.
   Chưa duyệt vẫn chạy diagnostic với nhãn DRAFT, báo số riêng. Blind phải cố định trước lần chạy đầu; không lấy
   output của pipeline làm đáp án. Duyệt không cần viết tay lại toàn bộ gold.
5. T−10: `$sync-gate <N>` ở thread Local (N≥1: commit và push `p4` trước; S0 làm trên `main`). Lấy baseline mới trước từng merge; gate đạt thì ghi HANDOFF và commit cùng `PHASE=N`, rồi mới tag/push. Lỗi chưa giải thích chặn tag; WAITING phải có missing lane/commit và chỉ được gọi partial. `/review`, click path và log làm sau tag.
6. Gọi cắt scope theo README §8 nếu cần. Thông báo "merge sync-N vào branch của bạn".

**Skill Codex dùng trong lane này** (cài ở `~/.agents/skills`, gõ trong ô chat của Codex):

| Khi nào | Gõ | Kết quả |
|---|---|---|
| Đầu mỗi phase | `$phase-kickoff P4 <N>` | Codex đọc section phase, cập nhật ExecPlan, hỏi nếu dính trigger, rồi chạy Prompt chính |
| Test đỏ hoặc verdict sai | `$trace-debug <tên test hoặc field>` | Tìm bước đầu tiên đi sai trong trace, viết test tái hiện, sửa đúng gốc lỗi (file của lane khác thì gửi CCR), ghi "Notable loop" vào CODEX_LOG |
| Xong sớm, bị kẹt, phải chọn cắt gì | `$brainstorm <options / cut / qa> <bối cảnh>` | Phương án xếp hạng kèm prompt dán được ngay, không viết code |
| T−20 mỗi phase | `$self-review` | Chạy test và build, quét hardcode, từ cấm, gold, secret, kiểm lane, contract, ExecPlan → `READY TO PUSH` hoặc `BLOCKED` |
| T+20 (Phase 1–4) | `$sync-gate <N> contract` | Mini-sync: merge riêng commit hợp đồng của P1 và P2, tag `contract-<N>` để P3 code trên type thật |
| T−10 mỗi phase | `$sync-gate <N>` | Local: baseline trước từng merge, gate test/build, HANDOFF cùng checkpoint trước tag `sync-N`. S0 bỏ merge P4, luôn test phase 0. Sau tag mới `/review`, click path và operational log |
| Phase 3 → 6 | `$mvp-demo` | Storyboard, callout và timing (Phase 3–4, P4); mặc định không giọng/TTS. P3 quay segment (Phase 5), P4 ghép và kiểm (Phase 6). Chỉ thêm giọng khi người dùng yêu cầu |
| Sau 16:45, chuẩn bị pitch | `$brainstorm qa` | Câu hỏi giám khảo có thể hỏi, kèm câu trả lời trỏ tới bằng chứng trong repo |

---

## Phase −1 — Trước ngày thi (29–30/10)

### Mục tiêu
Đến sáng 31/10 mọi người đã có tài khoản, tài liệu và skill; repo đã có commit init, và đã chỉ định người soát gold trong ngày thi.

### Việc cần làm
1. **Đọc README §14 checklist** và giao việc cho từng người.
2. **Dataset:** không mang dataset vào ngày thi. Fixture và gold DRAFT được Codex soạn từ `docs/DATASET-SPEC.md`, case thật capture ngày thi; một người duyệt gold theo lô (P4-0c, P4-1c, P4-2b, P4-3). Trước 31/10 chỉ cần: (a) đọc lại §3–§5 và chọn case; (b) mở thử URL thật, ghi URL còn sống; (c) giao người soát gold, có thể là P4, không cần một vai trò manual riêng.
3. **Repo public hay private:** case thật lưu text trang bên thứ ba. Nếu thể lệ buộc public, quyết định trước là commit đủ snapshot hay chỉ URL + hash + excerpt (PROPOSAL OQ-8).
4. **Pack đã import vào root repo:** tài liệu, prompt, AGENTS và đủ 6 skill/demo kit nằm trong `_outside-repo/skills`.
   Skill/demo kit là công cụ setup chuẩn bị trước, không phải application implementation; chưa có dataset hay recordings.
5. **GitHub đã khởi tạo:** `https://github.com/thphuc06/seaxopenai_hcpus.git` có một commit init prepared materials.
   Mời 3 người còn lại và kiểm tra quyền truy cập; không tạo repo/copy pack/commit init lại vào ngày thi.
6. **Pitch facts:** kiểm lại `docs/pitch/fact-check.md` (điền URL và ngày cho từng số).
7. Thử `/skills` trên máy mình. Đọc lại hết 3 file lane còn lại để biết ai cần gì ở Sync nào.

---

## Phase 0 — Nền móng & hợp đồng (T+0:00–0:30 · 10:00–10:30)

### Mục tiêu
Repo, AGENTS, docs, prompt và skill đã có trong commit init. Trong 15 phút đầu ngày thi, P4 dựng skeleton backend,
**contract đã đóng băng** và stub interface. Đến S0: pytest collect được, backend boot, seed chạy (P1), smoke đã có kết quả (P2), frontend boot (P3).

### Must / Should / Could
- **Must:** xác nhận commit init prepared materials đã có (không tạo lại) · skeleton + `config.py` + `models.py` + `main.py` + stub + `pytest.ini` + `conftest.py` + `PHASE` + `test_guards.py` · `.env.example` đầy đủ · `docs/tracking/*` mới · `.agent/plans/P4.md` · `.worktreeinclude` + setup script + Actions cho Codex app (README §4).
- **Should:** CODEX_LOG ghi task đầu tiên. (`check_fixtures.py` nằm trong P4-0c.)
- **Could:** GitHub Actions chạy pytest (chỉ khi còn dư 5 phút).

### Kiểm tra checkout có sẵn (10:00–10:05; đã bỏ bước khởi tạo repo)

Chỉ clone nếu máy chưa có checkout; nếu đã có thì vào checkout đó:
```powershell
git clone https://github.com/thphuc06/seaxopenai_hcpus.git
cd seaxopenai_hcpus
git status --short
git log --max-parents=0 --oneline
```
Không `git init`, copy pack hay commit prepared materials lại. P4 bắt đầu trực tiếp Prompt P4-0 trên `main` khi giờ thi bắt đầu.

**Mỗi người, ngay sau khi clone** (P1–P3 tạo branch của mình; P4 làm Phase 0 thẳng trên `main` và tạo `p4` sau S0). Venv này chỉ để làm việc được từ 10:05; sau S0 chạy `scripts\dev\setup_worktree.ps1` để cài đúng `backend/requirements.txt` của ngày thi:
```powershell
git switch -c p2; git push -u origin p2                     # thay p2 bằng lane của bạn (P1–P3)
py -3 -m venv backend\.venv                                 # Python >= 3.11
backend\.venv\Scripts\python -m pip install openai openai-agents fastapi uvicorn pydantic python-dotenv httpx pytest pillow   # mạng yếu: thêm --find-links <thư mục wheels>
Set-Content backend\.env "OPENAI_API_KEY=<key của bạn>"      # gitignored
```

### Prompt chính P4-0 (effort: medium) — 10:05–10:20
```text
You are the P4 (Integrator) Codex agent for Product Truth Passport, Phase 0 (T+0:05–0:20). AGENTS.md is loaded.
This repo already has its pre-event init commit: specs, team prompts and the prepared skills/demo kit under
_outside-repo/skills. No application implementation or dataset exists yet (fixtures and app data files are generated
today from docs/DATASET-SPEC.md). Do not repeat repository creation/import/init; keep the prepared tooling intact. Three teammates
(P1 backend core, P2 AI, P3 frontend) are waiting for the skeleton you create now, so speed and exact contracts matter
more than completeness. Create `.agent/plans/P4.md` from `.agent/PLANS.md` first (Phase 0 milestone), keep it updated.

GOAL
A runnable backend skeleton whose shared contracts are frozen and whose cross-lane interfaces exist as typed stubs, so
P1/P2/P3 can build in parallel without editing each other's files.

CONTEXT (read in one batch)
- docs/team-plan/README.md §5 (file ownership), §7 (contracts: Python interfaces, REST, trace steps, env vars)
- docs/04-data-model.md (enums, tables), docs/05-contracts.md (event envelope, passport response, extraction schema)
- docs/07-ai-integration.md §0 and §4 (env, modes), docs/team-plan/AGENTS.contest.md is AGENTS.md
- docs/DATASET-SPEC.md (fixtures and data files are generated on the day — nothing is pre-filled)
- Build from the specs; do not reuse code from memory of another codebase.

BUILD
1. Layout: backend/app/{__init__,config,models,main,context,budget,worker,chain}.py and packages
   backend/app/{events,api,pipeline,agent,retrieval,llm,connectors}/ (each with __init__.py). backend/tests/ WITHOUT
   __init__.py. Do NOT create db.py, seed.py, store.py or trace.py — P1 writes them from 10:05 on its own branch.
   frontend/ is P3's (do not create files there).
2. backend/requirements.txt pinned (start from docs-referenced pins: openai, openai-agents, fastapi, uvicorn, pydantic,
   python-dotenv, httpx, pytest, rapidocr-onnxruntime, pillow). Verify each pin exists for
   this Python with `pip index versions <pkg>` or `pip install --dry-run`; if a pin is missing pick the nearest release
   and note it. backend/requirements-dev.txt: pinned playwright and imageio-ffmpeg for E2E/video. No edge-tts by
   default; voice is optional only when the user asks. The personal video venv may use the skill's requirements.txt.
   Create the venv and install.
3. backend/app/config.py: a Settings dataclass loaded from backend/.env with EVERY switch in README §7.5 (typed,
   defaults as listed, LLM_MODE validated against fallback|replay|record|live), `reload_settings()` for tests,
   settings.replay_dir from REPLAY_DIR (default ../fixtures/replay), and model prices read from
   backend/app/data/model_prices.json when that file exists (P2 creates it at Phase 0 — do not create it; until then
   cost estimates show "price unknown"). backend/.env.example lists every switch with a one-line comment; .env is
   git-ignored.
4. backend/app/models.py: all enums from docs/04 (Verdict, ConflictLocus, ScopeMatch incl. passage scope AGENT,
   Freshness, Readability, ReviewState, EvidenceLevel, SourceKind incl. REGISTRY_RECORD and WEB_PAGE, SourceStatus,
   RunStatus, Role, EventType incl. WEB_SEARCH_REQUESTED, EventOutcome), PUBLIC_FIELDS, EventEnvelope, AdmitResult,
   strict ExtractedClaim/ClaimExtraction (docs/05 §3), Citation, PassportField, ClaimFinding, PassportResponse,
   and the shared policy output models from README §7.1: RuleStep(rule, outcome, detail), DependsOn(source_id,
   source_version_id), Gap(field_key, missing_kind, needed_doc, known_ids, reason), FieldDecision(...exact fields...).
   Strict-schema rules: every field required, nullable as `X | None`, no dict[str, Any] in models sent to the API.
5. Stubs with the exact signatures of README §7.1, each with a docstring naming its owner lane and the Sync when it must
   be real — EXCEPT backend/app/llm/client.py and backend/app/llm/messages.py: P2 is writing those right now on its own
   branch; create only backend/app/llm/__init__.py (empty) so the merge does not conflict. Stubs must be importable and safe: extract → returns an empty Extraction; scope resolution → no-op outcome;
   claims audit → []; retrieval.search → empty result with stages={"bm25": []}; web discover → no-op; ocr → []; Budget →
   a minimal working class (counts and raises BudgetExceeded). No stubs for P1's Phase 0 files (db, seed, store, trace).
   context.py: RunContext dataclass exactly as README §7.1.
6. backend/app/main.py: `create_app()` (FastAPI, all routers mounted under /api, routers imported from
   app/api/{passport,events,runs,cases,observe,orders}.py which you create as empty APIRouter modules owned by P1),
   startup hook that calls db.init_db() and seed.seed_if_empty() when app.db and app.seed are importable — P1 creates
   them in Phase 0 and they merge at S0; until then the hook logs "storage not merged yet" (remove this guard at S1),
   CORS for http://localhost:5173, `GET /api/health` returning LLM_MODE, models, policy version, phase and DEMO_RUN_DELAY_S (E2E and the
   video script check them).
7. backend/pytest.ini (`pythonpath = .`, markers: `phase(n)`), backend/tests/PHASE containing `0`, conftest.py:
   env defaults (LLM_MODE=fallback, WORKER_INLINE=1, OCR_ENABLED=0), a `client` fixture (temp DB via DB_PATH,
   reload_settings, TestClient(create_app()), seed reset), helpers fire(name), passport(product_id, role), fields(p),
   counts() over events/runs/trace_steps/field_results/gaps/claims, header dicts per role, and a collection hook that
   skips tests marked phase(n) when n > int(os.getenv("CONTEST_PHASE") or tests/PHASE).
8. backend/tests/test_guards.py (phase 0): (a) nothing under backend/app imports or opens fixtures/gold (grep the source
   tree, excluding this test); (b) forbidden wording regex from docs/06 (EN + VI, case-insensitive, word-bounded) absent
   from backend/app and frontend/src string literals (skip frontend if absent; ignore the regex definition itself);
   (c) no fixture ids or brand names in app code (backend/app and frontend/src, excluding frontend/src/mock): collect
   product_id, case_id, source_id and the passage ids that contain a digit and have 6+ characters (so a plain word such
   as "ingredients" is never treated as an id) plus brand names from fixtures/**/*.json at test time
   — never hardcode a prefix list, the ids are generated today (the set grows as fixtures land); (d) backend/.env is not
   tracked by git, and no tracked file contains an OpenAI-key-shaped string (`sk-` followed by 16+ key characters).
9. docs/tracking/: fresh HANDOFF.md (one `## sync-<N>` section per Sync, committed by $sync-gate before its tag;
   every lane's kickoff reads that tagged section), DEVLOG.md, CODEX_LOG.md (table: time | lane | task | files | accepted/edited/rejected | human change | test, plus a
   "Notable loops" section),
   ISSUES.md, PROGRESS.md (milestones S0..S4, Freeze, Submitted with planned clock times from README §3). DECISIONS.md
   (one short ADR per contract or rule decision made today).
10. .gitignore already exists (from the pack): extend it only if you add new generated folders; keep backend/.env ignored.
11. Second-thread worktrees (Codex app; read https://learn.chatgpt.com/docs/environments/git-worktrees and
    .../local-environment first): `.worktreeinclude` at the repo root listing `backend/.env` (gitignore-style patterns;
    ignored files only, never tracked ones), and `scripts/dev/setup_worktree.ps1` — Windows PowerShell 5.1 compatible,
    idempotent: create backend/.venv with `py -3 -m venv` (Python ≥ 3.11; fallback `python -m venv`) if missing; pip install
    backend/requirements.txt and requirements-dev.txt (add `--find-links $env:WHEELS_DIR` when that variable is set);
    `npm ci --prefer-offline` in frontend/ only if frontend/package-lock.json exists; print each step. Then give me the
    exact text to paste in the app Settings → Local environments: the Windows setup script
    (`powershell -ExecutionPolicy Bypass -File scripts\dev\setup_worktree.ps1`) and four Actions — backend (uvicorn on
    :8000 from backend/), frontend (npm run dev), tests (pytest with CONTEST_PHASE), sync_check (scripts/sync_check.py).
    The app stores them under `.codex/`; I save them and you commit that folder.

CONSTRAINTS
- Only create files you own (README §5) plus the empty stubs listed above for other lanes; stubs contain no logic beyond
  the safe defaults, so the owners can overwrite them freely.
- Names, enums and fields exactly as docs/04 and docs/05; if the docs disagree with README §7, README §7 wins for
  signatures and docs win for enum values — note any conflict in the Decision Log.
- Windows: utf-8 everywhere; no heredoc edits.
- Order: commit and push items 1–7 (skeleton, config, models, stubs, main, pytest setup) on main by about 10:20 —
  the whole team waits on them. Items 8–11 (test_guards, tracking docs, worktree support) follow in a second commit.

DONE WHEN
- `cd backend; .venv/Scripts/python -m pytest -q` → collection works, test_guards passes (phase 0).
- TestClient(create_app()) GET /api/health answers in a test; I confirm uvicorn boots with the app Action `backend`
  (do not start servers yourself — sandboxed child processes stop when the command ends).
- `python -c "from app import models, config, context, budget; from app.pipeline import extract, policy"` succeeds.
- Committed **on main** and pushed (`git push origin main`) by about 10:20 as "S0 P4: skeleton, frozen contracts, stubs
  (codex)" — P1–P3 merge origin/main from there. Report per AGENTS.md §6.

IF UNSURE
- Library versions/APIs: check pypi and the official docs before pinning or using them.
- Ask me only if a contract in README §7 is internally contradictory or a fixture needed for seeding contains TODO.
```

### Prompt phụ P4-0c — check_fixtures + dataset đầu tiên (effort: medium, thread 2 · từ đầu Phase 0, song song với P4-0)
```text
P4, Phase 0c (thread 2, 10:05–10:28). First write scripts/check_fixtures.py: walk fixtures/{synthetic,real,blind,marketplace} (whatever exists — the
dataset is generated during the day) and validate every snapshot JSON against the format in docs/DATASET-SPEC.md §2
(required keys, kind in SourceKind, dataset_origin REAL|SYNTHETIC,
unique passage ids per file and per product, non-empty text except an intentionally unreadable PACKAGING_IMAGE with
an actual sibling PNG and explanatory fixture note (DATASET-SPEC §2), no uppercase "TODO" anywhere (case-sensitive: keys such
   as "image_todo" are fine), product.json present with product_id,
variant, market, case_id), every event in fixtures/events against EventEnvelope (models.py), and every
payload.snapshot path exists. Print a table (path, problems) and exit 1 on problems. Use utf-8. Add a phase(0) test that
runs it in-process on the fixtures folder. Do not modify fixtures; report problems to me instead.
Then the dataset. No dataset was brought to the event: fixtures are generated today from docs/DATASET-SPEC.md. Read §1
(rules), §2 (formats), §4 row S1 and the event list, §7. Generate ONLY what S0/S1 need:
fixtures/synthetic/<s1-folder>/product.json + listing.v1.json + packaging_label.v1.json (transcript only; the PNG comes
at Phase 1) + notification_doc.v1.json + brand page for another market; fixtures/events/01-bootstrap-demo.json,
02-price-change.json, 03-duplicate-price-change.json (same idempotency key as 02), 08-rejected-producer.json, each with
an "expect" sentence. Plant exactly the facts in the S1 row; write fresh, natural Vietnamese wording (one English page
for the other market); fictional brand only; dataset_origin SYNTHETIC; stable ids from the spec. Then write
fixtures/gold/dev/demo-story.json with the expected verdicts after 01 as a DRAFT for me to check (status DRAFT,
labelled_by: "draft:codex", short evidence locator and rationale) — only human approval marks it REVIEWED. Run scripts/check_fixtures.py and report. (This thread runs in
a fresh worktree before the setup script exists: once P4-0 has committed models.py and the setup script on main, `git merge main`,
run scripts/dev/setup_worktree.ps1, then run the check. Until then write files only.)
DONE WHEN: check_fixtures.py exits 0 on the S1 product and events 01–03/08; its phase(0) test is green. This worktree
is on branch p4-b0 (Create branch here); I merge it into main from the Local checkout (`git merge p4-b0`) and push
before 10:25, so P1's seed.reset() can load S1 at S0.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Done-check S0
```powershell
cd backend; .venv/Scripts/python -m pytest -q; .venv/Scripts/python ..\scripts\check_fixtures.py
```
S0 cần đủ: P1 có `seed.reset()` nạp được sản phẩm S1 (sản phẩm duy nhất có ở S0) và event 01–03/08 · P2 đã post bảng smoke và `.env` đề xuất, đã tạo `model_prices.json` · P3 đã chạy `npm run dev` với mock.

### Bàn giao ở Sync 0
- Chạy `$sync-gate 0` trên `main`: gate phase 0 + HANDOFF đạt thì mới tag `sync-0`. Gửi team:
  - model IDs và effort đã chốt từ smoke;
  - **con số budget** (`RUN_MAX_MODEL_CALLS`, `RUN_DEADLINE_S`) tính từ latency đo được;
  - link README §7.
- `PHASE` giữ 0 (quy ước: sau Sync N, `PHASE` = N).
- Skill đã tạo/push `p4` một lần sau tag và handoff. Nếu làm Sync bằng tay, chỉ chạy `git switch -c p4; git push -u origin p4` khi nhánh chưa tồn tại; nếu đã có thì switch sang `p4` và merge `sync-0`, không tạo lại.

### Rủi ro dự kiến (phòng hờ)
- `tests/__init__.py` gây lỗi import.
- Test grep chữ "gold" fail vì docstring nhắc tới từ đó. Chỉ grep import/path, không grep chữ tự do.
- `.env.example` thiếu switch.

---

## Phase 1 — Xương sống (T+0:30–1:45 · 10:30–11:45)

### Mục tiêu
Viết sẵn **toàn bộ** test nghiệm thu (AC-01…AC-20 trong docs/09, cộng các test glass box/receipt/web), gắn phase marker, để mọi lane có đích rõ. Có `scripts/sync_check.py` cho click path. Merge S1 = M1.

### Must / Should / Could
- **Must:**
  - `test_acceptance.py` có đủ AC, mỗi AC gắn `phase(n)`;
  - `scripts/sync_check.py` cho phase 1–4;
  - `scripts/seed.py` + `scripts/demo_reset.py` (gọi API của P1);
  - S1 merge.
- **Should:** `docs/tracking/PROGRESS.md` cập nhật thời gian thật.
- Metamorphic test thuộc P2 (P2-1b), P4 không viết lại.

### Prompt chính P4-1 (effort: high)
```text
You are P4 (Integrator), Phase 1 (T+0:30–1:45). Update .agent/plans/P4.md (Phase 1 milestone) first.

GOAL
Turn docs/09-eval-plan.md into an executable acceptance suite that every lane builds against, gated by phase, plus a
phase click-path script. Tests are the contract for behaviour; they must be precise, deterministic (fallback mode,
inline worker, no network) and must not encode implementation details that the specs leave open.

CONTEXT
- docs/09-eval-plan.md (AC-01..AC-20), docs/05-contracts.md (routes, envelope), docs/06-policy-rules.md (rules,
  templates, review triggers), docs/04-data-model.md (buyer label mapping)
- docs/DATASET-SPEC.md §4 (cases, events and what each must prove), fixtures/events/*.json (each has an "expect"
  note), fixtures/synthetic/*/product.json. Expected values in tests come from these specs — NOT from gold (gold is for
  eval.py and blind_eval.py only), so tests never inherit a DRAFT label
- docs/PROPOSAL.md §8 (AC-21…AC-41: names and expectations beyond docs/09)
- backend/tests/conftest.py (helpers), docs/team-plan/README.md §3 (which phase delivers what), §7.2 routes, §7.3 steps

BUILD
0. FIRST, before T+20: the phase(1) tests listed below, committed alone as "S1 P4: contract (phase-1 acceptance
   tests)" and pushed on p4 — they ship in contract-1, so P1/P2 build against them from about 10:50. Then the rest.
1. backend/tests/test_acceptance.py — one test per AC (AC-01…20 named as in docs/09; AC-21…41 named after
   docs/PROPOSAL.md §8), marked with the phase that delivers it AND with @pytest.mark.needs("P1", "P2", …) listing every
   lane whose code the test exercises (register both markers in pytest.ini; conftest derives the current lane from CONTEST_LANE,
   else from the git branch name (p<k> or p<k>-b<N>; on main or an unknown branch there is no WAITING) and, in the
   terminal summary, lists each failing test whose needs() names another lane as "WAITING on <lanes>" — it still
   counts as failed — so builders know it is not theirs to fix):
   phase(1): AC-05 demo bootstrap, AC-07 price NOOP (0 jobs, 0 model calls), AC-08 duplicate (no new rows anywhere),
             AC-10 wrong market excluded (scope reason recorded, not CONFLICTING), AC-13 buyer GET x5 creates nothing
             (compare counts()), AC-14 buyer cannot POST events (403), AC-16 old run cannot overwrite newer revision
             (SUPERSEDED_RUN in trace), AC-19 forbidden wording absent from every public_text after the whole story,
             AC-20 every non-INSUFFICIENT field cites one passage containing the contiguous excerpt (check via DB,
             NFC + whitespace collapse on both sides, case-sensitive, never join fragments), rejected producer → REJECTED.
             AC-01 Foaming (real R2): skip with reason until fixtures/real/ has it (captured at S2 by P4-2b).
   phase(2): AC-02/AC-03 within-source conflict on skin_type and key_ingredients, seller_attributable false,
             NEEDS_REVIEW (use the CeraVe hydrating fixture if present, else the synthetic Hydra product from
             11-bootstrap-hydra — same pattern; parametrize over whichever exist), AC-04 single source (CeraVe blemish
             if present; always also: DEMO skin_type SINGLE_SOURCE after bootstrap), AC-06 revoke → only notification
             fields STALE immediately with 0 model calls, then INSUFFICIENT + EvidenceRequest, volume keeps the same
             result_version, AC-09 volume change → CONFLICTING/LISTING_VS_SOURCE/NEEDS_REVIEW, AC-11 injection ignored
             (ignored_instructions_detected true in trace detail, verdicts unchanged), AC-12 isolated blurred-photo case
             without other readable support for the tested field → UNREADABLE → INSUFFICIENT + "clearer photo" request;
             also verify adding 10 to the full story preserves useful existing evidence, AC-15 review on stale revision → 409 and nothing written, override
             without citation → 422, AC-17 budget exhausted (set RUN_MAX_MODEL_CALLS / AGENT_MAX_TOOL_CALLS to 1 via env)
             → run PARTIAL with stop_reason, no fabricated verdict, AC-18 model failure (force a fake LLM error via a
             monkeypatched client) → run FAILED or PARTIAL and buyer label "Could not update" or prior result kept;
             evidence-added flow (06-evidence-added) → company back to CONSISTENT, number CONFLICTING, requests FULFILLED;
             claims audit on 13-bootstrap-clear-serum → claim findings exist, all NEEDS_REVIEW, buyer sees only a count;
             verify claim:* rows use P1's policy decisions and CL explain trail, never a verdict supplied by the model
             or independently assigned by the audit orchestrator.
             NOTE for AC-17/AC-18: fallback mode makes no model calls, so these two tests set LLM_MODE=record and
             monkeypatch P2's single network seam `app.llm.client._call_api` (a fake that returns a valid empty
             ClaimExtraction, or raises) — no network — with REPLAY_DIR pointed at tmp_path so tests never write recordings into
             fixtures/replay; AC-17 also covers RUN_DEADLINE_S=0 → no call made.
   phase(3): catalogue (09-catalogue-published) → skin_type changes through the size-less line the agent places with a
             code-verified anchor (AGENT_VERIFIED); size-less passages never MATCH without a verified anchor; gap controller (12-bootstrap-sun-fluid) → REGISTRY_RECORD
             source cited, gap stop_reason GAP_CLOSED; explain endpoint: buyer sees no private sources/model ids/rule codes,
             reviewer sees the full trail; chain endpoint valid after the story and invalid after tampering a hashed
             column directly in the DB.
             Exercise agent-dependent checks offline with record mode and a deterministic fake at P2's documented
             network seam, tmp_path recordings (as for AC-17/18). This proves orchestration/verification, not real model
             quality; actual recorded agent behaviour is checked separately in replay mode.
   phase(4): fresh isolated scenario: 01 bootstrap → order receipt → first processing of 05 revoke → receipt diff shows
             the two changed fields; never reuse the already-processed 05 from the phase-2 story to expect a change.
             Marketplace scan → copies count once,
             incompatible values routed to review, buyer response has no shop names; web search with a fake provider →
             snapshots are REAL with sha256, retailer disagreement never seller-attributable, buyer GET never searches.
   Assert on behaviour and contract fields only (verdict, locus, review_state, freshness, seller_attributable, outcome,
   status codes, counts) — not on exact public_text wording beyond forbidden words and "leads with the value" checks.
2. scripts/sync_check.py <phase> [--mode fallback|replay]: runs in-process (TestClient, temp DB, inline worker), replays the path of
   every phase ≤ <phase> (fires fixture events in order, reads passports as BUYER and REVIEWER) and prints a PASS/FAIL
   table with the observed verdicts per product/field; exit 1 on FAIL. Mode = explicit --mode, else LLM_MODE, else fallback
   when unset; print the resolved mode. Only fallback/replay are supported: reject other modes with an explanation to
   select one of these, before any work or network access. Neither supported mode calls the network. Existing freeze
   commands that set LLM_MODE=replay work without an extra flag. Implement phase 1 now; P4-2/3/4 extend it. The
   paths (expectations from DATASET-SPEC §4 and docs/06):
   - phase 1: reset → 01 → S1 passport (volume CONSISTENT, skin_type SINGLE_SOURCE, key_ingredients CONSISTENT,
     notification fields CONSISTENT, other-market page excluded) → 02 NOOP → 03 DUPLICATE → 08 REJECTED → passport x3
     (counts unchanged).
   - phase 2: + 05 (two notification fields STALE at once, 0 model calls; after the run INSUFFICIENT + 2 requests) → 06
     (company CONSISTENT, number CONFLICTING, requests FULFILLED) → 04 (volume CONFLICTING/LISTING_VS_SOURCE) → approve
     review (decision listed; a stale revision → 409) → 07 (volume back; injection flagged) → 10 (UNREADABLE → clearer-
     photo request, prior readable evidence retained) → 11 (Conflict in source on skin_type and key_ingredients) → 13 (claim findings; buyer count only).
   - phase 3 in fallback: + 09 (sized lines decided by deterministic pre-pass; size-less line remains unresolved,
     no invented agent effect) → 12 → explain as BUYER (no private source / model id / rule code) and as REVIEWER.
     Agent-dependent scope/GAP_CLOSED checks run in the separate offline fake-client tests above. In replay mode,
     require the actual recordings to show size-less placement with a verified anchor, skin_type change and agent:effect,
     plus the registry hop/GAP_CLOSED when demonstrated; a missing recording is REPLAY_MISS, not fallback or PASS.
   - phase 4: + 14–17 (real cases: R1 Conflict in source; R2 no false alarm; R3 number + company read; R4 claims without
     a false alarm, where the day's captured content supports these expectations; report changed pages and use
     source-grounded expected answers set before the run, never force historical verdicts) → in a fresh isolated DB:
     01 bootstrap → order receipt → first 05 → receipt diff on two fields.
     Marketplace scan and web-search checks use their own scenario state. Reposting processed 05 must still be DUPLICATE.
   A case whose fixtures do not exist (a real page that could not be captured) is printed as SKIP with the reason,
   never as PASS.
3. scripts/seed.py (reset + seed via app.seed) and scripts/demo_reset.py (POST /api/internal/demo/reset on a running
   server, with a clear error if the port is not answering).
4. Bump backend/tests/PHASE only at the Sync, not now.

CONSTRAINTS
- Use only public routes and the DB (read-only) for assertions; never import private helpers of other lanes.
- Expected values come from docs/06, docs/09, DATASET-SPEC §4 and the fixture "expect" notes — not from gold. Where
  they disagree, mark xfail(strict=False, reason=…) (allowed for P4 by AGENTS §4) and list it for me — never guess.
- Keep every test fast (< 2 s) and independent (fresh client fixture).

DONE WHEN
- `CONTEST_PHASE=1 pytest -q` runs phase ≤1 tests (they may fail until P1/P2 land — report which and why);
  `CONTEST_PHASE=4 pytest -q --co` collects the whole suite without import errors.
- sync_check.py 1 runs end-to-end against the merged S1 code (after merge).
- Report per AGENTS.md §6; list for each lane which of its tests are red now.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Prompt phụ P4-1c — các case synthetic còn lại + ảnh nhãn (effort: medium, thread 2 · từ đầu phase)
```text
P4, Phase 1c. From docs/DATASET-SPEC.md §4 generate the remaining synthetic cases and events: S1-v3 (volume edit),
S1-v4 (prompt injection inside one passage), S1-up (seller-uploaded notification doc 00077), S1-blur (unreadable seller
photo, empty transcript), S1-cat (catalogue with sized lines AND one size-less line under the 50 ml heading), S2
(brand page that contradicts itself), S3 (no notification doc; the label prints the number), S4 (claims vs INCI; listing
skin text copied from the brand page), the mock registry, and events 04–13 with "expect" sentences (payload.snapshot
paths relative to fixtures/). Plant exactly the facts in each row; fresh wording; fictional brand only. Write
scripts/make_label_images.py (Pillow, utf-8 Vietnamese text, readable at 1280×720; --blur for S1-blur) and render every
PACKAGING_IMAGE PNG next to its JSON. Extend fixtures/gold/dev/demo-story.json with a checkpoint after every event,
derived from the actual passages, "Proves" column and docs/06 — DRAFT with short evidence/rationale for batch review.
Distinguish the isolated unreadable-only AC-12 from event 10 in the full story: the latter adds an unreadable image,
not a revocation of previous readable evidence. Run check_fixtures.py. Do not touch app code.
DONE WHEN: check_fixtures.py exits 0; every event 04–13 exists with its snapshot; every label has a PNG.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Sync 1 — `$sync-gate 1` (thread Local, sau khi commit và push `p4`; không chạy ở thread 2)
```text
$sync-gate 1
```

### Done-check S1
`$env:CONTEST_PHASE=1; .venv/Scripts/python -m pytest -q` green · `.venv/Scripts/python ../scripts/sync_check.py 1` PASS · mở `http://localhost:5173`: bấm Operator "Bootstrap" thì Buyer thấy 5 field có citation (fallback), REPLAY/FALLBACK/SYNTHETIC badge đúng.

### Bàn giao ở Sync 1
`PHASE` = 1 (đã ghi trong `$sync-gate 1`). Gửi mỗi lane danh sách test phase 2 đang đỏ, đó là đích của Phase 2.

---

## Phase 2 — Mâu thuẫn nguồn + vòng đời + model thật (T+1:45–3:00 · 11:45–13:00)

### Mục tiêu
Có baseline để chứng minh "agentic RAG + policy có đáng không": `eval.py` so sánh B0 với candidate trên demo story. Chuẩn bị cảnh **Codex fix loop** từ một lỗi thật. Theo dõi chi phí.

### Must / Should / Could
- **Must:**
  - `backend/app/pipeline/baseline.py` (B0);
  - `scripts/eval.py` ghi ra `docs/results/eval-latest.md`;
  - S2 merge;
  - CODEX_LOG cập nhật.
- **Should:** chọn và ghi lại một fix loop thật (test đỏ → `$trace-debug` → sửa → xanh), lưu vào "Notable loops".
- **Gold (trong lúc code chạy):** Codex soạn `real.json` sau capture và bảng blind `expected-set1.json` (đa dạng case, khoảng 12 nếu kịp; ít hơn vẫn dùng được). Một người duyệt theo lô; chưa duyệt giữ DRAFT. Cố định blind trước lần chạy đầu, không chặn build vì chờ duyệt.

### Prompt chính P4-2 (effort: medium)
```text
You are P4, Phase 2 (T+1:45–3:00). Update .agent/plans/P4.md first.

GOAL
A reproducible evaluation that compares a naive baseline (B0) with the full pipeline (candidate) on the demo story, so
the team can show measured value, honestly labelled (draft vs human-reviewed gold).

CONTEXT
- docs/09-eval-plan.md "Baseline B0 vs candidate" and "Metrics to record per run"
- fixtures/gold/dev/demo-story.json (checkpoints after each event; check its status/labelled_by fields)
- routes: /api/internal/demo/fire, /api/products/{id}/passport, /api/internal/runs (usage)

BUILD
1. backend/app/pipeline/baseline.py — B0 as a pure function over stored claims: listing value vs brand-page value,
   normalised compare (reuse normalize/compare — do not reimplement), no self-conflict check, no scope check, no
   notification-document requirement, no agent. Returns per-field verdicts in the same enum.
2. scripts/eval.py — in-process (TestClient, temp DB), mode from LLM_MODE (default replay; falls back to fallback with a
   loud label if recordings are missing). Walk the gold checkpoints: fire each event, then compare candidate passport
   and B0 with the expected verdicts. Per checkpoint and in total: correct/total, seller wrongly blamed (CONFLICTING +
   seller_attributable where gold says not), abstentions (INSUFFICIENT/UNCERTAIN where gold expects them), model calls,
   tokens, latency (from run usage). Write docs/results/eval-latest.md (+ .json) with a header that states mode, model,
   prompt versions, policy version, gold status (DRAFT or reviewed by whom) and date. Separate DRAFT and REVIEWED
   counts and scores; never blend them into one reviewed score. DRAFT results are exploratory diagnostics.
3. A phase(2) test that runs eval in fallback on the first two checkpoints (smoke only, no numbers asserted).
4. Extend scripts/sync_check.py with the phase-2 path listed in P4-1.

CONSTRAINTS
- Gold is read only by scripts/ and tests/ (rule 11). Never "fix" a gold label to match output; disagreements go to a
  list in the report for a human.
- Do not add new model calls in eval beyond what the pipeline makes (B1 comes in Phase 3).

DONE WHEN
eval.py runs in fallback and in replay (if recordings exist), writes both files, and the report shows a per-checkpoint
table. Report per AGENTS.md §6, including the first numbers.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Prompt phụ P4-2b — capture sản phẩm thật (effort: medium, thread 2 · từ đầu phase)
```text
P4, Phase 2b. Real cases are captured today from public pages (docs/DATASET-SPEC.md §3). Write
scripts/capture_page.py <url> --product <product_id> --kind LISTING|BRAND_PAGE|WEB_PAGE [--family …]: httpx GET with a
timeout and a normal browser user-agent; HTML → text with the standard-library html.parser (drop script/style/nav,
menus, the section-end markers of DATASET-SPEC §6 and link cards; keep this cleaning in one function clean_html()
that P2's web_sources imports instead of writing a second one); split into passages with locators (title,
highlights#n, description#pN, usage, specs#…, ingredients); write a REAL snapshot (uri, captured_at now, family by
domain) under fixtures/real/<product-folder>/ and print the passages for review. A page that blocks fetching or returns
no product text is reported and skipped — never retype a page by hand as REAL. Then capture R1–R4 (listing = the
retailer page in the table; references = the official brand pages), write each product.json (web.enabled true with
brand_domains and aliases for R1), events 14–17. Draft fixtures/gold/dev/real.json from the captured text and policy,
with short evidence locators/rationale, labelled_by draft:codex, status DRAFT; never infer labels from candidate output.
Prepare a compact review table so one human can approve or adjust the batch. Also draft the blind case table in
fixtures/gold/blind/expected-set1.json from DATASET-SPEC §5 for Phase 3 (a smaller mixed set is fine if time is short).
Only human approval marks gold REVIEWED. Report what each page actually says today for the behaviours in §3.
DONE WHEN: each reachable R1–R4 page is stored as a REAL snapshot that passes check_fixtures.py; blocked pages listed;
real gold and the blind case table are drafted for batch review. Pending review does not block diagnostic evaluation.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Done-check S2
`CONTEST_PHASE=2 pytest -q` · `sync_check.py 2` gồm revoke ripple, Conflict in source, review 409 · có ít nhất 1 run `record` của P2 thành công, badge hiện đúng model.

---

## Phase 3 — Agentic + RAG + glass box (T+3:00–4:15 · 13:00–14:15)

### Mục tiêu
Đo khả năng thích ứng trên **sản phẩm chưa từng thấy** (blind sets) và so với **B1** (một lần gọi LLM với mọi nguồn). Bắt đầu làm video: storyboard, callout và timing; mặc định không giọng/TTS.

### Must / Should / Could
- **Must:** `scripts/blind_eval.py` · B1 trong `baseline.py` (record, có trần) · `scripts/demo/storyboard.md` + callout/timing, `narration.json = {}` (bước 1–3 của `$mvp-demo`) · S3 merge.
- **Should:** chạy blind set 1 ở fallback và replay, ghi `docs/results/blind-summary.md`.
- **Could:** judge citation (model khác family, offline, record).

### Prompt chính P4-3 (effort: high)
```text
You are P4, Phase 3 (T+3:00–4:15). Update .agent/plans/P4.md first.

GOAL
Prove adaptation, not memorisation: run the pipeline on products it was never tuned on (fixtures/blind/**) with the
answers fixed in advance (fixtures/gold/blind/*.json), and compare with a single-LLM baseline (B1).

CONTEXT
- docs/DATASET-SPEC.md §5 (blind-set process and probe categories), fixtures/gold/blind/expected-set1.json drafted
  by Codex in Phase 2, if present (retain its actual DRAFT/REVIEWED status)
- P1 exposes seed.load_product_dir(path) (generic loader) — if it does not exist yet, send a CCR to P1 instead of
  writing your own loader
- app/llm/client.parse (P2) for B1; docs/09 metrics; AGENTS rule 14 (test on unseen products)

BUILD
0. Blind set 1 (docs/DATASET-SPEC.md §5): if the case table is missing, draft it now with expected fields and short
   rationale from policy, without candidate outputs. Generate fixtures/blind/set1/<product>/ realising each row
   (aim for 12 mixed cases if time permits; a smaller set is fine, report the count; fresh wording, SYNTHETIC).
   Check passages against expected answers and run check_fixtures.py; report unrealizable rows. Freeze fixtures and
   labels before the first run. One human may approve the batch; pending review stays DRAFT and diagnostics can proceed.
1. scripts/blind_eval.py --set <n|all> [--mode fallback|replay|record] [--max-calls N]: temp DB per set, load each blind
   product via seed.load_product_dir, fire a BOOTSTRAP for its case, read the passport (and claim findings), compare with
   the expected file. Output docs/results/blind-set<n>.md: per product per field expected vs got, misses with the
   "probes" note, seller wrongly blamed count, abstention count, model calls/tokens, gold status and reviewer if any.
   Separate DRAFT/REVIEWED counts and scores. Preserve first-run results; append or separately save reruns instead of
   overwriting that initial result, including when a human corrects a label after the run. A summary
   docs/results/blind-summary.md across sets. Exit code 0 even with misses (it is a report), 1 on crashes.
2. B1 in backend/app/pipeline/baseline.py: one strict-schema call (via llm.client.parse, step "baseline:b1", its own
   prompt version) that receives all sources' passages and returns per-field verdicts (same enum). Recorded like any
   call; budget cap from --max-calls. eval.py gets a B1 column.
3. Video kick-off with the mvp-demo skill (installed at ~/.agents/skills/mvp-demo): follow its workflow steps 1–3 using
   its references/passport-storyboard.md as the starting point. Write scripts/demo/storyboard.md (short callouts,
   scene timings for a 3:00 limit with ~20 s reserve, what each scene shows) and scripts/demo/narration.json as {}.
   Default to no voice, no TTS and no music; add narration only when the user requests it later. The
   video is a demo of the running app and the system flow only — no pitch slides, market numbers, results or Codex
   slides (the team pitches live). Do not record yet.
4. Extend scripts/sync_check.py with the phase-3 path listed in P4-1.

CONSTRAINTS
- After the first run, do not tune blind fixtures or labels to output. A wrong-looking label goes to the human review
  list; a justified human correction preserves the original report and records who changed what and why.
  Disclose Codex-assisted gold.
- Record mode spends money: cap calls (default 60 for all sets) and print the estimated cost before running; ask me if
  the estimate is above $3.
- The demo kit is prepared setup tooling tracked under _outside-repo/skills/mvp-demo (declared separately from app code).
  scripts/demo/* written today may import it from that folder or a user-installed skill via DEMO_KIT_DIR.

DONE WHEN
blind_eval runs on set 1 in fallback with a report; eval.py shows B0 / B1 / candidate; storyboard drafted, narration.json={}.
Report per AGENTS.md §6 with the first blind numbers.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Done-check S3
`CONTEST_PHASE=3 pytest -q`: kiểm agent bằng fake client offline · `sync_check.py 3 --mode fallback`: kiểm pre-pass và explain theo role · `sync_check.py 3 --mode replay` (khi có recording): agent đổi verdict, `agent:effect` có before/after; thiếu recording báo chưa xác minh · bỏ `--mode` thì dùng `LLM_MODE`, mặc định fallback nếu chưa đặt · storyboard đã được cả đội xem 2 phút.

---

## Phase 4 — Khác biệt + nâng cấp (T+4:15–5:15 · 14:15–15:15)

### Mục tiêu
Storyboard, callout và timing chốt xong để P3 quay ở Phase 5; `narration.json={}` cho video không giọng. Blind set đã chạy; số liệu và bằng chứng Codex leverage gom về một chỗ; có marketplace thật R5. E2E (`scripts/e2e.py`) và quay segment (`record_demo.py`) thuộc P3, scorecard (`scripts/metrics.py`) thuộc P1. P4 chạy và dùng kết quả để ghép video và nộp bài.

### Must / Should / Could
- **Must:** chốt `scripts/demo/storyboard.md` + `narration.json` (thứ tự event, testid từng cảnh) cho P3 · chạy `blind_eval.py --set 1` ở fallback/replay · S4 merge.
- **Should:**
  - gom số liệu cho write-up: CODEX_LOG đếm theo lane/outcome, số thread, số lần dùng skill, finding của `/review`, fix loop;
  - kiểm tra `e2e.py` (P3) chạy được trên code đã merge. `metrics.py` (P1) tới Phase 5 mới có.
- **Could:** citation judge (recall/precision) bằng một model khác, offline.

### Prompt chính P4-4 (effort: high)
```text
You are P4, Phase 4 (T+4:15–5:15). Update .agent/plans/P4.md first.

GOAL
(1) A final silent-video storyboard P3 can record from in Phase 5 (event order, data-testids, callouts and scene timings);
(2) adaptation evidence from the blind set; (3) one place with the numbers and Codex-leverage evidence the write-up
needs. (E2E is P3's scripts/e2e.py — run it, do not rewrite it. P1's scripts/metrics.py arrives in Phase 5.)

CONTEXT
- docs/team-plan/README.md §7.4 (data-testids), §9 (direction → scene map), §10 (Codex leverage), scripts/demo/storyboard.md
- ~/.agents/skills/mvp-demo (SKILL.md, references/recording.md, scripts/demo_kit.py API: record_segment, Segment
  helpers, assemble, check_overlaps, contact_sheet); docs/tracking/CODEX_LOG.md, .agent/plans/*.md, git log

BUILD
1. Finalise scripts/demo/storyboard.md and scripts/demo/narration.json against the merged UI: for every scene the
   fixture events in order, the data-testids to click, short callouts and reading holds (3:00 limit with ~20 s reserve;
   no numbers or pitch slides). Keep narration.json={} and do not call TTS unless the user requests voice. P3 records
   the segments from this file (P3-5b); check each testid exists.
2. Run scripts/blind_eval.py --set 1 in fallback (and replay where recordings exist); refresh
   docs/results/blind-summary.md; list misses with their "probes" note — never edit expected labels.
3. scripts/codex_stats.py (yours): counts from docs/tracking/CODEX_LOG.md (tasks per lane, accepted/edited/rejected,
   notable loops), git log (commits per lane prefix "S<N> P<k>", first/last application-code commit time under backend/, frontend/ and scripts/; exclude the prepared _outside-repo tooling/init), .agent/plans (decisions,
   surprises count) → docs/results/codex-usage.md. This feeds SUBMISSION "How Codex was utilised".
4. Marketplace R5 (docs/DATASET-SPEC.md §3): capture 4–5 retailer pages of the R1 product with scripts/capture_page.py
   into fixtures/marketplace/<R1 product_id>/ (kind LISTING, REAL). Keep synthetic sellers only if fewer than 3 real
   pages can be fetched. Report the values each page states (size, skin type) before P1's scan runs.
5. Extend scripts/sync_check.py with the phase-4 path listed in P4-1.

CONSTRAINTS
- Video and blind runs use replay/fallback only; never live. Never edit an AI answer in the video; cut or fast-forward
  and disclose (mvp-demo principle).
- If a data-testid is missing, send a CCR to P3 with the exact element and id; do not select by text.

DONE WHEN
storyboard.md + narration.json final (every testid exists); blind-summary.md refreshed; codex-usage.md written; R5
pages captured; sync_check.py 4 runs; e2e.py (P3) status reported. Report per AGENTS.md §6.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 5 — Hardening & freeze (T+5:15–6:00 · 15:15–16:00)

### Mục tiêu
Đến 16:00 tất cả green ở replay, số liệu cuối đã đo, P3 đã quay xong các segment, README repo đã viết. **Đúng 16:00 đóng băng.**

### Việc (theo thứ tự)
1. **~15:15 (sau tag sync-4):** P2 `git merge sync-4` rồi chạy record pass (thứ tự: cảnh storyboard → event 01–17 → blind set). Trong lúc chờ, bạn chạy prompt README bên dưới.
2. **~15:35:** P2 gửi CCR cấu hình freeze; P4 cập nhật `config.py`/`.env.example` nếu cần. `$sync-gate 5 rec` → merge recordings (`p2`) và storyboard (`p4`), gate phase 4 + replay path đạt không có REPLAY_MISS/WAITING trong phạm vi bắt buộc → tag `rec-freeze`. P3 merge tag rồi quay với `LLM_MODE=replay DEMO_RUN_DELAY_S=3 OCR_ENABLED=1`.
3. Sau `rec-freeze`, ở thread Local:
   ```powershell
   cd backend; $env:LLM_MODE="replay"; .venv/Scripts/python -m pytest -q
   .venv/Scripts/python ../scripts/eval.py; .venv/Scripts/python ../scripts/blind_eval.py --set 1 --mode replay; .venv/Scripts/python ../scripts/metrics.py
   ```
   `e2e.py` do P3 chạy, vì cần server bật bằng Actions.
4. **15:50:** `$sync-gate 5` → full gate phase 5 ở replay đạt, không WAITING, HANDOFF đã nằm trong checkpoint → tag `sync-5` và `freeze`; gate lỗi thì báo BLOCKED, không gắn tag xanh giả. 16:00 đóng băng scope; sau đó chỉ sửa blocker qua `$sync-gate 6`.
5. README repo: dùng prompt dưới đây.

### Prompt chính P4-5 (effort: medium)
```text
You are P4, Phase 5 (T+5:15–6:00), feature freeze at T+6:00. Update .agent/plans/P4.md first.
Write the repository README.md for judges: one-paragraph problem and solution; what is new (field-level evidence,
source self-conflict, event-driven staleness, code-verified agent, learned vocabulary); the two build directions with
the evidence links (docs/results/*); architecture diagram (mermaid from docs/03 updated to the contest build); how to run
(backend venv + .env.example + uvicorn, frontend npm ci + npm run dev, LLM_MODE=replay works without a key, tests);
results table with measured numbers from docs/results (state mode, date, gold status); honest limits (synthetic data
labelled, mock registry, draft gold if not reviewed, small sets); how Codex was used (link to docs/tracking/CODEX_LOG.md
and .agent/plans/); declaration link. No claims of authenticity/safety (rule 1). Keep it under 200 lines.
Then fill docs/tracking/PROGRESS.md with actual times. (docs/03–06 "As built" belong to P1, docs/07 to P2.)
DONE WHEN: README.md committed (< 200 lines, every number linked to docs/results/*); PROGRESS.md has the real times.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

---

## Phase 6 — Video + nộp bài (T+6:00–7:00 · 16:00–17:00, **nộp lúc 16:45**)

### Phân việc
| Ai | Việc | Hạn |
|---|---|---|
| P4 | `$mvp-demo`: assemble → `check_overlaps` → `contact_sheet` → xem hết 1 lượt → upload (YouTube unlisted/Drive, đúng thể lệ) → demo link | 16:30 |
| P1 | Đoạn "Architecture & policy" cho write-up (≤150 chữ) + kiểm README phần chạy app trên máy sạch | 16:20 |
| P2 | Đoạn "AI design" + "How Codex was used": số task, accepted/edited/rejected, số thread song song, skills đã dùng, `/review` findings, fix loop | 16:20 |
| P3 | 6 screenshot sạch (P3-6) và sửa lỗi UI chặn video; các segment đã quay ở Phase 5 | 16:15 |
| P4 | Hotfix blocker (nếu có): `$sync-gate 6`, tag `submit` | 16:40 |
| P4 | Ghép write-up + declaration theo [SUBMISSION.md](SUBMISSION.md), tổng kết CODEX_LOG, chuyển repo public (nếu cần), nộp form | **16:45** |

### Prompt chính P4-6 (effort: medium)
```text
You are P4, Phase 6 (T+6:00–7:00). Submission is due at 16:45 local time. Fill docs/SUBMISSION.md from the template in
docs/team-plan/SUBMISSION.md using only facts present in the repo: docs/results/* (measured numbers with mode and date),
docs/tracking/CODEX_LOG.md (count tasks by outcome and lane; quote 1–2 notable loops), .agent/plans/* (decisions and
surprises), git log (first commit time, number of commits per lane), the teammates' paragraphs I paste below.
Write: (1) project write-up (problem, solution, build directions Deep Domain AI + Autonomous & Adaptive AI with
concrete evidence, how Codex was utilised, results, limits), (2) declaration (prepared-before-the-event materials listed
explicitly; OSS with licenses from the installed packages' metadata — run pip show / npm ls, do not guess; personal
tools used; verify whether application code under backend/, frontend/ and scripts/ was written on 31 Oct between
10:00 and 17:00 from git history. Explicitly list the earlier init commit and prepared _outside-repo/skills/demo kit;
never claim all source files in the repo were written during the event), (3) the submission checklist with links.
Flag anything you could not verify instead of inventing it.
DONE WHEN: docs/SUBMISSION.md has write-up, declaration and checklist; every number links to a file in the repo.
IF UNSURE
Check the official docs and the installed version first (AGENTS.md §4); ask me only on the AGENTS.md §5 triggers,
each question with your recommended default; otherwise decide, log it in the ExecPlan and continue.
```

### Checklist nộp (16:30–16:45)
- [ ] Repo: README, `docs/SUBMISSION.md`, `docs/results/*`, `docs/tracking/CODEX_LOG.md`, `.agent/plans/*`, không có `.env` (chạy `git ls-files | Select-String '(^|/)\.env$'` phải ra rỗng); skill/demo kit trong `_outside-repo/skills` đã được khai đúng là công cụ setup từ commit init.
- [ ] Demo link mở được ở chế độ ẩn danh. Độ dài video đúng giới hạn.
- [ ] Write-up có đủ problem, solution, 2 direction, cách dùng Codex.
- [ ] Declaration có đủ phần chuẩn bị trước, OSS, personal tools (mvp-demo kit, skills), và phần build trong ngày.
- [ ] Form đã nộp, chụp màn hình xác nhận.

---

## Q&A prep (P4 trả lời phần "toàn cảnh")
- *Có overfit demo không?* → Đưa số trên blind sets, metamorphic tests, test guard chặn hardcode, vocabulary học có provenance.
- *Codex làm gì, người làm gì?* → Dẫn CODEX_LOG, ExecPlans, skills, `/review`, fix loop.
- *Số liệu đo thế nào?* → Mode replay, ngày đo, gold soát bởi ai, set nhỏ, không tuyên bố độ chính xác toàn sàn.
- *Cái gì làm trong ngày, cái gì chuẩn bị trước?* → Declaration và commit đầu tiên "prepared materials".
