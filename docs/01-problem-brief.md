# 01 — Problem brief (one page)

## Problem

Cosmetics shoppers compare volume, skin type and key ingredients. Platforms also need regulatory details: the cosmetic notification number and the company responsible for the product. Mall badges and ratings are seller-level signals. They do not show whether **each field** of a listing is supported by the right source (notification, brand page, packaging) for the **exact product version**, or whether that support is still current.

Evidence we cite:

1. **Official sources contradict themselves.** CeraVe Vietnam's Hydrating Cleanser page (captured 19/09/2026, re-read 21/09/2026): title/highlights say dry skin; the description talks about a foaming cleanser for normal-to-oily skin and mentions niacinamide, which is not in the page's ingredient list. A naive "listing vs brand page" check would wrongly flag an accurate seller.
2. **Checks go stale.** June 2026: DAV revoked 286 cosmetic notification numbers from 21 companies in one decision (at the companies' request — administrative, not a safety finding).
3. **Pressure on platforms.** VCC 2025: e-commerce = 191 of 896 complaints (21.3%); incomplete/inaccurate information = 9.2% of cases by violation type. E-Commerce Law 122/2025/QH15 (in force 1 July 2026), Art. 17: intermediary platforms must moderate seller-created product information before display.

(All figures to re-verify in [pitch/fact-check.md](pitch/fact-check.md).)

## Users

| User | Need | What the Passport gives |
|---|---|---|
| Shopee Health & Beauty category managers, Trust & Safety (primary) | Prioritise cases needing human judgment; see why a field was flagged | Reviewer queue with evidence attached, history, revision-bound approval |
| Ingredient-conscious buyers | Know which detail is supported, conflicting or unverified | Per-field labels + public evidence + last-checked time |
| Brand / official store managers | Accurate claims represented; reference-source errors not blamed on them | Source-conflict label separate from seller fault; evidence requests |

## Solution

**Product Truth Passport**: per field, compare listing ↔ brand reference ↔ supporting document, scoped to the same variant, market and version. Show verdict + evidence + last check.

Three design choices:

1. Check reference sources for self-contradiction before flagging a listing.
2. Model extracts claims; code decides results.
3. Findings update when evidence changes; opening a Passport never calls a model.

## Demo cases

| Case | Origin | Expected behaviour |
|---|---|---|
| CeraVe Foaming Cleanser | REAL | Harmless wording differences → CONSISTENT |
| CeraVe Hydrating Cleanser | REAL | Brand page self-contradiction → source conflict, not seller fault, goes to reviewer |
| CeraVe Blemish Control Cleanser | REAL | 2% salicylic acid only on brand page → SINGLE_SOURCE |
| Fictional domestic brand (DEMO-…) | SYNTHETIC | Notification matches listing; then a revoke event → notification-dependent fields STALE and re-assessed; others unchanged |

## What we do not claim

- Not an authenticity, counterfeit or safety check.
- Not marketplace-wide accuracy; the demo set is 3 real + a few synthetic cases.
- No live Shopee, registry or brand connectors in the demo.
