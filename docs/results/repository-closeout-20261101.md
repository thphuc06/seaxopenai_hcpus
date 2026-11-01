# Hoàn thiện repo sau cuộc thi — 1 November 2026

Đội xác nhận đã nộp bài. Tài liệu này kiểm kê repo sau `sync-5`, không thay thế hồ sơ đã nộp và không ghi nhận công việc1November như đã hoàn thành trong ngày thi. Điểm bắt đầu: `6f6e7ea` trên `p3`; `sync-5`/`freeze` trỏ tới `d46a1d6`. Giữ nguyên5 field, policy, API contract, PHASE=5, gold DRAFT và các recording cũ.

## Vai trò Phase6 của từng P và kết quả kiểm tra

| Lane | Trách nhiệm theo plan | Kết quả trong repo |
|---|---|---|
| P1 | Architecture & policy ≤150 từ; kiểm hướng dẫn cài/chạy; sửa blocker | Đoạn giải thích có bằng chứng bên dưới. Đã sửa README bảo toàn .env, dùng đúng phase và hướng dẫn khi launcher/port không hoạt động. Cài dependency trong venv mới và boot replay bằng DB tạm thành công; không phải kiểm toàn bộ demo trên máy mới. |
| P2 | AI design ≤150 từ; số liệu Codex/fix loops; nêu kết quả và chi phí thực đo | Đoạn AI bên dưới, số liệu có nguồn, hai vòng sửa lỗi từ ExecPlan. Full-story replay và lợi ích agent trên provider chưa được chứng minh đầy đủ. |
| P3 | Screenshot và sửa lỗi UI chặn demo |7 ảnh thật đã bàn giao, có [manifest](screens/README.md). Hai cảnh within-source conflict và agent before/after chưa đủ bằng chứng; không dùng ảnh thay thế để tuyên bố đạt milestone. Không có UI mới trong lượt bảo trì này. |
| P4 | Tích hợp, CI, video, write-up/declaration và nộp | Đội đã nộp theo xác nhận người dùng. Giữ video/tài liệu thi; sửa cấu hình CI, cập nhật tracking và bàn giao PR cho main. Không tạo lại form, upload hoặc tag submit. |

Nguồn phân việc: [P1](../team-plan/P1-backend-core.md), [P2](../team-plan/P2-ai-agents.md), [P3](../team-plan/P3-frontend.md), [P4](../team-plan/P4-integrator.md). Người dùng giao rõ việc hoàn thiện repo của cả bốn lane; thay đổi shared docs/CI trong lượt này nằm trong phạm vi đó.

## P1 — Architecture & policy

Operator events enter admission checks for role, idempotency and case revision. Material source changes stale only dependent findings. A worker pins the revision and runs extraction within one shared budget. Versioned code policy evaluates scope, independent sources and conflicting evidence; the publish gate checks stored citations and rejects outdated runs. Published findings retain their decision trail and hash-chain history. Reviewer decisions bind to a result and revision. Buyer reads return stored findings without starting a job or model call. This describes the checked sources, not the product's physical properties.

Bằng chứng: [admission](../../backend/app/events/), [run](../../backend/app/pipeline/run.py), [policy](../../backend/app/pipeline/policy.py), [publish](../../backend/app/pipeline/publish.py), [chain](../../backend/app/chain.py); tests [events](../../backend/tests/test_events.py), [staleness](../../backend/tests/test_staleness.py), [publish](../../backend/tests/test_publish.py), [reviews](../../backend/tests/test_reviews.py), [chain](../../backend/tests/test_chain.py), [acceptance](../../backend/tests/test_acceptance.py).

Kiểm setup: `py -3.12` trên máy này trả “No installed Python found”; dùng Python3.12.13 đã có để tạo venv riêng trong cache. Cài toàn bộ `backend/requirements.txt` và `pip check` thành công. `TestClient` với `LLM_MODE=replay`, khóa API rỗng, network guard và DB tạm: health200, OpenAPI200, danh sách8 sản phẩm200,0 provider call. Đây là fresh-venv backend startup, không phải fresh OS, cài mới frontend hay full replay. `.env` và DB Local đang chạy không đổi.

## P2 — AI design

Typed model output supplies extracted claims and proposals. Code validates quoted passages, applies normalization and decides publication. A shared run budget counts model, tool and web activity; exhausted or missing replay work remains PARTIAL with its stop reason. Scope agents propose passage placements that code checks against stored anchors. Learned vocabulary helpers retain provenance and can confirm, never accuse; their general runtime hook remains a follow-up. Web discovery records queries, checks identity and stores versioned snapshots before policy evaluation. Offline tests exercise these mechanisms; incomplete recordings prevent a full provider-replay or agent-effect claim. Measured bootstrap recording used4 calls and an estimated USD0.028166; the partial Foaming path used13 model/search calls and USD0.213180, including2 searches.

Bằng chứng: [AI As built và bảng chi phí31October](../07-ai-integration.md), [client](../../backend/app/llm/client.py), [budget](../../backend/app/budget.py), [canon](../../backend/app/pipeline/canon.py), [agent tests](../../backend/tests/test_agent_scope.py), [web pipeline](../../backend/app/pipeline/web_sources.py). Các chi phí trên là ước tính theo usage đã ghi; không phải tổng hóa đơn tài khoản hoặc chi phí của lượt bảo trì này. Lượt này không gọi provider.

Số liệu Codex: [bản đếm mới](codex-usage-20261101.md) dùng HEAD6f6e7ea và bảng CODEX_LOG tại thời điểm chạy; giữ nguyên [bản thi cũ](codex-usage.md). Đây là số **receipt được ghi**, không phải tổng task/thread/người hay tỷ lệ năng suất. Bản đếm trước lượt closeout có P1=12, P2=7, P3=15, P4=27 receipt; P2 gồm4 accepted,3 edited,0 rejected. Một số lượt sau chỉ có trong ExecPlan nên bảng trung tâm không đại diện toàn bộ hoạt động.

Hai ví dụ sửa lỗi P2 có bằng chứng trong [ExecPlan Phase5](../../.agent/plans/P2.md) và [image-count/reuse tests](../../backend/tests/test_record_image_counts.py):

1. Preflight đếm token ảnh chịu ảnh hưởng mode ambient; sửa để thao tác record đã được cho phép dùng đúng mode, còn replay/freeze không gọi endpoint đếm. Các biến thể giữ ràng buộc model/detail/content.
2. Continuation tự nhập recording cũ dù không truyền thư mục, gây2 lỗi trong lượt49 test. Sửa chỉ nhập khi caller cung cấp thư mục rõ ràng; receipt cuối19 test liên quan pass. Các lượt56/13/19 có chồng lặp, không cộng lại. Lượt full replay đã dừng trước summary vẫn là NOT VERIFIED.

Đây là lỗi triển khai được ghi lại và bắt bởi test/review; không suy ra số lần chat hoặc lỗi riêng của model từ Git.

## Sửa lỗi CI và hướng dẫn chạy

CI tại [commit6f6e7ea](https://github.com/thphuc06/seaxopenai_hcpus/actions/runs/41301874427) có JUnit1667 test,1 failure,0 error/skip. Failure duy nhất là `test_dollar_cap_blocks_hosted_provider_and_fetch_failure_keeps_reservation`: `MODEL_PRICE_NOT_REVIEWED`. Test cần model có trong price book để tính mức giữ chỗ trước khi kiểm dollar cap; CI bỏ trống `MODEL_AGENT`. Tái hiện local cũng lỗi đúng node này.

[Workflow](../../.github/workflows/ci.yml) nay đặt `MODEL_AGENT=gpt-6.1-sol`, dùng entry đã có trong price book cho test offline. Không thay test, dữ liệu, ngân sách hoặc nhánh quyết định. README dùng cùng cấu hình và đọc `backend/tests/PHASE`, không hardcode phase4. Không thay model/runtime của server Local.

[Local Actions](../../.codex/environments/environment.toml) cũng được đồng bộ: frontend dùng API thật; tests dùng phase đã công bố và cấu hình offline; sync_check gọi story4 mà script hỗ trợ, in rõ giới hạn và vẫn giữ CONTEST_PHASE=5. Đây là sửa lệnh gọi CLI không hợp lệ, không hạ gate. Đã đọc [OpenAI Docs về Local environments](https://learn.chatgpt.com/docs/environments/local-environment), giữ cấu trúc version1 có sẵn và parse TOML thành công. Chưa kiểm nút trên UI desktop; đã chạy đúng nội dung command của Action trong PowerShell.

| Kiểm tra mới1November | Kết quả / giới hạn |
|---|---|
| Full backend, mọi P3 wire contract và Render adapter |1671 passed và2 subtests passed;0 failure/error/skip/deselect, PHASE5,291.12s. JUnit local: backend/.venv/repo-closeout.xml. |
| Node frontend |95 passed;0 failed/skipped/cancelled. Node24.18.1 local. |
| Sites proxy |9 passed;0 failed/skipped/cancelled; offline. |
| API build |PASS; hai cảnh báo `use client` hiện có từ React Router. |
| Static hosting với dist thật |5 SPA routes và2 JS/CSS assets200, đúng bytes; unknown API, missing asset và đường dẫn .env404. Không khởi động lifespan hoặc thay DB. |
| Fixtures |101 checked;0 failed. |
| Local sync_check Action |36 PASS,0 FAIL/SKIP ở FALLBACK, DB tạm; story1–4, CONTEST_PHASE vẫn5. Không chứng minh provider replay hoặc live web discovery. |
| Dependency/setup |Cả venv đang dùng và venv mới `pip check` PASS; replay startup/read smoke PASS như mô tả ở P1. |
| Hosted GitHub CI sau sửa |Commit98fe48b: cả [PR run](https://github.com/thphuc06/seaxopenai_hcpus/actions/runs/41302925307) và [push run](https://github.com/thphuc06/seaxopenai_hcpus/actions/runs/41302921327) SUCCESS; Backend/contracts, Frontend/build và Render image đều SUCCESS. Đây là build/check image trên CI, không phải redeploy dịch vụ. |

Lệnh kiểm full từ `backend/` sau khi đặt biến môi trường offline trong README, thêm `DEMO_RUN_DELAY_S=0`:

```powershell
.venv/Scripts/python.exe -m pytest -q tests ../frontend/tests/test_backend_contract.py ../frontend/tests/test_s1_contract.py ../frontend/tests/test_s2_contract.py ../frontend/tests/test_s3_contract.py ../frontend/tests/test_s4_contract.py ../scripts/dev/render/tests -rs --tb=short -p no:cacheprovider --junitxml=.venv/repo-closeout.xml
```

Full suite local dùng Python3.12.13; CI dùng Python3.11/Ubuntu. Các kết quả khác môi trường được ghi riêng. Không reset/chạy E2E trên DB dùng chung, không live call hoặc quay lại video.

## Phần còn lại và thứ tự nên làm

1. **P1/P2/P4 — replay:** điều tra divergence event06 bằng trace, xác định recording nào thiếu hoặc không còn khớp schema/prompt/input. Chỉ thêm recording khi có ngân sách và scope riêng; không sửa key/file cũ hoặc gold để đổi kết quả. Sau đó chạy lại sync story và cảnh agent thực sự có proposal → code-accepted placement → effect.
2. **P1/P4 — API ngoài scope demo:** source-image GET, eval-metrics GET và run-OTel GET còn501. Eval CLI và trace view đã có không chứng minh ba endpoint này hoàn chỉnh. Fresh-image grounding và migration DB cũ cần thiết kế/test riêng.
3. **P3 — phần trình bày còn thiếu:** nối pending-claim count đã có trong backend, làm rõ Buyer Why bằng citation thật, origin/mode trong reviewer, rồi bổ sung hai cảnh screenshot còn thiếu khi backend/replay đủ bằng chứng.
4. **P2/P4 — đánh giá:** runtime canon hook, provider hybrid retrieval, blind replay và gold human review vẫn chưa hoàn tất. Giữ DRAFT và báo kết quả sơ bộ; không dùng số diagnostic như điểm chất lượng đã duyệt.
5. **P4 — vận hành:** tích hợp PR sau CI; kiểm Render/Sites và migration trên môi trường triển khai trước lần phát hành tiếp theo. Không suy ra dịch vụ live hoạt động từ test hosting wrapper. Video/form đã nộp theo xác nhận đội, bản nhận nộp không có trong checkout.

Các giới hạn này là backlog công khai, không phải các tính năng đã hoàn tất. [ISSUES](../tracking/ISSUES.md) giữ owner và lịch sử; [HANDOFF sync-5](../tracking/HANDOFF.md) giữ nguyên phạm vi đã được chấp nhận. Việc bảo trì lần này kết thúc khi cấu hình CI, setup, tài liệu và bàn giao repo đã được kiểm chứng; không tuyên bố toàn bộ backlog hoặc full replay đã hoàn thành.

Self-review: ba reviewer chỉ đọc đã kiểm rules/privacy, contracts/setup và overfitting/evidence. Đã sửa lệnh tạo usage report để luôn truyền `--output` tới tên mới, tránh ghi đè báo cáo thi. Sau lượt kiểm cuối không còn finding P0/P1/P2 trong phạm vi thay đổi. PR giữ ranh giới giữa kết quả offline mới, artifact cũ và giới hạn provider.

Bàn giao: commit98fe48b đã push lên `origin/p3`, SHA remote khớp, [PR19](https://github.com/thphuc06/seaxopenai_hcpus/pull/19) đã cập nhật đúng phạm vi mới và không có merge conflict tại thời điểm kiểm tra. P4 vẫn sở hữu bước tích hợp vào main. Các commit bổ sung receipt sau đó chỉ cập nhật tài liệu; xem GitHub checks của HEAD để biết trạng thái riêng của chúng.
