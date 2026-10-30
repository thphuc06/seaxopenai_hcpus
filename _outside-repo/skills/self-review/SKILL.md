---
name: self-review
description: Pre-handoff check before pushing a lane's work at a Sync in the Product Truth Passport repo — tests/build, file ownership, hardcoding and overfitting scan, AGENTS.md rule checks (forbidden wording, gold isolation, secrets, model-decides-verdict, buyer read-only), contract and replay safety, docs sync, ExecPlan, CODEX_LOG row. Use when someone says "self-review", "ready to push", "trước khi push", or at T−20 of a phase.
---

# Self-review before a Sync

Goal: P4's merge at the Sync should find nothing you could have found yourself. Fix what is in your lane. Report everything else as a CCR. Never edit or revert another lane's files.

## 1. Scope of the change
- `git fetch --tags`. Use `git status --short`; before printing patches, run the filename-only secret scan in §3
  and exclude any secret-bearing files from printed evidence. Review the **actual patches** from
  `git diff <latest sync tag>...HEAD`, `git diff --cached` and `git diff` (committed, staged and unstaged respectively).
  If no sync tag exists yet, use the task's recorded starting commit and report that base. List untracked files with
  `git ls-files --others --exclude-standard` and read their non-secret contents too; a filename list is not a review.
  Never print `.env`, credentials or key material; scan suspected files by filename only and redact review evidence.
- Map each file to its owner (README §5; AGENTS.md §4 "Stay in your lane"). If a file is outside your lane:
  - your accidental edit → undo only your own edit;
  - an intentional change → turn it into a CCR.

## 2. Tests and build
- `cd backend; .venv/Scripts/python -m pytest -q -rs` with `CONTEST_PHASE` set to the explicitly identified current
  phase; if missing, ask once rather than infer it. Tests depending only on merged work must pass; classify a failure
  as WAITING only with its `needs(...)` marker and the missing lane's work. Report passed/failed/skipped/deselected
  counts and the effective phase. No phase/marker/conftest/pytest.ini changes to make tests green: only P4 may make
  documented gating changes at a Sync; identify those separately with their rationale. Setting CONTEST_PHASE to run
  the current phase is expected, not a forbidden gating edit.
- If `frontend/**` changed: `cd frontend; npm run build`.
- If prompts or model steps changed: the prompt version or step name was bumped. Inspect `--name-status` for
  `fixtures/replay` across all three diffs in §1 and its untracked files: only added recordings, none modified/deleted.

## 3. Rules scan
Fixture ids and brand names in app code, forbidden wording, gold isolation, a tracked `.env` and key-shaped strings in
tracked files are checked by `backend/tests/test_guards.py` (it holds the one forbidden-word list), so step 2 covers
them — do not keep a second list here. Add the two scans the guard cannot do (run from the repo root):
```powershell
git grep -l -I --untracked -E "sk-[A-Za-z0-9_-]{16,}"    # filenames only, incl. new files; no match expected; never print the key
git grep -l -E "except( Exception)?( as [a-z_]+)?:[[:space:]]*$" -- backend/app    # filenames only; inspect/redact each handler locally, without printing secret-bearing context
```
Steps 3–5 need reading, not running: spawn three read-only `explorer` subagents in parallel on the full review scope from step 1 —
(a) the reading checks below, (b) §4 contracts and docs, (c) §5 overfitting — while this thread runs step 2. They
report; they never edit. Give each the base commit and the actual committed/staged/unstaged patches plus non-secret
untracked contents, or exact commands and access to read them. Filenames alone are insufficient; omit and report
secret-bearing files without copying their contents into prompts or logs.

Then check by reading the diff:
- **Open-set lists in code.** New Python/TS lists or dicts with five or more natural-language strings belong in `backend/app/data/*.json`, with an `_about` note (rule 14).
- **Model decides verdict (rule 3).** Only `pipeline/policy.py` decides the public `verdict`, `review_state` and
  `freshness`. `pipeline/publish.py` validates and persists policy-approved decisions; it never re-decides them.
  Claims audit and reviewer routes provide code-verified inputs through the documented policy/publish path, never
  copy model decisions into public results. `pipeline/baseline.py` may compute B0/B1 comparison outputs for isolated
  evaluation only; they never publish a passport or overwrite production findings.
- **Buyer read-only (rule 6).** If routes changed, a test proves every BUYER GET creates no rows.
- **Budget.** Every new model, tool, search or fetch call goes through `llm.client` / `Budget`.
- **Windows.** Every file open uses `encoding="utf-8"`. There is no `tests/__init__.py`.

## 4. Contracts and docs
- Signatures in README §7.1 are unchanged, or extended only with defaulted keyword arguments.
- New routes, trace steps and env switches are listed in your report. Ask P4 (CCR) to add new env switches to `config.py`/`.env.example`.
- A policy rule changed → `POLICY_VERSION` bumped and noted in `docs/tracking/DECISIONS.md`.
- A contract, table, route or enum changed → the matching spec doc section "As built (contest)" is updated, or a CCR is sent to its owner.

## 5. No overfitting
- Every rule touched in this phase is tested on at least one input that was not written for it: a metamorphic variant, a blind fixture, or a synthetic input built in the test.
- If a blind case failed and you fixed it, the fix is a mechanism, not a special case: name the mechanism in the report.

## 6. ExecPlan and log
- `.agent/plans/P<k>.md`: Progress is up to date; Surprises and the Decision Log are filled; Outcomes is drafted for this phase.
- Draft the CODEX_LOG row(s): `| time | lane | task (short) | files | accepted/edited/rejected | human change | test |`.

## 7. Codex review (if ≥ 5 minutes remain before T−10)
Ask the human to run `/review` → "Review against a base branch" → `main`, and paste the findings. Fix in-lane P0/P1
findings; turn the rest into CCRs.

## 8. Output
End with the AGENTS.md §6 report and one verdict line:
- `READY TO PUSH`, or
- `BLOCKED: <items>` — fix in-lane items now, then re-run steps 2–3.
