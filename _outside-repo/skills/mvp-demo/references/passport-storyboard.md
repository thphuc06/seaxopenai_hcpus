# Storyboard starter — Product Truth Passport (product demo, 3:00 limit, ~160 s planned, ~20 s reserve)

A starting point for `scripts/demo/storyboard.md` in the contest repo. The video shows the **running web app and the
system flow only**. The team pitches live, so there are no pitch slides, market numbers or "built with Codex" slides;
the problem framing, measured results and Codex evidence go into the pitch and the write-up. Before recording, check the
hackathon's video limit, then re-time every scene with the real app.

**Current team choice: silent video, no TTS.** Use short callouts and holds to explain the actions. The narration draft
below is retained only as optional wording for a future voice request; do not synthesize it or display whole paragraphs
as captions. Keep `narration.json` as `{}` until the user requests voice.

Ground rules for this product:
- Record in `LLM_MODE=replay` with `DEMO_RUN_DELAY_S=3`, so STALE stays visible.
- Before each take, `POST /api/internal/demo/reset`.
- Drive the UI through `data-testid` (contest README §7.4).
- The REPLAY, REAL and SYNTHETIC badges must be visible in at least one frame of every demo scene.
- Never call a product genuine, authentic or safe. Text quoted from a real page is shown as the source's words.
- Narration describes what the screen shows; it names no market statistics and makes no claims beyond the screen.
- Directions on screen (chip in the corner): **Deep Domain AI** in scenes 3, 4, 8; **Autonomous & Adaptive AI** in
  scenes 5, 6, 7.

| # | Time | Scene | Narration (draft, ~2.4 words/s) | On screen / action | What it shows | Note |
|---|---|---|---|---|---|---|
| 1 | 0:00–0:05 | Title | — (title card only) | "Product Truth Passport — evidence per field" | — | no claims, no numbers |
| 2 | 0:05–0:25 | System flow, live | "An event arrives. The model extracts claims; code checks every quote against its source, applies versioned rules, and publishes each field with a citation." | control room: `event-btn-01-bootstrap-demo` → stepper / trace waterfall (admit → extract → quote check → policy → publish gate) | the pipeline running, model vs code steps | SYNTHETIC badge visible |
| 3 | 0:25–0:47 | Field-level evidence on a real product | "A real pharmacy listing, captured today. Five fields, each with its own status. The title says oily skin; the usage section says normal, oily and combination — the brand page says normal to oily, which covers combination, so there is no false alarm. Opening the passport never calls a model." | `event-btn-15-bootstrap-real-foaming` → buyer → `evidence-open-skin_type` → refresh ×3, `model-calls-counter` unchanged | REAL badge, citation with capture time, read-only buyer | R2; if R2 could not be captured, use another REAL product (README §8) |
| 4 | 0:47–1:07 | Conflict in source | "The brand's own page says dry skin in the title and normal to oily in the description, and names an ingredient its own list does not contain. We flag the source, not the seller." | `event-btn-14-bootstrap-real-hydrating` → `why-open-skin_type`, `evidence-open-key_ingredients` | within-source conflict, seller not blamed | R1; fallback `event-btn-11-bootstrap-hydra` (SYNTHETIC twin, badge visible) |
| 5 | 1:07–1:27 | Revocation ripple | "The notification is revoked. Only the two fields that depended on it turn stale, instantly, with no AI call. The re-check marks them not verified and asks the seller for the right document." | `event-btn-05-revoke-notification` → Stale ripple → Not verified + request | event-driven staleness, abstention | registry is MOCK (badge) |
| 6 | 1:27–1:49 | Agent, verified by code | "A catalogue covers three sizes. Code decides every line that names a size. The agent places the one line without a size under its heading and must cite an anchor; code checks the anchor, and skin type changes — within a fixed budget." | `event-btn-09-catalogue-published` → `agent-panel`: proposal → "verified by code (anchor)" → before/after; `budget-meter-*` | agent effect, verified, bounded | say exactly what it changed |
| 7 | 1:49–2:07 | Web Scout | "For a real product, a scout searches the web; only pages whose identity code verifies are stored, hashed and cited. Retailer pages may confirm, never accuse." | `event-btn-14-bootstrap-real-hydrating` (web enabled) → `web-audit` panel → citation with domain and capture time | autonomous discovery with an audit trail | if a page was blocked, the audit shows the skip and its reason |
| 8 | 2:07–2:22 | Claims auditor | "Marketing claims are checked against the ingredient list: 'alcohol-free', yet alcohol is listed; two percent niacinamide, listed after a preservative capped at one percent." | `event-btn-13-bootstrap-clear-serum` → reviewer claims list; buyer sees only a count | domain rules from cited data | rule source note from `regulatory_limits.json` |
| 9 | 2:22–2:40 | Reviewer and receipt | "A reviewer approves one exact revision. When evidence changes, that approval goes stale too, and the buyer's receipt shows what changed since purchase." | reviewer queue → approve → stale after an event; receipt diff | human-in-the-loop bound to a revision | cut first if over time |

Cut order if over time: scene 9 → shorten 2 → scene 8.
Never cut 3, 4, 5 or 6. They carry both directions.
