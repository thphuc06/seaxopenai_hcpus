# Gói nộp bài — template (P4 điền ở Phase 6, nộp trước 16:45)

Nộp 4 thứ: **GitHub repo** · **project write-up** · **demo link** · **declaration**. Template viết bằng tiếng Anh vì giám khảo đọc tiếng Anh. Có thể kèm một bản tóm tắt tiếng Việt nếu form cho phép.

Nguyên tắc: **mọi con số phải có nguồn trong repo** (`docs/results/*`, `docs/tracking/CODEX_LOG.md`, git log). Số nào chưa đo được thì ghi "not measured" chứ không đoán. Không dùng câu nào hàm ý xác thực hàng thật hay an toàn (AGENTS rule 1).

## 0. Checklist (P4, 16:30–16:45)

- [ ] Repo truy cập được (public nếu thể lệ yêu cầu). Có README, `docs/SUBMISSION.md`, `docs/results/*`, `docs/tracking/CODEX_LOG.md`, `.agent/plans/*`.
- [ ] `git ls-files | Select-String '(^|/)\.env$'` ra rỗng. Không có key trong lịch sử commit. Skills/demo kit nằm riêng trong `_outside-repo/skills`, được khai là công cụ setup chuẩn bị trước.
- [ ] Commit đầu tiên là init prepared materials (đặc tả, plan, prompt, AGENTS và đầy đủ skills/demo kit; không có dataset/application implementation). Chỉ các commit application code dưới backend/, frontend/, scripts/ được đối chiếu với khung 10:00–17:00 ngày 31/10.
- [ ] Demo link mở được ở cửa sổ ẩn danh. Độ dài video đúng giới hạn. Mô tả video có ghi chú trung thực.
- [ ] Write-up có đủ problem, solution, build directions, cách dùng Codex.
- [ ] Declaration có đủ phần chuẩn bị trước, OSS kèm license, personal tools, và phần build trong ngày.
- [ ] Đã nộp form, chụp màn hình xác nhận và gửi vào nhóm chat.

---

## 1. Project write-up (template)

```markdown
# Product Truth Passport — field-level evidence for cosmetics listings

## Problem
Cosmetics buyers and marketplace Trust & Safety teams need to know, for each product detail (volume, skin type, key
ingredients, cosmetic notification number, responsible company), whether it is supported by the right source for the
exact product version — and whether that is still true today. Seller badges and ratings do not answer this per field.
- Official sources contradict themselves: in our 19/09/2026 audit (re-read 21/09), a brand's Vietnamese product page
  for a hydrating cleanser said "dry skin" in its title/highlights while its description described a foaming cleanser
  for normal-to-oily skin and mentioned niacinamide, which is absent from the page's own ingredient list. A naive
  "listing vs brand page" check blames an accurate seller.
- Checks go stale: a Drug Administration of Vietnam decision dated 22/06/2026 withdrew 286 cosmetic notification numbers from 21 companies
  (administrative, at the companies' request).
- Pressure on platforms: Vietnam's consumer-protection authority received 896 complaints in 2025, 191 (21.3%) about
  e-commerce; 9.2% of cases concerned incomplete or inaccurate information. <source links from docs/pitch/fact-check.md>

## Solution
For each field, the Passport compares the listing with the brand page, packaging label, notification document and
pages found on the web — scoped to the same variant, market and version — and publishes a finding with a verbatim,
locator-checked citation and the time of the last check: Consistent · Single source · Conflict in source (not the
seller's fault) · Conflicting (to a reviewer) · Not verified · Stale. It never certifies authenticity or safety.
Design choices: the model extracts claims, versioned code rules decide; reference sources are checked for
self-contradiction before a listing is judged; a source event (revocation, page change) stales only the dependent fields
and triggers re-assessment; buyers' reads never call a model; anything that reflects on a seller goes to a human.

## Build directions
**Deep Domain AI** — <3–5 bullets with evidence, e.g. notification-document requirement and revocation; ASEAN INCI
descending-order rule + 1% preservative caps from a cited data file; free-from claims vs INCI families; treatment-claim
wording; variant/market scope; source independence (copied text counts once); reviewer workflow bound to one revision.>
**Autonomous & Adaptive AI** — <3–5 bullets with evidence, e.g. event-driven re-assessment with 0 model calls to mark
stale; a bounded agent whose scope placements are verified by code through an anchor passage (changed N verdicts without
a reviewer in <set>); a Web Scout agent that finds and snapshots real sources with identity checks; a vocabulary learned
at run time that may confirm but never accuse; hard per-run budget with PARTIAL + stop reasons; results on N unseen
products (blind sets): <x/y fields, z sellers wrongly blamed>.>

## How it works
<mermaid or 6-line pipeline from README; one line per module group; link docs/03-architecture.md>

## How Codex was utilised
- Team of 4, three parallel lanes + one integrator; every lane ran Codex in up to 2 parallel threads/worktrees.
- Shared AGENTS.md (product rules + known risks) and living ExecPlans per lane
  (.agent/plans/P1–P4.md) — each phase started from a plan and ended with outcomes and surprises.
- Team skills: $phase-kickoff, $self-review, $sync-gate, $trace-debug, $brainstorm, $mvp-demo (<n> invocations).
- /review on every sync diff: <n findings, n fixed>.
- Codex fix loop: <the notable loop from CODEX_LOG: failing acceptance test → trace inspected → root-cause fix →
  human approval → green>.
- Numbers: <N> Codex tasks (<a> accepted, <e> edited, <r> rejected), <T> tests written, <C> commits; where Codex was
  wrong and how we caught it: <1–2 examples>.
- Evidence table (from CODEX_LOG and git, 5–8 rows across lanes, at least one where Codex was wrong):
  | task | what Codex produced | what a human changed | test | commit |

## Results (measured on <date>, mode <replay/record>, gold labels <reviewed by …/draft>)
| | Candidate | B0 rules | B1 single LLM |
|---|---|---|---|
| Fields correct (demo story) | | | |
| Sellers wrongly blamed | | | |
| Abstentions where evidence is missing | | | |
| Blind sets (unseen products) | | – | – |
| Citations verbatim / judge recall-precision | | – | – |
| Model calls / tokens / cost per case | | | |

## Limits (honest)
Synthetic products are labelled SYNTHETIC; the notification registry is a labelled mock; evaluation sets are small and
not marketplace-wide; <gold status>; web results change daily (stage demo replays the recorded pages); claim rules are a
demo subset needing legal review per market.

## What's next
Batch scheduler with risk priority; product-level reference store; real registry/brand connectors under agreement;
human-written holdout set.
```

---

## 2. Declaration (template)

```markdown
# Declaration

## Built during the hackathon (31 Oct 2026, 10:00–17:00)
Application implementation — backend (`backend/app/**`), tests (`backend/tests/**`), frontend (`frontend/**`)
and application scripts (`scripts/**`) — was written during the hacking window by the team with Codex <verify before
submission>. Evidence: git history filtered to those paths (first code commit <time>, last <time>),
docs/tracking/CODEX_LOG.md, .agent/plans/*. The prepared tools below are excluded from this application-code statement.

## Prepared before the event (no application code)
- Problem research and design documents: problem statement, proposal, requirements, data model, contracts and policy
  rules (`solution.md`, `docs/`), plus a dataset specification (`docs/DATASET-SPEC.md`) describing the test cases and
  the public product pages chosen for the demo. The page contents themselves were captured on the day.
- Team process: `AGENTS.md`, the ExecPlan template, the phase plan and the Codex prompts (`docs/team-plan/`).
- Initial repository preparation on 30 Oct 2026: documents, prompts, templates and all six skill bundles, including the
  pre-existing demo-video kit under `_outside-repo/skills/mvp-demo`. This init did not create application code or datasets.
- Before the event we tested the feasibility of the idea in a separate, private prototype. No application code, data, recordings
  or test fixtures from it are included in this repository; what we carried over are written lessons and design notes.

## Prepared personal tools (tracked separately from application code)
- Codex skills written by the team (workflow instructions): phase-kickoff, self-review, sync-gate, trace-debug,
  brainstorm.
- `mvp-demo`: a pre-existing personal demo-video kit (Playwright + ffmpeg; silent by default, TTS only if later requested),
  tracked under `_outside-repo/skills/mvp-demo` in the init commit. `scripts/demo/record_demo.py` (written on the day)
  imports that kit or its user-installed copy; do not describe the kit itself as built during the event.
- Per-machine Codex settings (`~/.codex/config.toml`, `~/.codex/AGENTS.md`), not committed.

## Open-source software and services
| Component | License (from installed package metadata) |
|---|---|
| FastAPI, Uvicorn, Pydantic, httpx, pytest | <fill from `pip show`> |
| openai (Python SDK), openai-agents | <fill> |
| RapidOCR (onnxruntime), Pillow | <fill> |
| React, React Router, Vite, TypeScript | <fill from `npm ls` / package.json> |
| Playwright, imageio-ffmpeg (video only; add a speech engine only if actually used) | <fill> |
| OpenAI API (models: <ids>), OpenAI web search tool | service |
| Open Beauty Facts data | ODbL |
```

Lệnh lấy license thật (không đoán):
```powershell
cd backend; .venv/Scripts/python -c "import importlib.metadata as m; [print(p, '|', (m.metadata(p).get('License-Expression') or m.metadata(p).get('License') or '?')[:60]) for p in ['fastapi','uvicorn','pydantic','httpx','pytest','openai','openai-agents','rapidocr-onnxruntime','pillow']]"
cd ../frontend; npm ls --depth=0; Get-Content node_modules/react/package.json | Select-String '"license"'
# Run with the personal video venv (not necessarily the app backend venv):
& "$HOME\.agents\tools\mvp-demo\.venv\Scripts\python.exe" -c "import importlib.metadata as m; [print(p, '|', (m.metadata(p).get('License-Expression') or m.metadata(p).get('License') or '?')[:60]) for p in ['playwright','imageio-ffmpeg']]"
```

---

## 3. Mô tả video demo (dán vào YouTube/Drive)

```text
Product Truth Passport — 3-minute demo (Sea × OpenAI Codex Hackathon, Vietnam, 31 Oct 2026).
Recorded from the running app in replay mode (recorded model outputs, labelled REPLAY on screen); waits are
fast-forwarded and marked; nothing in the AI outputs was edited. Voice: none (silent demo; update only if a voice was actually added). Synthetic products are
labelled SYNTHETIC; the registry is a mock. Numbers on screen: <list with source and date>.
Repo: <link>
```

## 4. Câu trả lời một dòng cho form (nếu có)

- **Direction(s):** Deep Domain AI (primary), Autonomous & Adaptive AI.
- **One-liner:** "Per-field, cited, self-updating evidence for cosmetics listings: the model extracts, code decides, and a source change re-checks only what depended on it."
