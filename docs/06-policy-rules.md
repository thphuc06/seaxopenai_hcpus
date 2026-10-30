# 06 — Policy rules (`policy-v1`)

Implemented in `pipeline/policy.py`. Pure functions: `(claims, scope, sources, gaps, reviews) -> FieldResult`. No model calls. Bump `POLICY_VERSION` on any change and note it in [tracking/DECISIONS.md](tracking/DECISIONS.md).

## Ordered rules (per field)

1. **Access.** Drop passages the current role cannot see. Never leak another case/tenant's documents.
2. **Validity.** Drop claims from sources with status `REVOKED` / `SUPERSEDED` from current conclusions (keep in history). If a field's only supporting source was revoked → `INSUFFICIENT`, `freshness = CURRENT` after re-assessment (STALE until re-assessed).
3. **Scope.** Claim scope (product, variant, market, version) must match the case. Unknown → `scope_match = UNKNOWN`, verdict at most `UNCERTAIN`. Mismatch → claim excluded, reason recorded.
4. **Self-conflict first.** Within one source version, if two passages give incompatible values for the same field → `CONFLICTING`, `conflict_locus = WITHIN_SOURCE`, `seller_attributable = false`, `review_state = NEEDS_REVIEW`. That source is not used to judge the listing for this field.
5. **Compare.** Same field, normalised values:
   - volume: equal within 1% → compatible.
   - skin_type: **directional**. A listing claim is supported when the reference says `ALL`, or when the claim's types ⊆ the reference's types; a listing saying `ALL` is **not** supported by a page saying `{DRY}`. Two references (neither is "the claim", e.g. two sections of one page) agree if either direction holds. `{DRY}` vs `{NORMAL, OILY}` → incompatible.
   - key_ingredients: listing ingredient ⊆ reference highlights ∪ reference INCI → compatible. Highlighted ingredient absent from the **same source's** INCI → within-source conflict.
   - identifiers (notification number, company): exact after normalisation.
6. **Not mentioned ≠ negated.** A source that does not mention a value is not evidence against it. Highlight list ≠ full INCI.
7. **Independence.** Count independent source **families** that state the value, the listing included (brand page and a seller copy of the brand page = one family). One family → `SINGLE_SOURCE` with text "Stated by {source} only" (e.g. Blemish 2% salicylic acid: brand page only; DEMO skin type: listing only).
8. **Consistent.** ≥2 independent families, all compatible, scope MATCH → `CONSISTENT` ("consistent across the sources checked").
9. **Conflict across sources.** Listing vs reference incompatible → `CONFLICTING`, `LISTING_VS_SOURCE`, `NEEDS_REVIEW` (a human decides before anything reflects on the seller).
10. **Missing.** No usable claim → `INSUFFICIENT` + a `Gap` (field, missing kind, needed doc, known ids) → `EvidenceRequest` if a party can supply it.
11. **Publish gate** (`publish.py`): every citation's passage exists, quote ⊆ passage text, source not revoked, run revision == case revision, review (if any) bound to this revision. Fail → do not publish; trace `PUBLISH_BLOCKED` with reason.

## Field evidence requirements (`get_field_policy`)

| field_key | Required before CONSISTENT | If missing |
|---|---|---|
| `notification_number` | ≥1 `ACTIVE` `NOTIFICATION_DOC` with the same number | `INSUFFICIENT` — "No active notification document on file" → EvidenceRequest to seller |
| `responsible_company` | ≥1 `ACTIVE` `NOTIFICATION_DOC` naming the company | as above |
| `volume` | listing + (`PACKAGING_IMAGE` or `BRAND_PAGE`) same variant | `SINGLE_SOURCE` / `INSUFFICIENT` |
| `skin_type`, `key_ingredients` | listing + reference family | `SINGLE_SOURCE` / `INSUFFICIENT` |

This is why revocation matters even though the label still prints the number: after `SOURCE_REVOKED` on the notification doc, `notification_number` and `responsible_company` go STALE, then `INSUFFICIENT` with a request; `volume` and `skin_type` do not depend on that document and keep their result version.

## Review triggers (→ `NEEDS_REVIEW`)

- Any `CONFLICTING` result.
- `scope_match = UNKNOWN` on an identifier field.
- Any result that could reflect badly on a seller (`seller_attributable = true`).
- Manager proposed `PROPOSE_REVIEW`.
- A cited passage has scope `AGENT` (the agent placed a size-less passage in scope; code could not verify it).
- Every marketing-claim finding that is not consistent (`claim:*`).

Approval applies to `(result_id, case_revision)` only. A new revision supersedes the review (`SUPERSEDED`).

## Additional rules (`policy-v1` / `claims-rules-v2`; web rules `policy-v2`)

Rule ids are the ones the "Why?" panel shows (`RULE_NAMES` in `pipeline/policy.py`). Bump `POLICY_VERSION`
whenever a rule changes.

| Id | Rule | Decided by |
|---|---|---|
| R3 (inferred) | **Scope without metadata** (crawled pages): the product's own evidence (listing, label photo, notification, seller upload, registry record) is in scope; market from a 2-letter country-code web address; a page naming one size is in/out by that size, several sizes → passage level, none → product level. Known weakness: generic ccTLDs (`.co`, `.io`, `.ai`) look like markets (review M6). | code |
| R3p | **Passage-level scope** for a source covering several variants: a **code pre-pass** decides every passage that names a size (MATCH if every size it names is the variant, within 1%; else MISMATCH). Only passages that name no size and carry a claim for a waiting field go to the agent. | code, then agent |
| R3a | Agent says a size-less passage applies → stored as scope `AGENT`; usable, but every result citing it → `NEEDS_REVIEW`. The agent's "does not apply" is ignored. | agent proposes, human confirms |
| R3b *(contest, BR-05a)* | Agent placement whose anchor is a code-decided MATCH passage of the same variant → `MATCH`, `decided_by = AGENT_VERIFIED`; usable like a code decision. Invalid or missing anchor → R3a. | code verifies the agent |
| R7c | **Copy detection**: if every listing passage stating the field is a near-copy (5-char shingle Jaccard ≥ 0.8, passage ≥ 30 chars) of one reference source, the listing joins that source's family for this field → not an independent confirmation. | code |
| REQ | `notification_number` / `responsible_company` need an `ACTIVE` `NOTIFICATION_DOC` **or** an `ACTIVE` `REGISTRY_RECORD` (mock) among the cited sources. A revoked registry record → "the registry lists this notification number as revoked". | code |
| IMG | A field unreadable in an image (`readability = UNREADABLE`) → note + evidence request "a clearer photo of the label", kept open only while the field is unresolved. | code |
| Gaps | `NO_ACTIVE_NOTIFICATION_DOC` → gap controller (`pipeline/gaps.py`): join key (number read from the label) → MOCK registry lookup (≤ 2) → holder compared with the company → stop reason (`GAP_CLOSED`, …). Every hop decided by code. | code |
| Vocab | Open-set names (ingredients, skin-type phrases) start from `app/data/vocab_seed.json`; unknown ones are mapped by the model, phrase-checked by code and stored with provenance. **Asymmetric trust**: a `model` mapping may confirm a claim against a real INCI list but never raises a conflict; only `seed` / `reviewer` entries can. An unknown highlighted name that no reference INCI list contains is "unconfirmed" and set aside (R6). | model proposes, code verifies |
| CL | **Marketing claims vs INCI** (`claims-rules-v2`): the model finds and classifies claims (quote-checked); code judges. Free-from: seed INCI patterns → `CONFLICTING`; model-only family membership → `UNCERTAIN`. Concentration: an ingredient listed after one capped at ≤ 1% (`app/data/regulatory_limits.json`) is ≤ 1%. Treatment wording ("đặc trị", "trị mụn") → reviewer. All non-consistent findings are `NEEDS_REVIEW`; buyers see only a neutral count until a reviewer decides. Rules are a demo subset and need legal review per market. | model finds, code judges |
| R7w | **Web copies** (`policy-v2`): a `WEB_PAGE` whose passages stating the field are near-copies of another reference joins that reference's family. | code |
| R9w | **Retailer pages confirm, never accuse**: a `WEB_PAGE` that disagrees with the listing → `NEEDS_REVIEW` if other independent sources still agree, else `UNCERTAIN`; never `LISTING_VS_SOURCE`, never seller-attributable. Between references, a disagreeing retailer page is dropped with a note. | code |
| R4w | A `WEB_PAGE` stating several values for a field (e.g. every size it sells) is not used for that field; its highlight-vs-own-INCI mismatch is a note, not a finding. | code |
| R11+ | Publish gate also rejects forbidden wording in `public_text`; reviewer overrides pass the same checks (no citation → only `INSUFFICIENT`). | code |

For `claim:*` findings, P1 implements CL in `pipeline/policy.py` through the existing
`decide(field_key, observations, product, gaps, reviews) -> FieldDecision`; it alone assigns the final verdict,
`review_state`, rule trail and public text. P2's `claims_audit.audit(ctx, listing_obs, observations) -> list[FieldDecision]`
extracts, quote-validates and normalises findings to the existing `SourceObs`, delegates each claim key to `policy.decide`,
and returns its rows unchanged. The run remains public-field policy → claims audit (delegating claim policy) → publish
gate. CL is implemented by P1 and consumed by P2 in Phase 2; the Phase 1 audit hook is a no-op stub.

## Public text templates (no free-text from the model reaches the buyer)

| Label | Template |
|---|---|
| CONSISTENT | "Consistent across {n} independent sources checked: {sources}." |
| SINGLE_SOURCE | "Stated by {source} only; not independently confirmed." |
| CONFLICT_IN_SOURCE | "The {source} gives different {field} information in different sections. This is not attributed to the seller." |
| CONFLICTING | "The listing differs from {source} on {field}. Under review." |
| NOT_VERIFIED | "Not verified: {gap_reason}." |
| STALE | "A source this relied on changed on {date}. Re-checking." |

Forbidden words test: `genuine|authentic|fake|counterfeit|safe|certified|verified product|chính hãng|hàng giả|an toàn`.
