# P4-2b — capture and draft review, 31 October 2026

Branch `p4-b2`, base `86c624c0eef4384c29b693aafb2c3f5a9ddcad22`, containing
`sync-1` (`be91b3bd0051568d4795801b438409326ac51dc3`). Worktree:
`C:/HCMUS/OPENAI/seaxopenai_hcpus-p4-b2`. Local remains on its original checkout.

Eight HTTPX captures, four REAL products and events 14–17 are present. Capture
timestamps are around 11:41 ICT; each JSON records the exact UTC time, requested and
final URL, response SHA256, cleaned-text SHA256 and ordered passage locators.
Text comes from fetched HTML, including custom accordion labels. Whitespace is
collapsed; source spelling, punctuation and INCI noise are retained. No manually
transcribed page, model call, replay or fabricated scope is used.

Gold was drafted before the first candidate execution. All 20 real field labels
and all 12 planned blind cases are **DRAFT**, `labelled_by: draft:codex`.
Blind rows are only a case table: `PLANNED_NOT_MATERIALIZED`, not ready for evaluation.
Phase 3 must create passages, verify planned locators and freeze fixtures before
its first blind run. There was no blind candidate execution in this task.

## Compact human review table

SS = SINGLE_SOURCE; C = CONSISTENT; X = CONFLICTING; I = INSUFFICIENT.
Each row's exact citations and rationale are in `fixtures/gold/dev/real.json`.
The table targets the documented policy after code infers scope; it does not claim
that the S1 fallback pipeline already produces those results.

| Product / event | Volume | Skin | Ingredients | Number / company | Source evidence and review attention |
|---|---|---|---|---|---|
| R1 Hydrating / 14 | SS | X | X | I / I | Brand `title` vs `description#p4` disagree on dry vs normal/oily; that description names niacinamide absent from brand `ingredients#2`. Both conflicts are WITHIN_SOURCE, NEEDS_REVIEW, no seller attribution. Listing `specs#19` is 236ml; the 20ml promotion is a different item. |
| R2 Foaming / 15 | SS | C | C | I / I | Listing `usage#6` enumerates normal/oily/combination; brand `description#p1` uses the documented range convention. Listing's 30ml gift is not the primary 236ml bottle. INCI spelling/comma differences are retained. |
| R3 Blemish / 16 | SS | X | SS* | I / I | Brand `description#p1` and `usage#6` give different skin sets. Brand `description#p4` states 2%; listing `ingredients#3` names Salicylic Acid sixth without a percentage. See concentration issue below. |
| R4 Effaclar / 17 | SS | SS | SS | I / I | Listing `description#p20` notes old/new packaging; `description#p26` names Hexylene Glycol; `description#p29` contains free-from claims. No full in-scope INCI. The retailer 400ml WEB_PAGE is the same family and a different size. |

R1 and R2 both print `169170/22/CBMP-QLD` and `L'Oréal Việt Nam` on the listing.
R3 prints `267602/25/CBMP-QLD` and `Công ty TNHH L'OREAL VIỆT NAM`; its distributor
is listed separately and must not replace the responsible company. These are
observations from retailer text, not confirmation by an active document. Both
identifier fields stay I for every real case under REQ. No registry query was made.

*R3 concentration issue:* retain AC-04's existing field-level SS target for review.
Ingredient presence is supported by both INCI lists, whereas **2%** has only one
family. A reviewer must decide how the concentration claim is projected onto the
aggregate ingredient field. This task neither alters that contract/test nor derives
an answer from candidate output. R4's alcohol-free claim is I pending complete
INCI/version evidence; Hexylene Glycol by itself does not establish a conflict.

To approve, review the linked fixture locators and record reviewer/date and any
corrections. Only approved rows become REVIEWED; preserve this original draft and
any first-run evidence. No approval has been recorded by this task.

## Reachability

| Source | Result |
|---|---|
| Pharmacity R1, R2, R3, R4 listing URLs in DATASET-SPEC | HTTP 200; four LISTING snapshots |
| Official CeraVe R1, R2, R3 URLs in DATASET-SPEC | HTTP 200; three BRAND_PAGE snapshots |
| Pharmacity Effaclar 400ml | HTTP 200; one WEB_PAGE snapshot, same seller family, wrong size for R4 |
| Long Châu R1 URL in DATASET-SPEC | HTTP 403 Forbidden; absent from fixtures |
| Long Châu R2 Foaming 236ml URL | HTTP 403 Forbidden; absent from fixtures |
| `https://www.laroche-posay.vn/` and `https://laroche-posay.vn/` | DNS resolution failed, `getaddrinfo` error 11001; no brand snapshot |

R2 alternative URL attempted:
`https://nhathuoclongchau.com.vn/duoc-my-pham/sua-rua-mat-lam-sach-sau-danh-cho-da-dau-cerave-foaming-cleanser-mb094622-236ml-36481.html`.
R4 400ml captured URL is stored in its WEB_PAGE JSON. A search result is never used
as a substitute for an HTTP capture. All four primary listings succeeded, so all
four event files are present. Initial R2 identity rejection was resolved by reading
its actual h1 and adding the full observed alias, then fetching again; no source
text was typed into a REAL snapshot.

## Checks and integration handoff

From this worktree's backend with LLM_MODE=fallback, WORKER_INLINE=1,
OCR_ENABLED=0, WEB_SEARCH=off, AGENTS_TRACING=0; PHASE remains the checked-in 1:

- `python -m pytest -q tests/test_capture_page.py tests/test_phase2_capture_dataset.py tests/test_fixtures.py tests/test_guards.py`: final 62 passed, 0 failed/skipped/deselected (29 new capture/dataset checks, 29 existing fixture checks, 4 guards).
- `python -m pytest -q tests/test_acceptance.py --tb=short -rs`: 13 passed, 1 failed, 43 skipped, 0 deselected/errors.
- `python ../scripts/check_fixtures.py`: 53 files checked, 0 failed.
- After staging all 24 task files, `python -m pytest -q tests/test_guards.py`:
  4 passed, 0 failed/skipped/deselected; `git diff --cached --check` passed.

The one failure is **WAITING P1/P2**, `test_foaming_harmless_wording`: its volume
result is UNCERTAIN, with reason `Source scope needs confirmation`. Base S1
`pipeline/run.py` reads only declared scope; REAL snapshots intentionally omit it
per DATASET-SPEC. Scope inference is scheduled for Phase 2 and is not merged into
this task's base. The previously absent R2 event now exposes this existing boundary.
Do not weaken AC-01 or manufacture scope in fixtures. The 43 skips are pre-existing
future-phase gating, unchanged. No new skip, xfail, marker or assertion edit.

First R2 candidate execution was this offline acceptance check, **after** real and
blind draft labels were saved. Pre-run gold SHA256 values remain:

- real.json: `239532f541667ec67133bf341507b83ee0559288eacfe2aeb418de6670757489`
- expected-set1.json: `c74e98f6c2cb9b1b8e83b69f1d40dd04de7041dbe8b2b9c658df22f8796e5b38`

These are SHA256 of UTF-8 files with LF line endings; normalize CRLF to LF when
comparing after a checkout that uses Windows line-ending conversion.

The original acceptance JUnit output and exploratory capture logs are retained
locally under `backend/.venv/p4-2b-artifacts/` (ignored, not application data).

No baseline/eval/sync_check task, server, live model, main/p4 merge or push, tag,
or Phase 3 implementation. Browser appearance and live-model extraction remain
NOT VERIFIED. Main Local owns resolving these integration needs:

- **CCR P4→P2:** `scripts.capture_page.clean_html(html: str, *, section_end_markers: tuple[str, ...] = SECTION_END_MARKERS) -> str` · need: reuse this pure helper in web_sources · why: one HTML cleaning rule · snippet: `from scripts.capture_page import clean_html`. Ensure repository root is importable in the runtime. `CaptureError` means skip/report; caller retains fetching, ACL, Budget and trace ownership. No P2 file changed.
- **CCR P4→P1/P2:** inferred REAL scope in `pipeline/run.py` / scope owner · need: integrate documented R3 inference, distinguish primary size and promotion · why: AC-01 now fails on S1 scope UNKNOWN · snippet: retain source text and compute scope from product identity/variant/market before policy, never patch gold.
- **CCR P4→Local P4/P1/P2:** AC-04 ingredient/concentration projection · need: review field target vs concentration-level support · why: both sources list Salicylic Acid, only brand lists 2% · snippet: preserve existing assertions until an explicit shared decision; do not treat absence of percentage as contradiction.

Automatic read-only review covers touched-file ownership, immutable writes,
source/gold isolation, no candidate-derived labels, HTML generalization, blocked
fetches and test preservation. No separate `/review` step is required by the user.
