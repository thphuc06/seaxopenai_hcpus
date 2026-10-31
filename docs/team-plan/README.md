# Team plan — Product Truth Passport, ngày thi 31/10/2026 (4 người · 7 giờ · Codex)

Folder này là kịch bản làm việc của team trong 7 giờ: 3 người code song song 3 lane, 1 người integrate. Mọi lane đi theo **cùng 7 phase, cùng mốc giờ**, nên ở mỗi mốc Sync integrator biết chính xác phải merge và kiểm tra những gì.

| File | Ai đọc | Dùng để làm gì |
|---|---|---|
| `README.md` (file này) | cả team, đọc trước | Lịch, luật chơi, hợp đồng giữa các lane, map 2 direction, setup Codex |
| [`AGENTS.contest.md`](AGENTS.contest.md) | Codex (tự động) | Sáng 31/10 copy thành `AGENTS.md` ở root repo thi. Codex tự nạp vào mọi prompt |
| [`PLANS.contest.md`](PLANS.contest.md) | Codex | Copy thành `.agent/PLANS.md`. Đây là template ExecPlan, mỗi lane giữ một bản sống |
| [`P1-backend-core.md`](P1-backend-core.md) | P1 | Phase 0–6 kèm prompt cho lane dữ liệu, luật, API |
| [`P2-ai-agents.md`](P2-ai-agents.md) | P2 | Phase 0–6 kèm prompt cho lane model, agent, RAG, web |
| [`P3-frontend.md`](P3-frontend.md) | P3 | Phase 0–6 kèm prompt cho lane UI 3 vai trò và glass box |
| [`P4-integrator.md`](P4-integrator.md) | P4 | Phase −1…6: skeleton, contract, test nghiệm thu, eval, merge, video, nộp bài |
| [`SUBMISSION.md`](SUBMISSION.md) | P4 + cả team ở Phase 6 | Template write-up, declaration, README repo, checklist nộp |
| [`PACK-README.md`](PACK-README.md), [`pack.gitignore`](pack.gitignore) | P4 | Bản gốc của `README-PACK.md` và `.gitignore` trong `open-ai-pack/`. Pack đã được import vào root repo trong commit init; không build/copy lại ở ngày thi |
| `_outside-repo/skills/` (root repo) | Codex | Đủ 6 skill và demo kit đã có trong commit init; có thể cài vào `~/.agents/skills/` trên mỗi máy |

Thứ tự đọc cho mỗi người: README §1–§8 → file lane của mình → `AGENTS.contest.md`. P4 đọc thêm hết các file lane khác.

---

## 1. Cuộc thi — những gì đã kiểm tra

Nguồn: [codexhackathon.sea.com](https://codexhackathon.sea.com/) (đọc ngày 29/10/2026).

- **Thời gian:** 31/10/2026 tại Shopee Vietnam Office, HCMC. 8:30 check-in. **Hack 10:00–17:00.** Sau 17:00 là chấm vòng 1 (giám khảo đi vòng các bàn) rồi finalist lên sân khấu.
- **Tiêu chí chấm:** problem framing · quality of build · depth of thinking · **how effectively Codex was leveraged in the build process**.
- **Luật quan trọng:** *"Pre-built code or existing projects shall not be submitted. Ideas can be prepared in advance, but all building must take place on the day."* Hệ quả:
  - Repo nộp là **repo mới**. Chứa pack chuẩn bị đã khai báo bên dưới, cộng với application code **và dataset** do Codex tạo trong ngày (case thật được fetch và capture trong ngày từ các URL đã ghi trong `docs/DATASET-SPEC.md`). Không mang application code từ bản rehearsal vào repo thi.
  - Repo này giữ đủ skills/demo kit trong `_outside-repo/skills` như công cụ setup chuẩn bị trước theo quyết định nhóm.
    Khai rõ trong declaration và commit init; không tính chúng là application code viết trong giờ thi.
- **Nộp bài** (theo yêu cầu team nhận được): GitHub repo · project write-up (problem, solution, build direction, cách dùng Codex) · demo link · declaration. Template ở [SUBMISSION.md](SUBMISSION.md).
- **Tài nguyên:** mỗi người $100 OpenAI API credits và Codex credits. Kích hoạt theo email gửi trước 1 ngày. Cài Codex app trước. Không có Tavily, nên web discovery dùng OpenAI hosted `web_search`.
- **Direction team đã chọn:** **Deep Domain AI** + **Autonomous & Adaptive AI** (map chi tiết ở §9).

## 2. Đội hình

| Lane | Vai trò | Sở hữu (tóm tắt) | Đầu ra cuối ngày |
|---|---|---|---|
| **P1** | Backend core: dữ liệu, luật, API | DB, seed, admission, worker, run orchestration, policy, publish gate, chain, gap controller, marketplace, toàn bộ REST | Backend chạy đủ demo story ở fallback và replay, mọi rule có test |
| **P2** | AI: model, agent, RAG, web | LLM client (4 mode + replay), budget, extraction, normalize, learned vocab, claims auditor, agent (Manager + specialist + anchor verify), retrieval, Web Scout, OCR, smoke/record | Mọi model call đều đi qua budget và có replay, agent tạo ra thay đổi mà code verify được |
| **P3** | Frontend: 3 vai trò + glass box | `frontend/**` | Buyer, Operator, Reviewer, Observe, Receipt. Dễ đọc ở 720p, có `data-testid` ổn định |
| **P4** | Integrator (đề xuất: **người nắm toàn bộ spec**) | Skeleton, contract (`models.py`, `config.py`, `main.py`), fixtures, test nghiệm thu, eval, E2E, docs, merge, video, nộp bài | Repo nộp green, video, write-up, declaration |

P4 là người duy nhất merge vào `main`. P4 cũng là người bấm giờ và người gọi cắt scope.

## 3. Lịch tổng — 7 phase đồng bộ

Sync = **10 phút cuối** mỗi phase. "Must" phải có ở Sync, "Should" làm nếu kịp, "Could" là stretch. Chi tiết nằm trong file lane.

Ưu tiên Must/Should/Could trong lane và scope đã chốt gần nhất quyết định phần phải làm; các bước BUILD kế thừa
ưu tiên đó. Bảng dưới là đích chung, không tự nâng Should thành Must. P4 ghi scope cut một lần trong HANDOFF,
đồng bộ test được chọn và storyboard; tính năng đã hoãn không chặn Sync. Không đổi assertion hoặc che regression của
phần vẫn giữ. Prompt được tinh chỉnh theo tình hình; chỉ thay đổi contract/verdict dùng chung mới cần cập nhật spec
và báo lane liên quan. Không cần duyệt lại quyết định người dùng đã chốt.

| Phase | T+ / giờ thật | Kết quả phải có ở Sync | P1 | P2 | P3 | P4 |
|---|---|---|---|---|---|---|
| **0 · Nền móng & hợp đồng** | 0:00–0:30 · 10:00–10:30 | **S0:** smoke PASS/FAIL đã rõ · backend boot · seed chạy · pytest collect · frontend boot với mock | `db.py` đủ schema, `seed.py` generic, `store.py`, `trace.py` | kích hoạt key, `smoke.py` 8 bước dùng builder của pipeline, khung `llm/client.py` + `budget.py` | Vite/React/TS, router 5 trang, `types.ts`, mock, api client có role header | checkout repo đã init, AGENTS/PLANS và docs sẵn có; `config.py` đủ switch, `models.py`, `main.py` + stub, conftest, `.env.example` · **dataset đầu tiên S1 + event 01–03/08** (P4-0c) |
| **1 · Xương sống** | 0:30–1:45 · →11:45 | **S1 = M1:** Operator "Bootstrap" → Buyer thấy 5 field có citation (fallback) · NOOP/DUPLICATE/REJECTED · GET passport không tạo gì | admission, worker, `run.py`, policy R1–R11 + REQ, publish gate, API core | client đủ 4 mode, replay key hash toàn bộ input, fallback extractor, `extract.py`, `normalize.py`, live extract đầu tiên (record) | Buyer Passport (ngôn ngữ dễ hiểu), evidence drawer, badge, Operator v1 → **chuyển sang API thật** | toàn bộ AC-01…20 viết sẵn có phase marker, `demo_reset`, merge · **case synthetic S1–S4 + ảnh nhãn + gold nháp** (P4-1c) |
| **2 · Mâu thuẫn nguồn + vòng đời + model thật** | 1:45–3:00 · →13:00 | **S2 = M2:** revoke → STALE → re-assess · Conflict in source · review gắn revision · có 1 run model thật được record | version mới/revoke/stale, gap + evidence request, reviews (override qua gate), PARTIAL · thread 2: scope inference + copy detection | vision, coverage retry an toàn, canon (chỉ học từ claim đã validate), claims auditor, **budget cả run + deadline cứng**, record pass 1 | Reviewer console, stale ripple, claims (buyer chỉ thấy số đếm), control room + stepper | eval B0, chuẩn bị fix-loop, theo dõi CODEX_LOG · **capture sản phẩm thật R1–R4 + gold Codex soạn, người duyệt** (P4-2b) |
| **3 · Agentic + RAG + glass box** | 3:00–4:15 · →14:15 | **S3 = M3:** agent đổi được ít nhất 1 verdict **mà code verify được** (anchor) · Why? panel; hybrid search = Should | gap controller + mock registry, explain, observability, gắn hook agent · thread 2: hash chain, graph, search (OTel = Could) | pre-pass + **single typed call + anchor verify** · thread 2: retrieval (BM25 + embed lúc ingest + RRF) · Manager/specialist = Could | Why? (buyer gọn / expert đủ), waterfall, agent panel trước/sau, Ask the evidence, graph | **blind set (Codex soạn đáp án trước lần chạy đầu, người duyệt)**, B1, harness `blind_eval`, retrieval eval, **storyboard + callout/timing; narration.json={}** |
| **4 · Khác biệt + nâng cấp** | 4:15–5:15 · →15:15 | **S4 = M4:** web discovery có audit · receipt; marketplace UI/OCR = Should; khi thiếu giờ áp §8 | receipts, marketplace, policy-v2 (web), *stretch:* scheduler theo priority | Web Scout (OpenAI web_search → code fetch/clean/identity/snapshot), OCR · thread 2: `record_all.py` · *stretch:* evidence scout, reviewer copilot | receipt, marketplace, web audit, OCR overlay, Observe, time slider, `scripts/e2e.py` (Playwright) | chốt storyboard cho P3, chạy blind set, **marketplace thật R5**, gom số liệu và bằng chứng Codex |
| **5 · Hardening & freeze** | 5:15–6:00 · →16:00 | **FREEZE 16:00:** tất cả green ở `LLM_MODE=replay` | sửa bug, sync docs 03–06, kiểm `POLICY_VERSION` · thread 2: `metrics.py` + route | **record sau tag sync-4 (~15:15), freeze recordings 15:35 (tag `rec-freeze`)** | polish, rà wording, build tĩnh, E2E green · thread 2: **quay segment video** (`record_demo.py`) sau `rec-freeze` | số eval/metrics cuối, `$sync-gate 5 rec` (15:35) và `$sync-gate 5` (15:50, tag `freeze`), README repo |
| **6 · Video + nộp** | 6:00–7:00 · →17:00 | **Nộp xong lúc 16:45** (đệm 15 phút) | phần architecture trong write-up + README chạy app | phần AI design + số liệu "how Codex was used" | 6 screenshot, sửa lỗi UI chặn video | `$mvp-demo` → upload → link, write-up, declaration, nộp |

Sau 17:00: 2 lượt pitch thử, mỗi người chuẩn bị Q&A cho lane mình (cuối mỗi file lane có danh sách câu hỏi).

## 4. Giao thức Sync, git, CCR

**Branch.** Mỗi người **một branch cho cả ngày**: `p1`, `p2`, `p3`, `p4`. Chỉ P4 merge vào `main`. Đầu mỗi phase: `git fetch --tags; git merge sync-<N-1>`. **Không rebase branch đã push:** push sau rebase bị `rejected (non-fast-forward)` và phải force-push, mà AGENTS cấm (đã chạy thử). Luôn dùng merge.

**Hai thread mỗi người** (theo [git worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) và [local environments](https://learn.chatgpt.com/docs/environments/local-environment) của Codex app):
- **Thread 1 = Local**, checkout chính trên branch `p<k>`. **Chỉ thread này chạy server**, bằng Actions trên thanh trên cùng của app (`backend`, `frontend`), nên không tranh cổng 8000/5173.
- **Thread 2 = Worktree** (chat mới, chọn Worktree), dùng cho "Prompt phụ"; tiêu đề prompt phụ ghi giai đoạn bắt đầu ("từ đầu phase", "khi thread 1 đã commit …", "sau tag …"). Codex tạo worktree trong `$CODEX_HOME/worktrees` ở trạng thái detached HEAD, chạy setup script (`scripts/dev/setup_worktree.ps1`, P4 cấu hình ở Phase 0) để có `.venv` và `node_modules`, và copy `backend/.env` nhờ `.worktreeinclude`. Trước commit đầu tiên, bấm **Create branch here** → `p<k>-b<N>`. Không dùng `p<k>/…`, vì git không tạo được `refs/heads/p1/x` khi branch `p1` đã tồn tại. Thread 2 sửa file khác thread 1 hoặc chỉ viết test, chỉ chạy test in-process (`pytest`, `sync_check.py`), không bật server.
- **T−12:** ở checkout Local, chạy `git merge p<k>-b<N>` (worktree dùng chung `.git` nên không phải push branch phụ), chạy test, rồi push `p<k>` trước T−10. Chỉ archive chat của thread 2 **sau khi đã merge**: archive xóa worktree, và app chỉ giữ 15 worktree gần nhất.

**Mini-sync hợp đồng lúc T+20 (Phase 1–4).** Vì code chỉ ghép ở Sync, lane dùng interface của lane khác sẽ bị "mù" cả phase nếu không có bước này.
1. P1 và P2 push **commit đầu tiên của phase** chỉ gồm route và hàm mới ở dạng stub: route có `response_model`, trả 501 hoặc dữ liệu ví dụ; hàm đúng signature §7.1. Message `S<N> P<k>: contract`. Ở Phase 1, P4 cũng push `S1 P4: contract` gồm **test nghiệm thu phase 1**, để P1/P2 có đích ngay từ ~10:50 thay vì chờ tới S1.
2. P4 chạy `$sync-gate <N> contract`: merge riêng các commit đó (và lane nào trễ Sync trước), mỗi lần có test trước khi commit merge, rồi tag `contract-<N>` và push.
3. Mọi lane `git fetch --tags; git merge contract-<N>`. P3 sinh type từ `/openapi.json` và cập nhật mock.

**Checkpoint hai lượt (Prompt chính, thread Local, Phase 1–4).** T+20 ở đây là 20 phút sau khi phase bắt đầu
(ví dụ Phase 1 bắt đầu 10:30 → đích push trước 10:50), không phải T+0:20 của cả ngày thi.
- **Lượt A — contract trước:** P1/P2 chỉ làm interface mới và phần hỗ trợ tối thiểu để import/collect/OpenAPI hoạt động,
  cùng test contract cần thiết; không làm toàn bộ BUILD rồi mới push. P4 Phase 1 ưu tiên acceptance tests phase 1;
  Phase 2–4 chỉ đưa shared contract đã thống nhất/CCR được xử lý nếu có, không phải đẩy một bộ test mới mỗi phase.
  Chỉ sửa file mình sở hữu. Nếu không có thay đổi contract, báo `CONTRACT_NO_CHANGE`, không tạo commit rỗng hay thay stub
  đã có implementation bằng stub mới; mini-sync vẫn do P4 xử lý theo lịch hiện hành.
- Kiểm branch Local đúng `p<k>` và remote `origin`; chạy pytest/guards theo gate contract hiện hành (phase N−1, với
  WAITING được giải thích theo `needs`, không sửa PHASE/marker). Chỉ stage file/hunk contract, test và ghi chú checkpoint
  liên quan; không gom việc chưa liên quan hoặc merge branch phụ. Commit `S<N> P<k>: contract`, tự push lên đúng
  `origin/p<k>` theo ủy quyền của prompt, rồi kiểm SHA remote khớp checkpoint. Không force push; lỗi test/push phải báo
  nguyên nhân, không tuyên bố đã đẩy thành công. Không làm rộng BUILD để chữa test phase N chưa được triển khai.
- **Dừng turn sau checkpoint:** cập nhật ExecPlan rồi báo `CONTRACT_PUSHED` (branch, SHA, file, test counts và trạng thái
  push), `CONTRACT_NO_CHANGE`, hoặc `CONTRACT_BLOCKED` (lỗi và phần đã làm). Kèm bước tiếp theo. Không tự tiếp tục BUILD,
  tự chờ đến giờ hay tự chạy `$sync-gate`. Đây là điểm dừng người dùng yêu cầu, không phải xin lại quyền push đã có.
- **P4 chạy mini-sync riêng:** khi nhận checkpoint các lane, người cầm P4 gọi `$sync-gate <N> contract`; skill tạo tag
  theo gate hiện có. P4 cũng dừng sau lượt A trước khi được yêu cầu chạy gate hoặc tiếp tục phần việc của P4.
- **Lượt B — người cầm lane nhắn tiếp tục:** ví dụ `Tiếp tục Phase 2 của P1 sau mini-sync contract-2.` Codex đọc checkpoint
  trong ExecPlan, fetch và merge `contract-2` vào `p1`, rồi thực hiện phần còn lại của Prompt chính; không tạo lại lượt A.
  Nếu tag chưa có hoặc có merge conflict, báo đúng trạng thái và làm phần độc lập theo interface cũ; không giả định phần
  chưa ghép đã sẵn sàng, không tự giải quyết conflict ngoài lane. Lượt B vẫn self-review/push ở Sync cuối như bình thường.

Checkpoint do **Prompt chính** phụ trách. Prompt phụ có thể đụng file/helper liên quan contract, nhưng chỉ làm phạm vi
được giao trên `p<k>-b<N>` và bàn giao local; không tự push `p<k>` hay chạy mini-sync. Nếu checkpoint cần một file của
thread phụ thì owner phải bàn giao/commit phần tối thiểu rõ ràng trước; không mặc định kéo toàn bộ task phụ vào lượt A.

Mẫu dùng: `$phase-kickoff P1 2` → Codex làm lượt A và dừng → P4 gọi `$sync-gate 2 contract` → người cầm P1 nhắn
`Tiếp tục Phase 2 của P1 sau mini-sync contract-2.` Cách này áp dụng cả khi dán riêng Prompt chính; Phase 0/5/6 giữ
các mốc skeleton/recording/freeze/submission riêng. Sau khi cập nhật pack, các máy đã cài skill cần copy lại bản
`_outside-repo/skills/phase-kickoff` vào thư mục skill đang dùng để có checkpoint mới.

Trong phase, "xong" của P3 = build pass trên mock và type khớp `contract-<N>`. Click path trên backend thật được kiểm ở Sync.

**Tại mỗi Sync (P4 chạy `$sync-gate N`):**
1. **T−20:** mỗi lane chạy `$self-review`. **T−10:** P1, P2, P3 push (T−8 là hạn chót ân hạn). Commit message có dạng `S<N> P<k>: <việc> (codex)` hoặc `(human)`. Gửi kèm *báo cáo cuối turn* của Codex (mẫu trong AGENTS §6).
2. **Sync tối thiểu (~5 phút, thread Local của P4):** merge theo thứ tự **P4 → P1 → P2 → P3**. Lấy baseline mới trên `main` ngay trước **từng** merge; `git merge --no-commit --no-ff`, chạy cùng test/mode (và build nếu frontend đổi), đạt thì commit, regression thì `git merge --abort`. S0: P4 đã làm trên `main`, chỉ merge P1→P2→P3 và luôn kiểm phase 0; tạo `p4` sau S0. Không dùng `revert -m 1` để quay lại rồi merge lại lane như bình thường. Conflict ngoài file P4 chuyển owner xử lý và retry với baseline mới.
3. P4 ghi `PHASE=N`, chạy suite phase N, guards và fixture/sync checks nếu đã có. Test chỉ phụ thuộc lane đã merge phải xanh; `WAITING` cần node ID, marker `needs(...)` và phần việc chưa merge. Lỗi chưa giải thích, regression, collection/guard/build/check lỗi đều **chặn tag/push checkpoint**, dù trễ giờ. Sau gate, ghi `## sync-N` vào HANDOFF với trạng thái từng lane, CCR, WAITING và scope cut; commit cùng checkpoint **trước khi tag/push `sync-N`**. Thiếu handoff cũng chặn tag. Checkpoint còn `WAITING` phải ghi partial, không gọi milestone hoàn tất. `rec-freeze`, `freeze`, `submit` không chấp nhận `WAITING` trong phạm vi bắt buộc. Chi tiết recovery ở skill `sync-gate`.
4. Mọi người `git fetch --tags; git merge sync-N`. Nếu AGENTS.md vừa đổi thì mở thread mới: Codex chỉ nạp AGENTS.md lúc bắt đầu một phiên.
5. **Sau tag**: các lane kickoff phase mới đọc **HANDOFF từ chính `sync-N`** (mỗi lane 3–5 dòng đã có trước tag), cùng Outcomes trong ExecPlan của các lane khác, rồi ghi "Context from other lanes" vào ExecPlan của mình. Không có khoảng chờ handoff sau tag. P4 làm `/review`, click path tay bằng Actions, DEVLOG/CODEX_LOG và commit các log lên `main`; không di chuyển tag. Nếu thiếu Must thì áp **luật cắt scope** (§8) ngay, không tranh luận.

**CCR (Contract Change Request).** Khi cần đổi một contract (§7) hoặc sửa file của lane khác: **không tự sửa**. Gửi cho owner (hoặc P4 nếu là file shared) theo mẫu:

```
CCR <lane→owner>: <file/contract> · cần: <signature/field/route mới> · lý do: <1 câu> · đề xuất snippet: <...>
```

Owner xử lý trong vòng 10 phút hoặc trả lời "để sau Sync N".

**Test theo phase.** Ở Phase 1, P4 viết sẵn mọi test nghiệm thu (test phase 1 đi trước, trong `contract-1`), gắn `@pytest.mark.phase(n)`. `conftest.py` skip test có `n` lớn hơn phase hiện tại. Phase hiện tại lấy từ env `CONTEST_PHASE`, mặc định đọc file `backend/tests/PHASE`. Sau Sync N, `PHASE=N`; test phase ≤N phụ thuộc phần việc đã merge phải xanh, còn `WAITING` phải được công khai. Lane đang làm phase N+1 tự đặt `$env:CONTEST_PHASE=<N+1>`. `pytest -m phase --co` chỉ liệt kê mọi test mang marker, không lọc riêng argument N và không chứng minh test đã chạy. Chạy `$env:CONTEST_PHASE=3; .venv/Scripts/python -m pytest -m phase` để thực thi theo gate phase.

## 5. Bản đồ sở hữu file (repo thi)

Layout ở root: `backend/`, `frontend/`, `scripts/`, `fixtures/`, `docs/`.

| Owner | File / thư mục |
|---|---|
| **P1** | `backend/app/{db,seed,store,trace,worker,chain,context}.py` · `backend/app/events/**` · `backend/app/api/**` · `backend/app/pipeline/{run,policy,compare,publish,scope,gaps,marketplace,scheduler}.py` · `backend/app/connectors/registry.py` · `scripts/metrics.py` · test: `test_policy, test_events, test_publish, test_staleness, test_reviews, test_chain, test_scope, test_gaps, test_glassbox, test_orders, test_marketplace` |
| **P2** | `backend/app/llm/**` · `backend/app/budget.py` · `backend/app/pipeline/{extract,fallback_extract,normalize,canon,claims_audit,ocr,web_sources,scope_prepass}.py` · `backend/app/agent/**` · `backend/app/retrieval/**` · `backend/app/connectors/websearch.py` · `backend/app/data/*.json` · `scripts/{smoke,retrieval_eval,record_all}.py` · test: `test_llm_client, test_extract, test_normalize, test_canon, test_claims, test_agent, test_retrieval, test_web, test_replay` |
| **P3** | `frontend/**` (gồm `src/types.ts`, `src/api/*`, `src/mock/*`) · `scripts/e2e.py` · `scripts/demo/record_demo.py` |
| **P4** | `AGENTS.md` · `.agent/PLANS.md` · `.agent/plans/P4.md` · `.gitignore` · `.worktreeinclude` · `.codex/**` · `scripts/dev/**` · `backend/requirements*.txt` · `backend/.env.example` · `backend/pytest.ini` · `backend/app/{config,models,main}.py` · `backend/app/pipeline/baseline.py` · `backend/tests/{conftest.py,PHASE,test_acceptance.py,test_guards.py}` · `fixtures/**` · `scripts/{seed,demo_reset,check_fixtures,sync_check,eval,blind_eval,codex_stats}.py` · `scripts/demo/**` (trừ `record_demo.py`) · `docs/**` (trừ mục "As built") · `README.md` |

Ở Phase 0, P4 tạo **stub đúng signature** cho các interface liên lane (§7.1), **trừ** `db/seed/store/trace.py` mà P1 tự tạo từ 10:05. Sau đó owner nhận file và sửa tự do, miễn là giữ signature.

**Ngoại lệ về docs:** mục "As built (contest)" của `docs/03–06` do P1 cập nhật, của `docs/07` do P2 cập nhật. Phần còn lại của `docs/**` thuộc P4.

**ExecPlan:** `.agent/plans/P<k>.md` thuộc lane k, mỗi lane tự cập nhật file của mình. P4 sở hữu template `.agent/PLANS.md` và `.agent/plans/P4.md`.

## 6. Mô hình chung (chỉ nhắc lại để cả team nói cùng một ngôn ngữ)

```
event ─► admit (producer · idempotency · material filter · STALE dependents · bump revision) ─► queue
worker ─► run: pin revision ─► extract (model/fallback/replay, cached per source version) ─► normalize
      ─► scope (code inference ─► code pre-pass ─► agent + anchor verify) ─► policy (code, versioned)
      ─► claims audit (model finds, code judges) ─► gap controller (code hops) ─► publish gate ─► field_results (+chain)
buyer GET passport ─► read stored results only (never a model call, never a job)
```

Budget: **một `Budget` cho mỗi run**, mọi model call đều trừ vào đó (extract, retry, canon, claims, agent, web scout). Agent loop giữ thêm giới hạn riêng theo AGENTS rule 8. Hết budget thì run chuyển `PARTIAL` + `stop_reason`.

S0 stop-code vocabulary: root budget uses `MODEL_CALL_LIMIT`, `TOOL_CALL_LIMIT`, `RUN_DEADLINE`;
agent child uses `AGENT_MODEL_CALLS`, `AGENT_TOOL_CALLS`, `AGENT_DEADLINE`. Retain these tested names.

## 7. Hợp đồng liên lane

### 7.1 Python interfaces (P4 tạo stub ở Phase 0)

| Interface | Owner → consumer | Signature (giữ nguyên tên) | Cần thật ở |
|---|---|---|---|
| `app/context.py::RunContext` | P1 → P2 | `@dataclass RunContext(run_id, case_id, tenant_id, case_revision, product: dict, mode: str, budget: Budget, trace: TraceWriter)`. `product` gồm id, name, brand, variant, market, web | S0 |
| `app/trace.py::TraceWriter` | P1 → P2 | `.step(step, actor="code", input_refs=None, output_refs=None, detail=None, latency_ms=0, tokens_in=0, tokens_out=0, error=None)` · `.timed(step, actor)` (context manager) | S0 |
| `app/store.py` | P1 → P2 | `add_source_version(snapshot: dict, *, case_id: str \| None, origin: str, raw_path: str \| None = None) -> SourceVersionRef` (idempotent theo sha256; gọi `retrieval.index_source_version` và `ocr.index_image` nếu có) · `passages(sv_id) -> list[dict]` · `current_sources(case_id) -> list[dict]` | S1 |
| `app/seed.py` | P1 → P4 | `reset() -> None` · `load_product_dir(path, *, case_id_override=None) -> str` (product_id) · `seed_if_empty() -> bool` (startup hook của `main.py`) | S0 |
| `app/budget.py::Budget` | P2 → P1 | `Budget.from_settings()` · `take_model_call(step)` · `take_tool(name)` · `remaining_s()` · `stop_reason -> str \| None` · `usage() -> dict` · `class BudgetExceeded(Exception): reason` | S1 (stub S0) |
| `app/llm/client.py::parse` | P2 → P2/P4 | `parse(*, step, model, instructions, input_parts, schema, ctx, prompt_version, effort=None, max_output_tokens=None) -> LLMResult(parsed, usage, replayed, model)`. Lỗi trả về dưới dạng `LLMError(code)` với `code ∈ {INCOMPLETE, REFUSAL, REPLAY_MISS, API_ERROR}` hoặc `BudgetExceeded`. Mọi lời gọi mạng đi qua đúng một hàm `_call_api(**request)`, là điểm test monkeypatch. Giá model nằm ở `app/data/model_prices.json` (P2 điền ở Phase 0) | S1 |
| `app/pipeline/extract.py` | P2 → P1 | `extract_source_version(sv_id, ctx) -> Extraction(claims: list[Claim], ignored_instructions: bool, extractor: str, cached: bool)`. Claim gồm `id, source_version_id, passage_id, field_key, raw_value, normalized: dict, quote, readability, extractor, prompt_version, mapped_by` | S1 (fallback), S2 (model) |
| `app/pipeline/normalize.py` | P2 → P1 | `normalize(field_key, raw_value, proposed=None) -> dict \| None` · `volumes_in(text) -> list[dict]` · `skin_types_in(text) -> set[str]` · `parse_inci(text) -> list[str]` · `company_key(text) -> str` | S1 |
| `app/pipeline/compare.py` | P1 → P2 | `compatible(field, claim_value, ref_value) -> bool` (có chiều) · `agree(field, a, b) -> bool` (đối xứng) · `same_volume(a, b, tol=0.01) -> bool` | S1 |
| `app/pipeline/policy.py` | P1 → P2/P4 | `decide(field_key, observations, product, gaps, reviews) -> FieldDecision` · `POLICY_VERSION` · `SourceObs` dataclass. Từ S2, cùng hàm này quyết định `claim:*` theo CL; audit không có bộ rule quyết định riêng | S1 (CL ở S2) |
| `app/models.py::FieldDecision` | P4 (shared) | Pydantic: `field_key, verdict, conflict_locus, scope_match, review_state, evidence_level, seller_attributable, citations: list[Citation], depends_on: list[DependsOn], public_text, notes: list[str], explain: list[RuleStep], gap: Gap \| None, needs_scope_resolution: bool` | S0 |
| `app/pipeline/scope_prepass.py` + `app/agent/scope_resolution.py` | P2 → P1 | `resolve_all(ctx, observations, fields) -> ScopeOutcome(decisions: list[PassageScope], changed: bool, stop_reason: str \| None, effect_note: str)`. `PassageScope(passage_id, sv_id, scope_match ∈ {MATCH, MISMATCH, AGENT, UNKNOWN}, decided_by ∈ {CODE, AGENT_VERIFIED, AGENT, FIXED_WORKFLOW, REPLAY}, anchor_passage_id, reason)` | S3 (no-op stub trước đó) |
| `app/pipeline/claims_audit.py` | P2 → P1 | `audit(ctx, listing_obs, observations) -> list[FieldDecision]` (field_key `claim:<kind>:<detail>`). P2 trích xuất/kiểm quote/chuẩn hóa thành `SourceObs`; gọi `policy.decide(...)` cho từng claim; trả nguyên quyết định của policy, không tự đặt verdict/review_state/public_text | S2 |
| `app/pipeline/gaps.py` | P1 → P1 | `close_gaps(ctx, decisions, observations) -> GapOutcome(new_sv_ids, stops)` | S3 |
| `app/retrieval/search.py` | P2 → P1 | `index_source_version(sv_id) -> None` (gọi lúc ingest) · `search(case_id, query, *, k=8, mode="auto", allowed_sv_ids=None) -> SearchResult(hits, stages)` | S3 (BM25 từ S2) |
| `app/pipeline/web_sources.py` | P2 → P1 | `discover(ctx) -> WebOutcome(new_sv_ids, searches, stop_reason)` | S4 |
| `app/pipeline/ocr.py` | P2 → P1 | `index_image(sv_id) -> None` · `boxes_for(sv_id, excerpt) -> list[Box]` | S4 |

### 7.2 REST (P1 → P3), tất cả dưới `/api`, role đi qua header `X-Demo-Role`

**S0 implementation conventions (31 Oct, P4):** Settings attributes use snake_case and environment keys use uppercase;
relative paths resolve from `backend/`. `reload_settings()` updates the shared object in place. Model IDs stay empty
until P2 smoke selects them; absent price data means `price unknown`. `GET /api/health` returns `llm_mode`,
`models` (`extract`, `agent`, `cheap`, `embed`), `policy_version`, `phase`, `demo_run_delay_s`.
`RuleStep.detail` is a string; trace detail is JSON. `ClaimFinding` currently has the `FieldDecision` shape.
P4 also owns `backend/tests/test_skeleton.py` for these startup/config/schema contracts.
P4 owns `backend/tests/test_fixtures.py` for the dataset validator and source/gold integrity checks.
P4 owns `backend/tests/test_operations.py` for its seed/reset/sync CLI boundaries.
P4 owns `backend/tests/test_evaluation.py` and `test_sync_phase_two.py` for B0,
offline reports and S2 operational harness boundaries.
P4 also owns scripts/baseline_eval.py and tests/test_baseline_b1.py,
test_blind_evaluation.py and test_sync_phase_three.py for the S3 diagnostic harnesses.
Admission configuration is `config.PRODUCER_EVENT_TYPES` and `config.NON_MATERIAL_FIELDS`
(immutable server-side constants, docs05 §1); P1 retains role/type authorization.
Pinned RapidOCR requires Python <3.13; the shared setup uses Python 3.11/3.12.

| Sync | Route | Ghi chú cho P3 |
|---|---|---|
| S1 | `GET /products` · `GET /products/{id}/passport` · `GET /products/{id}/fields/{f}/evidence` · `POST /internal/events` · `GET /internal/events/catalog` · `POST /internal/demo/fire/{name}` · `GET /internal/events/log` · `GET /internal/runs` · `GET /internal/runs/{id}` · `GET /internal/metrics` · `POST /internal/demo/reset` | Passport shape giống `PassportResponse` trong `models.py`. P3 nên sinh type từ `/openapi.json` (`npx openapi-typescript`) |
| S2 | `GET /review/queue` · `POST /cases/{id}/reviews` (409 khi lệch revision, 422 `NO_CITATION`/`FORBIDDEN_WORDING`) · `GET /cases/{id}/history` · `POST /cases/{id}/evidence` · `GET /products/{id}/passport?as_of=` | |
| S3 | `GET /products/{id}/fields/{f}/explain` · `GET /internal/runs/{id}/otel` · `GET /internal/observability` · `GET /cases/{id}/graph` · `GET /cases/{id}/chain` · `GET /cases/{id}/search?q=&mode=` | `explain` đã được lọc theo role ở backend |
| S4 | `POST /orders` · `GET /orders` · `GET /orders/{id}` · `GET /products/{id}/marketplace` · `POST /internal/marketplace/{pid}/scan` · `POST/GET /cases/{id}/web-search` · `GET /sources/{sv}/image?as_role=` · `GET /internal/eval/metrics` | |

### 7.3 Từ vựng trace step (P1/P2 ghi, P3 tô màu theo lane)

| Lane UI | Prefix `step` | `actor` |
|---|---|---|
| code | `pin_revision`, `scope_check`, `policy:<field>`, `publish`, `publish:blocked`, `stale:mark`, `run:stop` | code |
| model | `extract`, `extract:retry`, `canon:learn`, `claims:audit` | llm (khi chạy fallback thì là code) |
| agent | `scope:code_prepass`, `agent:start`, `agent:scope_single`, `agent:tool:<name>`, `agent:proposal`, `scope:validate`, `agent:effect`, `agent:stop` | llm (tool và scope validation chạy bằng code) |
| retrieval | `embed:ingest`, `embed:query`, `retrieval:index`, `retrieval:search` | llm cho embedding; code cho index/search |
| gap | `gap:hop<n>:<name>`, `gap:stop` | code |
| web | `agent:web_scout`, `web:search`, `web:fetch`, `web:snapshot`, `web:skip`, `web:stop` | llm/code |

`detail` luôn là JSON. Các khóa chuẩn: `replayed`, `model`, `prompt_version`, `stop_reason`, `budget` (`{used, cap}` cho model_calls, tool_calls, seconds), `before`/`after` (cho `agent:effect`).

S3 scope validation stores the target in `input_refs`, the anchor in `output_refs`,
and `accepted`, `reason`, `scope_match` in detail. Only a current-run code
validation with accepted=true establishes a verified placement; raw proposals do
not. `agent:effect` remains P1's before/after code-policy result.
P2's additive `app.agent.retrieval.reindex_sources(ctx, source_version_ids)` and
`search_case_corpus(ctx, query, *, k=8)` bind server-owned context through
`app.retrieval.search.run_context(ctx)`. P1 has not enabled paid indexing in its
run. Ordinary expert GET search is unbound, read-only BM25; no embedding call.

### 7.4 `data-testid` (P3 → P4 E2E/video), giữ ổn định từ S1

`field-row-<field_key>` · `field-label-<field_key>` · `evidence-open-<field_key>` · `why-open-<field_key>` · `event-btn-<fixture_name>` · `scenario-next` · `run-status` · `model-calls-counter` · `review-task-<field_key>` · `review-approve` · `review-override` · `agent-panel` · `budget-meter-<kind>` · `buy-button` · `receipt-diff` · `web-audit` · `badge-origin` · `badge-mode`

### 7.5 Biến môi trường (P4 đưa hết vào `config.py` và `.env.example` ở Phase 0)

Frontend only: `VITE_USE_MOCK=1|0` selects local mock transport or `/api`. This is a Vite
build/development switch documented in `frontend/.env.example`, not a backend setting.
Use Node >=24 for frontend tests; keep Python 3.11/3.12 for the shared backend/OCR environment.

`OPENAI_API_KEY` · `LLM_MODE=fallback|replay|record|live` · `MODEL_EXTRACT` · `MODEL_AGENT` · `MODEL_CHEAP` · `EMBED_MODEL=text-embedding-3-small` · `LLM_EFFORT_EXTRACT=low` · `LLM_EFFORT_AGENT=medium` · `LLM_MAX_OUTPUT_TOKENS=16000` · `REPLAY_DIR=../fixtures/replay` (test trỏ sang thư mục tạm) · `LLM_VISION=1` · `RUN_MAX_MODEL_CALLS=24` · `RUN_DEADLINE_S=120` · `AGENT_MAX_MODEL_CALLS=10` · `AGENT_MAX_TOOL_CALLS=16` · `AGENT_MANAGER_TURNS=3` · `AGENT_RETRIEVAL_HOPS=2` · `AGENT_DEADLINE_S=75` · `AGENT_SINGLE_CALL_MAX=8` · `WEB_SEARCH=on|off` · `WEB_PROVIDER=openai|tavily` · `WEB_MAX_SEARCHES=3` · `WEB_MAX_PAGES=4` · `OCR_ENABLED=1` · `AGENTS_TRACING=1` · `REPLAY_FREEZE=0` · `WORKER_INLINE=0` · `DEMO_RUN_DELAY_S=0` · `DB_PATH` · `FIXTURES_DIR` · `CONTEST_PHASE`

Các con số budget ở trên chỉ là default. **Chốt ở S0** dựa trên latency đo được từ `smoke.py`. Ví dụ: một bootstrap 4 nguồn tốn khoảng 4 extract + 4 retry + 1 canon + 1 claims + tối đa 10 lượt agent = 20; web discovery còn cộng thêm, nên default là 24. Nếu thấy trần quá chặt thì tăng trần của run, **không nới** giới hạn của agent loop.

### 7.6 P4 operational helpers

P4 operational helpers (run from the repo root with the backend venv):
`backend/.venv/Scripts/python scripts/seed.py` seeds only an empty database;
`--reset` explicitly replaces demo state and `--db <path>` selects an isolated database.
`backend/.venv/Scripts/python scripts/demo_reset.py` resets the running backend via
the operator API; it never starts a server. `--base-url` overrides localhost:8000.
`backend/.venv/Scripts/python scripts/sync_check.py 1 --mode fallback` runs the S1
path in-process in a temporary DB and reports PASS/FAIL. `--mode replay` requires
the stored run to report REPLAY; misses/failures cannot pass. Mode defaults to
LLM_MODE, then fallback; record/live are rejected before app startup. Phase 2 now
extends S1 with revoke, evidence fulfillment, volume/review/409, injection, blurred
upload preserving prior support, source conflict and expert-claim filtering.
Its API implementation dependencies must be merged before the real path passes;
HTTP 501 or a wrong outcome is FAIL. Missing required fixtures are SKIP/incomplete.
The isolated unreadable-only clearer-photo case remains in acceptance tests; the
full story's blurred upload must not erase earlier readable evidence. Phase 3 now
extends the path with catalogue pre-pass, registry scenario and role-filtered
explain reads; replay also requires a recorded anchor/effect and registry closure.
Missing owner behavior fails the check; it does not create a passing Sync. Phase 4
remains unsupported. `scripts/eval.py` is documented in docs09;
its labelled replay-to-fallback diagnostic behavior does not apply to sync_check,
which requires the requested mode throughout and never converts a replay miss to PASS.

## 8. Luật cắt scope (quyết ngay tại Sync, không tranh luận)

| Tại | Nếu chưa có | Thì |
|---|---|---|
| S0 | smoke FAIL: vision | Ảnh nhãn chỉ dùng transcript (gắn nhãn); OCR box vẫn chạy bằng code |
| S0 | smoke FAIL: Agents SDK (cả `output_type` lẫn submit tool) | Agent chỉ dùng single typed call qua `llm.client.parse` |
| S0 | smoke FAIL: embeddings | Retrieval chỉ BM25, gắn nhãn "BM25 only" |
| S0 | smoke FAIL: web_search | Bỏ Web Scout; S4 chọn marketplace R5 (capture bằng script) |
| S0 | key chưa kích hoạt / hết quota | Tạm dùng key của thành viên khác, chỉ trong `backend/.env` máy mình (không commit, không dán vào chat công khai). Replay key không chứa API key nên recordings vẫn dùng chung được |
| S0 | smoke FAIL ở structured output | Đổi model qua env (danh sách model ở models page ngày thi). Vẫn FAIL thì build theo hướng fallback + replay, model thật chỉ dùng cho extraction |
| S1 | M1 | P2 tạm bỏ live, cùng P1 làm cho xong M1. Thu scope còn DEMO bootstrap + revoke |
| S2 | M2 | Bỏ copy detection và time travel. Vision chỉ chạy bằng transcript (gắn nhãn) |
| S3 | M3 | Agent: chỉ giữ single typed call + anchor verify, bỏ vòng Manager/specialist. Why? chỉ hiện bản expert |
| S2 (P4-2b) | trang thật bị chặn fetch | Không gõ lại trang bằng tay. Bỏ event của trang đó; `sync_check`, E2E, screenshot báo SKIP. Cảnh "Conflict in source" dùng S2 (synthetic twin của R1, DATASET-SPEC §4), gắn nhãn SYNTHETIC |
| S4 | web discovery chạy nhưng trang bị chặn | M4 vẫn tính đạt nếu audit ghi rõ trang bị chặn và lý do; không bịa nguồn |
| Mọi lúc | trang thật chứa "Chính hãng", "an toàn"… | Giữ nguyên văn (đó là lời của nguồn), chỉ hiện trong khung trích dẫn nguồn. Luật từ cấm chỉ áp cho text hệ thống viết (AGENTS luật 1) |
| 15:15 | record pass chạm trần call/$ | `record_all.py` đã chạy theo thứ tự cảnh storyboard → event 01–17 → blind set; phần chưa record chạy fallback, gắn nhãn FALLBACK. Có thể chạy tiếp bằng key của thành viên khác |
| S4 | M4 | Chọn **một** trong web discovery hoặc marketplace (ưu tiên web vì nó chứng minh direction Adaptive). Receipt chỉ làm backend |
| 16:00 | bất cứ thứ gì | Dừng code. Quay video với những gì đang chạy được |
| 16:20 | video chưa xong | Rút bớt cảnh, giữ video `--engine none` với callout/caption ngắn rồi upload |

**Mạng hội trường rớt.** Codex, git push, smoke và record pass cần mạng. Video mặc định không giọng/TTS và làm offline sau khi công cụ đã sẵn sàng; chỉ engine giọng tùy chọn mới có thể cần mạng.
- Thứ tự dùng hotspot: P2 (smoke, record) → P4 (merge, push) → các lane còn lại.
- Đồng bộ không cần GitHub (đã chạy thử): lane chạy `git bundle create p<k>.bundle sync-<N>..p<k>` rồi chép qua USB hoặc thư mục chung; P4 chạy `git fetch <file>.bundle p<k>:refs/remotes/usb/p<k>` và `$sync-gate` merge `usb/p<k>` thay cho `origin/p<k>`.
- Demo vẫn chạy được bằng replay và fallback (không cần mạng). Lùi record pass tới khi có mạng.
- Video: `--engine none`, `clips={}`, callout/caption; không gọi TTS và không tạo clip giọng giả. Chỉ thêm giọng khi người dùng yêu cầu.
- Codex không chạy được: code tay, commit ghi `(human)`, CODEX_LOG ghi lý do.

**Không bao giờ cắt:** citation/locator, scope check, buyer chỉ đọc, trạng thái "Not verified", budget + `stop_reason`, nhãn REAL/SYNTHETIC/REPLAY, declaration.

## 9. Hai build direction → tính năng → cảnh demo → bằng chứng

Định nghĩa trên trang thi:
- *Deep Domain AI:* "Build AI that goes deep in a specific field… how work is actually done, not a simplified version of it."
- *Autonomous & Adaptive AI:* "Build agents that can be trusted to operate without constant human oversight… handling the unexpected and staying reliable when real-world conditions change."

| Direction | Tính năng (lane) | Cảnh demo / bằng chứng |
|---|---|---|
| **Deep Domain** | So từng field theo đúng variant/market/version (P1 scope) | Trang brand cho market khác bị loại khỏi scope, có lý do |
| | Nguồn tham chiếu tự mâu thuẫn → "Conflict in source", **không đổ lỗi seller** (P1 R4) | Trang Hydra/CeraVe: title nói da khô, mô tả nói da thường–dầu |
| | Số công bố DAV + công ty chịu trách nhiệm chỉ CONSISTENT khi có hồ sơ công bố ACTIVE (P1 REQ). Thu hồi → STALE (P1) | Event revoke, mô phỏng quyết định của Cục Quản lý Dược ngày 22/06/2026 (thu hồi 286 số công bố; chỉ ghi ngày, không ghi số quyết định) |
| | Claims auditor: free-from so với họ INCI, quy tắc thứ tự INCI ASEAN + trần chất bảo quản 1%, từ ngữ "điều trị" (P2, quy định nằm trong `app/data/*.json` kèm nguồn) | Clear Skin Serum: "không chứa cồn" nhưng có Alcohol Denat., 2% niacinamide đứng sau phenoxyethanol |
| | Nguồn độc lập: listing copy trang brand chỉ tính là 1 nguồn (P1 R7c) | "Stated by brand page only" |
| | Workflow T&S thật: reviewer duyệt đúng một revision, override phải đi qua gate, evidence request gửi seller (P1 + P3) | Reviewer approve; 409 khi revision cũ |
| **Autonomous & Adaptive** | Event-driven: nguồn đổi thì chỉ field phụ thuộc thành STALE rồi tự re-assess, **0 model call** (P1) | Revoke ripple, bộ đếm model call đứng yên |
| | Agent có giới hạn, **code verify bằng anchor** nên đổi verdict mà không cần người (P2), có stop_reason/PARTIAL | Catalogue nhiều size: agent đặt passage không ghi size dưới heading 50 ml → verdict đổi, agent panel hiện trước/sau |
| | Web Scout tự viết query, tự chọn trang. Code kiểm identity và snapshot. Retailer chỉ được xác nhận, không được tố cáo (P2 + P1) | CeraVe thật: tự tìm trang hãng + 2 retailer, có audit panel |
| | Học từ vựng lúc chạy: model đề xuất, code verify, mapping lưu kèm provenance và **chỉ được dùng để xác nhận** (P2) | Sản phẩm có "nghệ" → học được "Curcuma Longa", hiện trên Observe + Why? |
| | Gặp tình huống bất ngờ: injection bị bỏ qua, ảnh mờ → UNREADABLE thay vì bịa, model lỗi → PARTIAL/fallback có nhãn (P2) | Listing chứa injection; ảnh nhãn mờ |
| | Thích ứng với sản phẩm chưa từng thấy (P4 eval) | Blind set tạo trong ngày (mục tiêu 12 sản phẩm nếu kịp; đáp án Codex soạn trước, người duyệt; ghi rõ số ca thực chạy), first-run accuracy, 0 seller bị đổ lỗi sai, metamorphic tests |

Stretch, chỉ làm khi dư giờ (cả hai đều tăng "Autonomous"): **evidence scout agent** (Manager tự chọn bước tiếp theo giữa registry, search, web và request, có `needs_approval`) và **scheduler theo priority** (kiểm tra trước theo rủi ro, không đợi click).

## 10. Thể hiện "Codex leverage" (một trong 4 tiêu chí chấm)

Những thứ phải **làm thật và ghi lại** trong ngày (P4 gom ở mỗi Sync):
1. `AGENTS.md` là luật chung cho mọi thread; `.agent/PLANS.md` cộng 4 ExecPlan sống (`.agent/plans/P1..P4.md`) cho thấy từng lane lập kế hoạch → làm → ghi nhận surprise.
2. **Song song thật:** 4 người × tối đa 2 thread (Local + Worktree). `$self-review` và `$sync-gate` còn gọi subagent `explorer` (built-in, chuyên đọc; nó kế thừa sandbox của thread cha nên skill dặn không sửa file) chạy song song phần soát luật, contract và overfit trong khi thread chính chạy test. Ghi số thread, subagent và task vào CODEX_LOG.
3. **Skills riêng của team:** `$phase-kickoff`, `$self-review`, `$sync-gate`, `$trace-debug`, `$brainstorm`, `$mvp-demo`. Ghi lần dùng nào tạo khác biệt.
4. **`/review` ở mỗi Sync.** `/review` chọn base là branch chứ không phải tag, nên `$sync-gate` tạo branch local `review-base` trỏ vào `sync-<N-1>`. Rule review nằm ở mục `## Code Review Rules` của AGENTS.md; dán cùng nội dung vào app Settings > Code Review. Ghi các finding đã sửa.
5. **Codex fix loop:** test nghiệm thu fail → `$trace-debug` đọc trace → sửa đúng gốc → người duyệt → chạy lại green. Ghi vào CODEX_LOG mục "Notable loops" (đây là cảnh form đã hứa).
6. Số liệu cuối ngày cho write-up: tổng task Codex, accepted/edited/rejected, số test Codex viết, số dòng code, thời gian mỗi milestone.
7. **Plan mode** cho phase effort high (P1-1, P1-2, P2-3, P4-1): `/plan` chỉ đọc, hỏi lại bằng câu hỏi trắc nghiệm, trả plan trong `<proposed_plan>`. Thoát Plan mode rồi `$phase-kickoff` ghi plan vào ExecPlan.

## 11. Rủi ro dự kiến → nơi phòng

Đây là các rủi ro **ước tính lúc lập kế hoạch**, không phải luật cứng. Codex kiểm lại bằng docs chính thức và test, được
chọn cách tốt hơn nếu có bằng chứng, và ghi lại trong ExecPlan.

| Rủi ro dự kiến | Phòng ở |
|---|---|
| Contract không chốt sớm thì các lane đoán lệch nhau; `.env.example` thiếu switch | P4 Phase 0 |
| Model không ổn định: cần fallback + replay từ giờ đầu; replay key phải hash mọi thứ model thấy; không ghi đè recording tốt | P2 Phase 1, 5 |
| Kết quả extraction dao động: prompt cue, effort thấp cho extraction, hỏi lại có giới hạn theo gợi ý của bộ trích luật | P2 Phase 1–2 |
| `output_type` có thể không chạy trên mọi model; số lượt agent phải tính cả lượt submit | P2 Phase 0 (smoke quyết), Phase 3 |
| Smoke và pipeline dựng message khác nhau → dùng một message builder | P2 Phase 0–1 |
| Budget chỉ đếm trong agent thì phần khác vượt trần: cần budget cho cả run, deadline cứng, `PARTIAL` | P2 Phase 2 + P1 Phase 2 + P4 AC-17 |
| Agent đề xuất mà code không kiểm được thì chẳng thêm giá trị → anchor; single call khi còn ít passage | P2 Phase 3 |
| Reasoning token tính vào `max_output_tokens`; effort theo từng step | P2 Phase 1 |
| Override của reviewer lách publish gate | P1 Phase 2 |
| Học từ vựng từ output thô của model | P2 Phase 2 |
| Hash cột thay đổi theo thời gian làm chain báo sai | P1 Phase 2 |
| Buyer UI lẫn với operator UI; không thấy agent đã đổi gì | P3 Phase 1, 3 |
| Embed lúc truy vấn chậm → embed lúc ingest | P2 Phase 3 |
| Port 8000/5173 bị chiếm trước demo/E2E | P4 `sync_check`, Phase 5 |
| Quên bump `POLICY_VERSION`; docs lệch code | P1 mọi phase, Phase 5 |
| Web: lấy nhầm sản phẩm anh em hoặc trang so sánh; nối quote; số call tăng nhanh | P2 Phase 4 |
| Kiểm theo click thay vì theo rủi ro; nguồn tham chiếu lặp theo case | P1 stretch |
| Windows: encoding, `tests/__init__.py`, sửa code bằng heredoc | AGENTS §4 (mọi người) |
| Field notification chỉ CONSISTENT khi có hồ sơ công bố ACTIVE | P1 Phase 1 |
| INCI có viết tắt (Denat., Ext.); dạng pháp lý công ty; skin type có chiều | P2 Phase 1 · P1 Phase 1 |
| Time travel phải tính lại freshness; câu kết luận nên bắt đầu bằng giá trị; đồng thuận ≠ tương thích | P1 Phase 2, 1, 4 |
| Overfit từ vựng/scope; một rule có hai implementation | P2 Phase 1–3, P1 Phase 2, AGENTS rule 14 |
| Nhãn expected do Codex soạn cần một người duyệt; người thứ hai tùy chọn; giá model phải lấy từ pricing page ngày thi | P4 · P2 Phase 0 |

## 12. Setup Codex (mỗi người, xong trước 31/10)

1. Kích hoạt credits theo email OpenAI. Cài **Codex app**, CLI và extension IDE nếu dùng. Đăng nhập.
2. Thêm vào `~/.codex/config.toml` (tên key đã kiểm trên [config reference](https://learn.chatgpt.com/docs/config-file/config-reference) ngày 29/10; sáng 31/10 kiểm lại nhanh):
   ```toml
   model_reasoning_effort = "medium"     # high cho policy/agent; xhigh chỉ khi model hỗ trợ ("available levels depend on the model")
   plan_mode_reasoning_effort = "high"   # Plan mode tự dùng high, khỏi đổi /model tay
   web_search = "live"                   # để agent tra docs mới khi chưa chắc (mặc định chỉ là "cached")
   sandbox_mode = "workspace-write"
   approval_policy = "on-request"

   [sandbox_workspace_write]
   network_access = true                 # cần cho pip/npm install, git fetch/push, smoke.py; record pass vẫn do người chạy

   [windows]
   sandbox = "elevated"                  # fallback cũ, cần admin/UAC một lần lúc setup

   [features]
   prefer_mxc = true                     # docs khuyên MXC (không cần admin); có MXC thì dùng, không có thì về "elevated"

   [tools.web_search]                    # chỉ tra docs chính thức; docs: "cached" giảm rủi ro prompt injection, "live" thì không, kết quả web luôn coi là không tin cậy
   allowed_domains = ["developers.openai.com", "platform.openai.com", "learn.chatgpt.com", "openai.github.io",
     "github.com", "fastapi.tiangolo.com", "docs.pydantic.dev", "react.dev", "vite.dev", "playwright.dev",
     "tailwindcss.com", "docs.python.org", "pypi.org"]
   ```
   Kiểm `codex --version` trước: cần bản mới (0.165.0 trên npm ngày 29/10; bản 0.137.0 báo `unknown variant mxc` và không có `prefer_mxc`). Cập nhật bằng `npm i -g @openai/codex@latest`; nếu vẫn không có `prefer_mxc` thì bỏ khối `[features]`. Sửa `config.toml` xong thì **khởi động lại Codex**, kiểm bằng `/status` và `/debug-config`. Nếu Codex báo lỗi ở khối `[tools.web_search]` (docs chỉ ghi kiểu `allowed_domains = [string]`, không có ví dụ) thì bỏ khối đó. **Thử sandbox trên từng laptop trước 31/10:** trong một thread, chạy `pip --version`, `npm --version`, `git fetch`, và chấp nhận UAC ngay lúc này, không để tới hội trường. Test MXC: `codex -c windows.sandbox=mxc sandbox --include-managed-config --permission-profile :workspace -- cmd.exe /d /c echo MXC_OK`. Đường dẫn home có dấu cách (ví dụ `C:\Users\Nguyen Van A`), nên mọi lệnh có `$HOME` hoặc `$CODEX_HOME` phải bọc nháy kép.
   Tạo thêm `~/.codex/AGENTS.md` trên máy mình. Codex nối file này **trước** AGENTS.md của project. Không commit file này, nhưng có ghi trong declaration:
   ```text
   Lane: P2. Branch: p2 (second thread: p2-b<N>). T+0:00 = 2026-10-31 10:00 ICT; compute T+ from Get-Date, never guess.
   Shell: PowerShell on Windows; join commands with ";" not "&&".
   ```
3. Skills đã được lưu trong repo; nếu muốn dùng bản cài cấp user, chạy từ root checkout:
   ```powershell
   New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
   Copy-Item -Recurse -Force .\_outside-repo\skills\* "$HOME\.agents\skills\"
   ```
   Nếu nhận được file `.skill` (zip của Claude), giải nén thẳng vào thư mục skills. `Expand-Archive` không nhận đuôi `.skill`, còn `tar` có sẵn trên Windows 10+ thì đọc được zip:
   ```powershell
   tar -xf .\MVPDemo.skill -C "$HOME\.agents\skills"      # tạo $HOME\.agents\skills\mvp-demo\SKILL.md
   ```
   CLI/IDE: gõ `/skills` hoặc `$`, phải thấy đủ 6 skill. App: mở **Skills** ở sidebar. Docs chỉ ghi cú pháp `$` cho CLI/IDE, nên thử gõ `$phase-kickoff` trong ô chat của app trước 31/10. Chưa thấy skill thì khởi động lại Codex. `sync-gate` và `phase-kickoff` đã tắt tự kích hoạt (`agents/openai.yaml`), nên phải gọi bằng `$tên`.
4. Python 3.11+ (khuyến nghị 3.13), Node 24, Git. Chuẩn bị sẵn cache wheel và npm nếu mạng hội trường yếu: `pip download openai openai-agents fastapi uvicorn pydantic python-dotenv httpx pytest pillow rapidocr-onnxruntime playwright -d wheels` (chỉ là package OSS).
5. Chọn model Codex: dùng model mặc định của Codex. Đổi effort bằng `/model` hoặc config.

**Cách dùng prompt trong file lane (mỗi phase):**
1. `git fetch --tags; git merge sync-<N-1>`. Phase effort high: có thể mở bằng `/plan` trước (xem §10 mục 7).
2. Mở thread Codex mới ở root repo, gõ `$phase-kickoff P<k> <N>`. Skill đọc section phase và nhịp lane, cập nhật ExecPlan rồi chạy "Prompt chính". Với P1/P2/P4 ở Phase 1–4, lượt đầu chỉ làm checkpoint contract rồi dừng theo §4; người dùng nhắn tiếp tục sau mini-sync để làm phần còn lại. Nếu không dùng skill thì **dán nguyên khối "Prompt chính"**, gồm cả CONTRACT CHECKPOINT.
3. Trong lúc Codex chạy, đọc diff, trả lời câu hỏi, bấm Action `backend`/`frontend` để chạy app thử. Thread thứ 2 (Worktree, xem §4) dùng cho "Prompt phụ" hoặc test.
4. T−20: gõ `$self-review` → sửa → commit → push trước T−10 (hạn chót T−8). Push commit contract lúc T+20 chỉ cần pytest và `test_guards.py`.

## 13. Skills (folder `skills/`; trong pack là `_outside-repo/skills/`)

| Skill | Ai dùng | Khi nào |
|---|---|---|
| `phase-kickoff` | P1–P4 | Nạp phase, cập nhật ExecPlan, kiểm contract; P1/P2/P4 Phase 1–4 push checkpoint rồi dừng, người dùng nhắn tiếp tục để làm phần còn lại |
| `self-review` | P1–P4 | Trước khi push ở mỗi Sync: test/build, quét hardcode/overfit/từ cấm, kiểm contract, ExecPlan, dòng CODEX_LOG, CCR |
| `sync-gate` | P4 | T+20 (mini-sync contract) và T−10 mỗi phase: merge theo thứ tự, test của phase, `sync_check`, `/review` với base `review-base`, tag, DEVLOG. Chỉ gọi bằng `$sync-gate` |
| `trace-debug` | P1–P4 | Verdict sai hoặc test fail: đọc trace/explain, tìm step gây sai, viết test tái hiện, sửa đúng gốc. Đồng thời là "Codex fix loop" để kể trong write-up |
| `brainstorm` | cả team | Lane xong sớm, bị kẹt, chọn stretch, chuẩn bị pitch/Q&A: liệt kê phương án, chấm theo tiêu chí thi + 2 direction + thời gian còn lại, chưa code. Nên chạy trong Plan mode (`/plan`), vì Plan mode chỉ đọc |
| `mvp-demo` | P4 + P3 | Storyboard + callout/timing, `narration.json={}` (P4, Phase 3–4) → quay segment bằng Playwright với `--engine none` (P3-5b) → ghép ffmpeg, kiểm, upload (P4, Phase 6). Giọng/TTS chỉ khi yêu cầu. Có `references/passport-storyboard.md` |

**Codex skill so với Claude skill:**

| | Codex | Claude |
|---|---|---|
| Định dạng | Thư mục chứa `SKILL.md` (frontmatter bắt buộc `name`, `description`), thêm tùy chọn `scripts/`, `references/`, `assets/`, `agents/openai.yaml` | Cùng chuẩn `SKILL.md`. Frontmatter có thêm vài field riêng của Claude |
| Vị trí | Repo: `.agents/skills/` (quét từ thư mục hiện tại lên root). User: `~/.agents/skills/`. Admin: `/etc/codex/skills` | Claude Code: `.claude/skills/`, `~/.claude/skills/`. claude.ai: upload file `.skill` |
| File `.skill` (zip) | **Không đọc được.** Đã kiểm tra source ngày 29/10: `codex-rs/ext/skills/src/host_roots.rs` chỉ nhận root là thư mục, `loader/discovery.rs` chỉ nhận file tên `SKILL.md`. Phải giải nén thành thư mục (đã làm cho `mvp-demo`). `$skill-installer` cài từ GitHub repo/URL, không cài từ zip | Là định dạng đóng gói để upload lên claude.ai (thực chất là file zip) |
| Thư mục user cũ | `~/.codex/skills` (`$CODEX_HOME/skills`) vẫn được đọc nhưng source ghi là *deprecated*. Dùng `~/.agents/skills` | — |
| Gọi | `$tên` hoặc `/skills`. Tự kích hoạt khi task khớp `description` (tắt được bằng `policy.allow_implicit_invocation: false` trong `agents/openai.yaml`) | `/tên` hoặc tự kích hoạt |
| Ngân sách | Danh sách skill chiếm khoảng 2% context (`skills.max_context_tokens`), nên description phải ngắn và nêu đúng trigger | tương tự |

Nguồn: [Codex skills](https://developers.openai.com/codex/skills), [Codex best practices](https://learn.chatgpt.com/docs/learn/best-practices), [Codex Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide), [ExecPlans](https://developers.openai.com/cookbook/articles/codex_exec_plans), [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## 14. Checklist

**Trước 31/10 (P4 điều phối):**
- [ ] Mỗi người đã kích hoạt credits, cài Codex app, sửa config, cài 6 skill, thấy chúng trong `/skills`.
- [ ] Mỗi người đã đọc README §1–§8 + file lane của mình + `AGENTS.contest.md`.
- [ ] **Không mang dataset.** Cả đội đọc `docs/DATASET-SPEC.md` (case synthetic sinh ngày thi, case thật capture ngày thi, blind set Codex soạn và P4 điều phối duyệt). Mở thử các URL thật ở §3 và ghi lại URL nào còn sống.
- [ ] Chỉ định một người duyệt gold Codex soạn theo lô trong ngày (AGENTS rule 11); người thứ hai hỗ trợ ca khó nếu rảnh. Nhãn chưa duyệt vẫn DRAFT và báo số liệu riêng.
- [ ] Repo `seaxopenai_hcpus` đã có một commit init gồm toàn bộ pack: docs, prompt, template và 6 skill/demo kit trong `_outside-repo/`; **không có application implementation hay dataset**. Cách dùng: `README-PACK.md` ở root.
- [ ] Cả nhóm truy cập được `https://github.com/thphuc06/seaxopenai_hcpus.git`; P4 không cần tạo repo/copy pack lại trong ngày thi.
- [ ] Xem lại số liệu pitch (DEVLOG 26/10: 896 khiếu nại, TMĐT 21,3%, 9,2% thông tin không đầy đủ/không chính xác; quyết định ngày 22/06/2026 (chỉ ghi ngày); **không** trích Luật 122/2025 Điều 17 như "platform phải kiểm duyệt", vì câu đó chưa xác nhận được).

**Sáng 31/10 (trước 10:00):** đủ pin laptop, sạc, hotspot dự phòng · mở sẵn file lane · thử `codex` và `/skills` · ports 8000/5173 trống · venv + `npm ci` (nếu được phép chuẩn bị môi trường; code thì chưa được viết) · Chromium cho Playwright đã cài trước bằng một venv thử (`python -m playwright install chromium`); ngày thi nếu playwright báo thiếu browser thì cài lại (cần mạng).
