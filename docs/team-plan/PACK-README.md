# Pack đã khởi tạo — seaxopenai_hcpus

Repo này được P4 khởi tạo trước ngày thi bằng toàn bộ `open-ai-pack`: **tài liệu, prompt, template và đủ 6 skill**,
kể cả demo kit trong `_outside-repo/skills/mvp-demo`. Đây là công cụ setup chuẩn bị trước, không phải code ứng dụng
backend/frontend. Chưa có implementation ứng dụng, dataset, gold hay recordings. Các phần đó được làm trong ngày thi
theo `docs/DATASET-SPEC.md`. Commit init phải được khai là prepared materials; không mang lịch sử/code của repo rehearsal sang.

## Cái gì đi đâu

| Trong pack | Đi vào | Ghi chú |
|---|---|---|
| `AGENTS.md` | root repo thi | Codex tự nạp vào mọi task. Ngắn, bắt agent tự đọc file theo bảng "Read before you write" |
| `.agent/PLANS.md` | root repo thi | Template ExecPlan. Mỗi lane tạo `.agent/plans/P<n>.md` ở Phase 0 |
| `.gitignore` | root repo thi | Chặn `backend/.env`, `*.db`, `.venv`, `node_modules` ngay từ commit đầu |
| `solution.md` | root repo thi | Spec thiết kế v0.3 (VI). Các docs link tới `../solution.md` |
| `docs/PROPOSAL.md` | repo | Proposal (EN): problem, stakeholders, US, FR, BR, NFR, AC, solution, direction, architecture, stack, data, eval, risk, scope, câu hỏi mở. **Tinh chỉnh tại đây** |
| `docs/requirements-fr-br-ac.vi.md` | repo | Bộ yêu cầu chi tiết (VI): FR, BR, AC, use case UC-01…14 |
| `docs/01, 03–07, 09-*.md` | repo | Spec: problem brief, architecture, data model, contracts, policy rules, AI integration, eval plan. 04/05/06 là bắt buộc theo |
| `docs/pitch/fact-check.md` | repo | Số liệu pitch cần kiểm lại |
| `docs/team-plan/` | repo | README (lịch 7 phase, ownership, contract), **P1–P4 (prompt từng phase)**, SUBMISSION, bản gốc AGENTS/PLANS |
| `docs/DATASET-SPEC.md` | repo | **Đặc tả dataset**, không phải dataset. Fixture và data được Codex sinh hoặc capture **trong ngày** theo prompt P4-0c, P4-1c, P4-2b, P4-3, P2-1/2/4. Expected answers do người viết trước khi chạy |
| `_outside-repo/skills/` | Giữ nguyên trong repo; có thể cài vào **`~/.agents/skills/`** trên từng máy | Đủ 6 skill và demo kit, được commit như công cụ setup chuẩn bị trước. Tên thư mục phân biệt với code ứng dụng; khai đúng trong declaration |

## Repo đã chuẩn bị — không lặp lại bước tạo repo/copy pack

P4 đã import pack và push **một commit init** vào `main` của repo sau. Chỉ clone nếu máy chưa có checkout:
```powershell
git clone https://github.com/thphuc06/seaxopenai_hcpus.git
cd seaxopenai_hcpus
```
Nếu đã clone: cập nhật `main` sạch bằng `git pull --ff-only`. Không `git init` lại, copy pack lại, đổi tên nhánh hay tạo
thêm commit "prepared materials" vào sáng 31/10. Nội dung pack đã nằm trực tiếp ở root; không có lớp thư mục
`open-ai-pack/` bên ngoài.

**Ngày thi từ 10:00:** bắt đầu đúng prompt Phase 0. P1–P3 tạo branch của mình; P4 làm trên `main` và tạo `p4` sau S0.
Repo mới chỉ được chuẩn bị nội dung; skeleton, venv và dependencies ứng dụng chưa được dựng. Các lệnh môi trường dưới
đây chỉ dành cho ngày thi; sau S0 dùng `scripts\dev\setup_worktree.ps1` của P4:
```powershell
git switch -c p2; git push -u origin p2                     # thay p2 bằng lane của bạn (P1–P3)
py -3 -m venv backend\.venv                                 # Python >= 3.11
backend\.venv\Scripts\python -m pip install openai openai-agents fastapi uvicorn pydantic python-dotenv httpx pytest pillow   # mạng yếu: thêm --find-links <thư mục wheels>
Set-Content backend\.env "OPENAI_API_KEY=<key của bạn>"      # gitignored
```

Sau đó P4 chạy Prompt P4-0 (`docs/team-plan/P4-integrator.md`), các lane bắt đầu Phase 0 theo file của mình.

## Cài skills (mỗi người, trước 31/10)
```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
Copy-Item -Recurse -Force ".\_outside-repo\skills\*" "$HOME\.agents\skills\"
```
Gõ `/skills` trong Codex, phải thấy đủ: `phase-kickoff`, `self-review`, `sync-gate`, `trace-debug`, `brainstorm`, `mvp-demo`.

## Prompt ở đâu

| Ai | File | Dùng thế nào |
|---|---|---|
| P1 Backend core | `docs/team-plan/P1-backend-core.md` | Mỗi phase có một "Prompt chính" và một "Prompt phụ". Gõ `$phase-kickoff P1 <N>`, hoặc dán nguyên khối prompt |
| P2 AI | `docs/team-plan/P2-ai-agents.md` | như trên |
| P3 Frontend | `docs/team-plan/P3-frontend.md` | như trên |
| P4 Integrator | `docs/team-plan/P4-integrator.md` | như trên, cộng `$sync-gate <N>` ở mỗi Sync |
| Cả đội | `docs/team-plan/README.md` | Lịch, hợp đồng giữa các lane, luật cắt scope, map 2 direction |

## Trước khi dùng pack (P4 kiểm)
- [ ] Đã đọc `docs/DATASET-SPEC.md` và mở thử các URL thật ở §3 (CeraVe Hydrating/Foaming/Blemish, La Roche-Posay Effaclar). Ghi lại URL nào còn sống. Pack không chứa dataset; mọi fixture được tạo trong ngày.
- [ ] Đã chỉ định 2 người soát gold **trong ngày** (gold chỉ được viết trong ngày).
- [ ] `docs/pitch/fact-check.md` đã điền. Đã trả lời các câu hỏi mở OQ-1…10 trong `docs/PROPOSAL.md` §16.
- [ ] Mở `AGENTS.md`, đọc lại 5 phút. Đây là luật Codex sẽ tuân theo cả ngày.
- [ ] Declaration (`docs/team-plan/SUBMISSION.md`) liệt kê đúng những gì có trong pack.
