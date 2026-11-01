# Replay screenshots — 1 November 2026

These seven1280×720 images show actual API responses from an isolated SQLite database using the shipped replay files and production frontend build at `sync-5` (`d46a1d6`). They were captured after the contest. No provider calls, frontend mock responses or screenshot text overlays were used. They do not replace P4's LIVE video or establish a complete replay journey.

| Image | What it demonstrates | Boundary |
|---|---|---|
| [Buyer](01-buyer-real-r2-replay.png) | REAL/REPLAY badges and initial R2 findings | Not all five fields fit this viewport; missing image/price presentation is retained. |
| [Evidence](02-evidence-real-r2-replay.png) | Stored volume quotes, locators, versions and capture times | The dialog obscures page-level origin/mode badges. |
| [Listing disagreement / Why](03-listing-conflict-why-r2-replay.png) | Actual listing-versus-source ingredient disagreement | **Not** within-source conflict; Why remains generic. |
| [Review queue](04-reviewer-real-r2-replay.png) | Open ingredient task, revision2 | No decision was submitted; current queue has no origin/mode badge. |
| [Agent / partial run](05-agent-no-confirmed-effect-replay.png) | Budget and `PARTIAL/REPLAY_MISS` | No recorded agent effect; neither a demonstrated change nor evidence of “no change.” |
| [Web audit](06-web-audit-real-r2-replay.png) | Two stored REAL snapshots, identity checks and passage counts | Original31October capture times; not new live fetches. |
| [Web query](07-web-query-replay.png) | REPLAY query and candidate decisions | Discovery/ranking evidence, not a generated answer. |

Capture made22 API GETs and no mutation requests or JavaScript errors. Two handled404s came from queue discovery for unrun S3/S4 products. Event/run/job/model-call counts did not change during capture. R1/S2 within-source scenes and a confirmed agent before/after effect were unavailable because replay coverage is incomplete. Full procedure and test receipts are preserved in [P3 Phase6](../../../.agent/plans/P3.md).
