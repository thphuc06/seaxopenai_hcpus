---
name: sync-gate
description: Integrator (P4) procedure for a Sync in the Product Truth Passport contest build ("$sync-gate 2", "$sync-gate 2 contract", "$sync-gate 5 rec") — merge lane branches in order P4→P1→P2→P3 with a test before each merge commit, advance the test phase, build, tag, then review and log. Run only when P4 types it.
---

# Sync gate (P4)

Goal: in about 5 minutes integrate the lanes that pass the checks below. Tag only after the applicable gate passes;
review and logs follow while the team starts the next phase. The clock never waives a failed gate.

## Rules
- **Inputs:** require explicit phase N (0–6); `contract` is valid only for N=1–4, `rec` only for N=5. Ask once if missing
  or inconsistent; never infer N from the clock or latest tag.
- **Where:** always in P4's Local thread (the main checkout), never in a worktree thread. For N≥1, commit and push
  `p4` first. S0 starts directly on `main`; `p4` is created only after S0. Check `git status --short` before switching
  branches; preserve unrelated work. Shell is PowerShell: `$env:CONTEST_PHASE=<n>; …`, never `CONTEST_PHASE=<n> …`.
- **No regression lands on `main`** ("red" = a test green immediately before this merge and red after it). Immediately
  before **each** merge, run the baseline on the current `main` and record test node IDs and outcomes; use the same
  phase, mode and commands after the merge. Refresh it after every accepted merge, including delayed retries: a test
  fixed by P1 and broken by P2 is a regression. New failing applicable tests and collection/setup errors also block.
  Merge with `git merge --no-commit --no-ff <branch>`, run the checks, then
  `git commit -m "S<N> merge <lane>"` if green or `git merge --abort` if red. Do not use `git revert -m 1` to back out a
  merge: if that lane is merged again later, git silently drops the reverted work (only the new commits arrive). If a
  bad merge is found only after it was committed, revert it, write the revert sha in DEVLOG, and before merging that lane
  again run `git revert <revert-sha>`.
- **Never rewrite history.** No force push, no rebase of a pushed branch. Lanes bring `main` into their branch with
  `git merge`, so every push is a fast-forward.
- Resolve conflicts yourself only in P4-owned files.
- **PHASE convention:** after Sync N, `backend/tests/PHASE` contains N. All tests for phases ≤ N whose dependencies
  are merged must pass. A checkpoint with explicit `WAITING` tests is partial, never "all green" or a completed
  milestone. Lanes working on phase N+1 set `$env:CONTEST_PHASE=<N+1>` themselves.
- Python is always the venv one: `cd backend; .venv/Scripts/python ../scripts/<script>.py`. A script that does not
  exist yet (for example `sync_check.py` at S0) is skipped and named in the report.

## Gate before any tag
- Run the selected phase's pytest suite with counts and `test_guards.py`, plus the frontend build if frontend code
  changed; run the applicable fixture and sync checks when present. No collection error, guard failure, unexplained
  failure, regression or broken build is acceptable, including a failure already present in the baseline.
- A test may be `WAITING` only when its `needs(...)` marker names required phase work that is demonstrably not merged.
  Record its node ID, missing lane/commit and reason. A merged branch from an earlier phase is not proof the required
  work arrived. Tests depending only on merged work, and failures without a dependency marker, must pass. Do not
  weaken tests, markers or phase settings to relabel a failure. Report actual passed/failed/skipped/deselected counts.
- If the gate fails: **do not create or push the tag, and do not announce completion**. Abort an uncommitted failing
  merge; for a failure after phase advance, restore only this invocation's uncommitted PHASE edit to the prior value.
  Preserve accepted merges and other work, report `BLOCKED` with owner/test/command, obtain the owner fix or apply the
  documented scope cut, then rerun the gate. Never move an existing tag or use force push. A time limit cannot bypass
  this recovery. `rec-freeze`, `freeze` and `submit` allow no WAITING within their required scope.

## Mini-sync (`$sync-gate N contract`, T+20 of Phases 1–4, about 5 minutes)
1. `git fetch --all --tags`; `git switch main`; `git pull`.
2. Merge, each with a fresh baseline and the no-commit test (`$env:CONTEST_PHASE=<N-1>`): P4's contract commit (Phase 1: the phase-1
   acceptance tests), then the commits whose message starts with `S<N> P1: contract` and `S<N> P2: contract`
   (`git merge --no-commit --no-ff <sha>`), then any lane that missed Sync N-1 (its whole branch).
3. Run the pre-tag gate at phase N−1; do not advance PHASE or claim phase N implementation is complete. If it passes,
   `git tag contract-<N>`; `git push origin main --tags`. Announce: "merge contract-<N> into your branch", with any WAITING.
If a lane has no contract commit by T+25, skip it and say so.

## Minimum Sync (`$sync-gate N`, T−10 → about T−5)
1. **Prepare.** `git switch main; git pull; git fetch --all --tags`. Lane branches: `origin/p1`, `origin/p2`,
   `origin/p3` (owners merge their second-thread branches `p<k>-b<N>` before pushing). Lanes push by T−10; T−8 is the
   grace limit — ping once, then continue without that lane.
2. **Check phase.** For N≥1 use N−1 during merges; for S0 use 0, never −1. Tests normally use `LLM_MODE=fallback`;
   recordings/freeze/hotfix use replay as specified below. Immediately before each merge run
   `cd backend; $env:CONTEST_PHASE=<check phase>; .venv/Scripts/python -m pytest -q` on the current `main`.
3. **Merge in order P4 → P1 → P2 → P3** (S0: P4's work is already on `main`, then P1 → P2 → P3),
   each with `git merge --no-commit --no-ff origin/<branch>`:
   - conflict in a P4 file → resolve it; conflict elsewhere → `git merge --abort` and tell the owner: "`git fetch;
     git merge origin/main`, resolve, test, push by T−3". Merge that lane last when it comes back; after T−3 omit it
     only if the remaining work passes the pre-tag gate, note it in DEVLOG, and retry at the next mini-sync.
   - checks: pytest with the same check phase and mode; plus `cd frontend; npm run build` when the lane is P3 or
     `frontend/` changed (`npm ci` first if `package-lock.json` changed). Compare against the baseline taken immediately
     before **this** merge, not the first merge of the Sync. Existing failures are eligible only for the explicit
     WAITING classification above. Green → commit and refresh the next baseline; red →
     `git merge --abort` and
     send the owner the failing test or build error.
4. **Advance.** Write `<N>` into `backend/tests/PHASE`. Run `$env:CONTEST_PHASE=<N>; .venv/Scripts/python -m pytest -q`
   and classify every failure using the pre-tag gate. Run `../scripts/check_fixtures.py` and
   `../scripts/sync_check.py <N>` with the venv Python, if they exist. A required script failure blocks the tag.
5. **Prepare the handoff, then tag only after the gate passes.** On `main`, append `## sync-<N>` to
   `docs/tracking/HANDOFF.md` before committing/tagging. Per lane, record 3–5 lines from its report and ExecPlan Outcomes:
   delivered work; changed interfaces/routes/trace steps/env switches; decisions affecting other lanes; open CCRs;
   WAITING tests with the missing lane/commit. Include omitted lanes and scope cuts; never invent a lane's status.
   Commit the PHASE/gate changes and this handoff together as `S<N> P4: sync gate`. Check
   `git show HEAD:docs/tracking/HANDOFF.md` contains the matching section before creating the tag; if absent, do not
   tag or push. Then `git tag sync-<N>`, verify the tagged handoff, and `git push origin main --tags`. Even at
   T+5 of the next phase, unresolved non-WAITING failures or a missing handoff block the tag. Announce:
   ```
   sync-<N> tagged at <clock>. Merge sync-<N> into your branch (git fetch --tags; git merge sync-<N>). Phase <N+1> ends <clock>.
   Status: complete / partial (WAITING) · Green: … · WAITING (test → missing lane): … · Not merged: … · Cut: …
   Handoff: docs/tracking/HANDOFF.md, section sync-<N>, included in the tag
   ```
6. **Return to the lane.** After the checkpoint and its handoff are pushed, `git switch p4; git merge sync-<N>`.
   At S0, create `p4` once from the tagged `main` (`git switch -c p4; git push -u origin p4`); if it already exists,
   switch to it and merge the tag instead. Every lane's `$phase-kickoff` reads the handoff from this exact sync tag.

## After the tag (first minutes of the next phase, while the lanes run their kickoff)
7. **Review** (skip at S0 — there is no previous tag). `git branch -f review-base sync-<N-1>` (local only, never
   pushed); ask the human to run `/review` → "Review against a base branch" → `review-base`, or "Custom review
   instructions": "review the diff sync-<N-1>..sync-<N> against the `## Code Review Rules` of AGENTS.md". Meanwhile spawn
   three read-only `explorer` subagents on that diff: (a) Code Review Rules, (b) README §7 contracts, (c) overfitting.
   Fix P4-owned findings on `p4`; the rest become CCRs.
8. **UI click path (human).** The human starts the Codex app Actions `backend` and `frontend` and clicks the phase path
   of README §3. Do not start servers yourself.
9. **Logs.** `docs/tracking/DEVLOG.md` (per lane: Done, Blocked, Surprise, Decision, Next; metrics), `CODEX_LOG.md` (one
   row per Codex task from the reports), `PROGRESS.md` (actual time), `DECISIONS.md` (contract or rule changes). Commit
   `S<N> P4: logs` on `main` (`git switch main`, commit, push, `git switch p4`, `git merge origin/main`), so the lanes
   can read them during the phase. The tag pins the code and its handoff; later operational logs do not move the tag.
10. **Cut rules.** Compare the README §3 Must list with reality; apply README §8 and write the decision in DEVLOG and
    DECISIONS. Do not reopen the debate.

## Special Syncs
- **S0 (10:20–10:30).** Start on `main` with P4's skeleton committed there; no `p4` push or merge prerequisite.
  If S1 fixtures from `p4-b0` have not arrived, integrate that branch with the same fresh-baseline gate, then merge
  `origin/p1..p3`. Use phase **0** for every baseline, post-merge and pre-tag run; `PHASE` stays 0. Run guards and
  collection; report a missing `sync_check.py` as NOT VERIFIED. No previous-tag review. Create/push `p4` after the
  successful `sync-0` tag (which already contains its handoff), never before as a requirement of S0. Do not create it
  a second time from the manual lane checklist.
- **Recordings freeze (`$sync-gate 5 rec`, about 15:35).** Merge only `origin/p2` (recordings, `REPLAY_FREEZE=1`) and
  `p4` (final storyboard), with fresh baselines and checks in `LLM_MODE=replay`, `REPLAY_FREEZE=1`, phase 4.
  Leave PHASE at 4; this is a recordings checkpoint, not completion of phase 5. Before tagging `rec-freeze`, require
  the phase-4 gate and the final storyboard's replay/sync path to pass with no replay miss or WAITING in that scope.
  P3 merges it and records the video segments. Report any deliberately fallback-labelled cut scenes separately.
- **Freeze (`$sync-gate 5`, 15:50).** Minimum Sync in replay; the full phase-5 gate must pass with no WAITING before
  tagging `sync-5` and `freeze`. After 16:00 only blockers change code.
- **Hotfix (`$sync-gate 6`, Phase 6).** A blocker fix approved by P4 is committed on the owner's lane branch and pushed;
  merge only the approved fix with the same fresh-baseline/no-commit tests in replay (check phase 5), then run the
  phase-6 pre-tag gate with no WAITING and the affected demo path. Tag `submit` before 16:40 only if those checks pass.
