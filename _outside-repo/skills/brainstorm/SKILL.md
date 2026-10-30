---
name: brainstorm
description: Structured brainstorming for the Product Truth Passport hackathon team — generate and rank options (stretch features, cuts, demo story, pitch framing, judge Q&A, design pre-mortems) against the judging criteria, the two build directions (Deep Domain AI, Autonomous & Adaptive AI), the AGENTS.md rules and the time left; recommends one option with a ready Codex prompt. No code. Use when a lane finishes early, is stuck, must choose what to cut, or someone says "brainstorm", "ideas", "nên làm gì tiếp", "chuẩn bị Q&A".
---

# Brainstorm (decide fast, decide well)

Goal: a short ranked list of options and one recommendation that fits the clock, the rules and the judging. This skill does not write or edit code.

Best run inside Plan mode (`/plan`): it is read-only and asks clarifying questions as multiple choice. Outside Plan mode, still write nothing except what the steps below name.

## Modes (pick from the user's words; default `options`)
- `options`: what to build or do next.
- `cut`: what to drop to hit a checkpoint.
- `story`: demo order and narration.
- `qa`: likely judge questions with one-sentence answers grounded in repo facts.
- `challenge`: pre-mortem or red-team a design, a claim or a pitch line.

## Steps
1. **Frame.** State the decision in one line. Note the time left until the next Sync and until the 16:00 freeze (README §3), and who would do the work (lane).
2. **Gather facts quickly**, in one batch of reads:
   - README §3 (current phase row), §8 (cut rules), §9 (directions map);
   - the Outcomes and Surprises in `.agent/plans/*.md`;
   - `docs/tracking/PROGRESS.md` and the latest DEVLOG entry;
   - test status, if relevant (`pytest -q` summary only);
   - `docs/results/*`, for `story`/`qa`.
3. **Generate 5–8 options.** Make them genuinely different. Include at least:
   - one that does less (cut or simplify);
   - one that makes something that already exists **visible** (often the best value late in the day);
   - one new capability.

   Tie each option to a direction and a judging criterion.
4. **Score each option in one table.** Columns:

   | Column | Values |
   |---|---|
   | Judging impact (problem framing / build quality / depth of thinking / Codex leverage) | 1–5 |
   | Direction fit: Deep Domain | 0–2 |
   | Direction fit: Autonomous & Adaptive | 0–2 |
   | Effort | hours and lane |
   | Risk to non-negotiable rules or demo stability | low / med / high |
   | Model cost | $ estimate |

   Drop any option that breaks an AGENTS.md rule, and say which rule it breaks.
5. **Pre-mortem the top two.** How would each fail on stage or under a judge's question? What is the mitigation?
6. **Recommend** one option and one fallback. For the recommendation, give:
   - the owner lane and the files;
   - the Done-check;
   - a ready-to-paste Codex prompt with Goal / Context / Constraints / Done when, following the lane-file style.
7. **Mode-specific outputs:**
   - `qa`: 10–15 questions, each with a one-sentence answer and the repo evidence path. Flag any answer the repo cannot support.
   - `challenge`: a ranked list of holes, each with a test or demo step that would expose it.
8. **Write to the ExecPlan only if the user asks.** In that case append the decision to the asker's ExecPlan Decision Log. Otherwise only reply.
