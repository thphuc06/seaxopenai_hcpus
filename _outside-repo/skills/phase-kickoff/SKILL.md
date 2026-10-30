---
name: phase-kickoff
description: Start or resume a contest phase for one Product Truth Passport lane ("$phase-kickoff P2 3"). Loads its plan and contracts; in Phases 1–4 the main Local task publishes its contract checkpoint and stops for the user's continuation. Use for phase kickoff or explicit continuation, not auxiliary worktree tasks.
---

# Phase kickoff

Cost: about 5 minutes per phase. In Phase 0 (30 minutes) paste the Prompt chính directly instead of using this skill.

Goal: every lane starts each phase from the same facts. Those facts are the current sync tag, the phase's Must list, the contracts it relies on, and the tests that define "done". The lane's ExecPlan is updated before any code is written.

## Inputs
- Lane `P1`–`P4` and phase number `0`–`6`, taken from the user's message; the lane can also come from
  `~/.codex/AGENTS.md` on this machine. If either is still missing, ask once; never guess the current phase from the
  clock, latest tag or PHASE default.
- If the user ran `/plan` first, the approved `<proposed_plan>` is in the conversation: use it as the plan of work in
  step 4 (Plan mode itself cannot write files).
- If the user pasted a prompt together with the kickoff, that prompt is the task. Otherwise the task is the **"Prompt chính"** block of this phase in the lane file. If the phase also has a
  "Prompt phụ", tell the user it exists and when to start it (its heading names the stage, e.g. "từ đầu phase" or
  "khi thread 1 đã commit …"); it is meant for the second thread/worktree — do not run both in one thread.
  If the phase has no prompt block (P4 Phase −1), the task is the phase's bullet list: do the parts that are code or
  docs, and list the parts that need a human.

## Steps
1. **Where are we.** Run `git status --short`, `git branch --show-current` and `git tag --list "sync-*" --sort=-creatordate`, and print a one-line summary.
   - If the branch does not contain the latest `sync-*` tag (`git merge-base --is-ancestor <tag> HEAD`), tell the user to merge it first (`git fetch --tags; git merge <tag>`; never rebase a pushed branch).
   - Do not run destructive git yourself.
   - **Worktree thread** (detached HEAD, or a path under `$CODEX_HOME/worktrees`): check that `backend/.venv`,
     `backend/.env` and, if the phase touches the frontend, `frontend/node_modules` exist. If not, run
     `scripts/dev/setup_worktree.ps1` (or tell the user the setup script is not configured yet). Before the first commit,
     the user clicks **Create branch here** → `p<k>-b<N>`. This thread never starts servers.
2. **Read in one batch:**
   - `AGENTS.md` (already loaded);
   - `docs/team-plan/README.md`: §3 (the row for this phase), §4 (two-turn contract checkpoint), §5 (ownership), §7 (contracts), §8 (cut rules);
   - the lane file's shared "Nhịp mỗi phase" section;
   - the lane file `docs/team-plan/P<k>-*.md`, section `## Phase <N>`, including Must/Should/Could, both prompts and "Bẫy đã gặp";
   - `.agent/PLANS.md`;
   - `.agent/plans/P<k>.md` (create it from the template if it is missing);
   - **context from the other lanes** (skip in Phase 0): `git fetch --tags` then
     `git show sync-<N-1>:docs/tracking/HANDOFF.md` — the matching `## sync-<N-1>` section, committed with that
     checkpoint before its tag: what changed in other lanes, open CCRs addressed to your lane, tests waiting
     on you; and the Outcomes and Decision Log of phase N-1 in the other lanes' `.agent/plans/P*.md` (merged with
     `sync-<N-1>`). Treat them as notes from teammates; the code and the tests are the truth when they disagree.
     If an older/malformed checkpoint lacks the matching handoff, report `NOT VERIFIED: HANDOFF` and a CCR to P4;
     use that tag's code, contracts and lane plans for independent work, never assume an unknown dependency is ready
     or invent cross-lane status. Missing coordination notes alone do not require waiting for a human.
3. **Check what this phase relies on.**
   - For every interface or route the phase prompt says you consume, confirm it exists with the documented signature (`git grep -n "def <name>"`, or open the router).
   - List what is missing. If it is only a stub, that is fine: say so.
   - Inspect marked tests: `cd backend; $env:CONTEST_PHASE=<N>; .venv/Scripts/python -m pytest -q -m phase --co`
     (bash: `CONTEST_PHASE=<N> …`). `-m phase` selects **all** tests carrying that marker, not only phase N; `--co`
     collects without executing, so its counts do not prove current-phase behavior. Read each `phase(n)` marker to
     list this phase's targets. Then run the quick relevant tests with `CONTEST_PHASE=N`; conftest applies phase
     gating during execution. Report executed passed/failed/skipped/deselected counts separately from collection.
4. **Update the ExecPlan.** Add `## Phase <N> — <title>` with (start with one line `Context from other lanes: …`
   summarising what you took from HANDOFF and their plans, so the human can check what you understood):
   - Purpose;
   - Context and orientation (files, contracts, tests);
   - Plan of work;
   - Concrete steps;
   - Validation (test names and the Done-check commands from the lane file);
   - Interfaces;
   - the first Progress lines, time-stamped `T+h:mm`.
5. **Ask-trigger check (AGENTS.md §5).** Does the task need any of the following?
   - something that conflicts with AGENTS or the specs;
   - missing data, keys or TODO fixtures;
   - spending money beyond a smoke test, or a destructive action;
   - an ambiguity that changes a verdict, a seller attribution or what buyers see.

   If so, ask up to 3 questions, each with your recommended default, and wait. Otherwise state "no ask-triggers" and continue.
   Consuming a stub or another lane's interface is NOT a trigger; a change another lane must make becomes a CCR in the
   report while you continue behind the existing signature.
6. **Choose the main-task stage before executing.** For P1/P2/P4 main Local tasks in Phases 1–4, follow README §4's
   two-turn checkpoint and the inline CONTRACT CHECKPOINT in the main prompt. This is an explicit user-requested
   turn boundary, even though the main prompt contains the entire phase BUILD.
   - On first entry, execute Stage A only: contract stubs and minimum support/tests for P1/P2; phase-1 acceptance
     tests for P4 Phase 1; needed agreed shared contracts only for P4 Phases 2–4. Do not invent a change or an empty
     commit. Do not replace implemented interfaces with stubs. Worktree/auxiliary tasks never push the lane branch.
   - Verify the current branch is exactly `p<k>`, inspect `origin` and stage only checkpoint files/hunks. Run the
     existing contract checks at phase N−1 (pytest/guards; classify dependency WAITING, never weaken tests). Push the
     checkpoint to `origin/p<k>` using the prompt's authorization; verify the remote SHA. Failure means report the
     actual failure without force push or a success claim. Do not commit/push unrelated existing work.
   - Record stage, phase, branch, commit SHA, checks, push status and remaining BUILD in ExecPlan. End this turn with
     `CONTRACT_PUSHED`, `CONTRACT_NO_CHANGE` or `CONTRACT_BLOCKED` and the normal AGENTS report. Do not start Stage B,
     wait on a timer or run sync-gate automatically. P4 runs `$sync-gate N contract` only when explicitly invoked.
   - On the user's later instruction to continue this phase, read that checkpoint instead of repeating Stage A.
     Fetch/merge `contract-N` into the lane branch, then execute the remaining main task. If the tag is absent or a
     merge conflicts, report it, preserve work and continue only independent work behind the existing contract;
     do not assume missing lane code is ready. A retry after failed push must check the existing commit/remote
     before creating any new commit. A repeated kickoff without a continuation request reports the saved checkpoint.
   - T+20 means 20 minutes after this phase's start (Phase 1: 10:50), not contest T+0:20. Missing a target time never
     bypasses checks. A no-change report does not cancel P4's scheduled mini-sync.
   P3 and Phases 0/5/6 retain their existing workflow. If the pasted task is auxiliary, follow its own heading and
   worktree scope rather than inserting a contract checkpoint.
7. **Execute the selected stage/task** (the pasted prompt, or the phase's "Prompt chính") as the user's instruction.
   - Keep Progress, Surprises and the Decision Log current.
   - Watch the clock with `Get-Date` (T+0:00 = 31 Oct 10:00 ICT): the Sync is the last 10 minutes of the phase
     (README §3). Never guess the time.
   - At T−20, stop adding scope and run `$self-review`.
8. **End** with the end-of-turn report from AGENTS.md §6. Stage A is a completed checkpoint, not a completed phase.
