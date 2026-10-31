# 06 — Policy rules (`policy-v1`)

Implemented in `pipeline/policy.py`. Pure functions: `(claims, scope, sources, gaps, reviews) -> FieldResult`. No model calls. Bump `POLICY_VERSION` on any change and note it in [tracking/DECISIONS.md](tracking/DECISIONS.md).

## Ordered rules (per field)

1. **Access.** Drop passages the current role cannot see. Never leak another case/tenant's documents.
2. **Validity.** Drop claims from sources with status `REVOKED` / `SUPERSEDED` from current conclusions (keep in history). If a field's only supporting source was revoked → `INSUFFICIENT`, `freshness = CURRENT` after re-assessment (STALE until re-assessed).
3. **Scope.** Claim scope (product, variant, market, version) must match the case. Unknown → `scope_match = UNKNOWN`, verdict at most `UNCERTAIN`. Mismatch → claim excluded, reason recorded.
4. **Self-conflict first.** Within one source version, if two passages give incompatible values for the same field → `CONFLICTING`, `conflict_locus = WITHIN_SOURCE`, `seller_attributable = false`, `review_state = NEEDS_REVIEW`. That source is not used to judge the listing for this field.
5. **Compare.** Same field, normalised values:
   - volume: equal within 1% → compatible.
   - skin_type: **directional**. A listing claim is supported when the reference says `ALL`, or when the claim's types ⊆ the reference's types; a listing saying `ALL` is **not** supported by a page saying `{DRY}`. Two references (neither is "the claim", e.g. two sections of one page) agree if either direction holds. Normalisation follows docs/04 and DATASET-SPEC §6; `{DRY}` vs `{NORMAL, COMBINATION, OILY}` → incompatible.
   - key_ingredients: listing ingredient ⊆ reference highlights ∪ reference INCI → compatible. Highlighted ingredient absent from the **same source's** INCI → within-source conflict.
   - identifiers (notification number, company): exact after normalisation.
6. **Not mentioned ≠ negated.** A source that does not mention a value is not evidence against it. Highlight list ≠ full INCI.
7. **Independence.** Count independent source **families** that state the value, the listing included (brand page and a seller copy of the brand page = one family). One family → `SINGLE_SOURCE` with text "Stated by {source} only" (e.g. Blemish 2% salicylic acid: brand page only; DEMO skin type: listing only).
8. **Consistent.** ≥2 independent families, all compatible, scope MATCH → `CONSISTENT` ("consistent across the sources checked").
9. **Conflict across sources.** Listing vs reference incompatible → `CONFLICTING`, `LISTING_VS_SOURCE`, `NEEDS_REVIEW` (a human decides before anything reflects on the seller).
10. **Missing.** No usable claim → `INSUFFICIENT` + a `Gap` (field, missing kind, needed doc, known ids) → `EvidenceRequest` if a party can supply it.
11. **Publish gate** (`publish.py`): every citation's passage exists, quote is contiguous in passage text using the shared NFC + whitespace check in docs/05 §3, source not revoked, run revision == case revision, review (if any) bound to this revision. Fail → do not publish; trace `publish:blocked` with reason.

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
| R3a | Without a valid anchor, YES → scope `AGENT` (usable, every result citing it → `NEEDS_REVIEW`); NO/UNSURE → `UNKNOWN`, never exclusion based only on the agent's assertion. | agent proposes, human confirms |
| R3b *(contest, BR-05a)* | Code checks that the anchor is the nearest preceding size-naming passage in the same source version and section/table group, with no intervening size heading. YES + code-decided MATCH anchor → `MATCH`; NO + code-decided MISMATCH anchor → `MISMATCH`; both stored with `decided_by = AGENT_VERIFIED`. Invalid/missing anchor or UNSURE → R3a. The agent cannot overwrite pre-pass decisions. | code verifies the agent |
| R7c | **Copy detection**: if every listing passage stating the field is a near-copy (5-char shingle Jaccard ≥ 0.8, passage ≥ 30 chars) of one reference source, the listing joins that source's family for this field → not an independent confirmation. | code |
| REQ | `notification_number` / `responsible_company` need an `ACTIVE` `NOTIFICATION_DOC` **or** an `ACTIVE` `REGISTRY_RECORD` (mock) among the cited sources. A revoked registry record → "the registry lists this notification number as revoked". | code |
| IMG | A field unreadable in an image (`readability = UNREADABLE`) → note; request "a clearer photo of the label" while that field is unresolved. This signal does not erase readable evidence from other active sources. `INSUFFICIENT` requires that no usable support remains for the field. | code |
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

## As built (contest)

S2 integration correction: policy-v1.6 records version-bound passage scope in the
claims auditor and the sourced broad hyaluronate ingredient-family mapping. The
auditor calls the existing scope helper for each passage; MISMATCH is excluded,
UNKNOWN/AGENT stays unresolved and policy retains its UNCERTAIN/review handling.
No model chooses a verdict. Gift quantities removed at extraction still receive
the existing scope_check exclusion reason and passage reference.

Current version is policy-v1.5 after integrating P2 S2. P2's regulatory table is a list
whose rows are explicitly provisional (status=verify) and qualified by use/market. It is
treated as unavailable for automated concentration contradiction, rather than causing a
mapping-shape error or silently promoting provisional limits into facts. Concentration stays
UNCERTAIN/NEEDS_REVIEW with a verification note. The earlier numeric-map contract remains
supported; activating the row table requires a reviewed applicability contract with P2/P4.
CCR P1→P4: record v1.5 as the current version, preserving v1.4's R2 changes below.
For an unreadable-only field, the IMAGE gap reason includes the replacement action (provide
a clearer photo of the label), so the persisted seller evidence request is actionable as well
as its needed_doc. Readable support is still retained without opening an unnecessary gap.

S2 REAL follow-up advances POLICY_VERSION to policy-v1.4. Volume scope examines stored
passage text using source-noted gift cues in data/scope_text_rules.json (explicitly approved
P1 ownership exception). A single quantity after a cue within a clause is gift-context
MISMATCH; multiple quantities there, or the same value appearing in both main and gift
contexts, remain UNKNOWN. Negated, conditional purchase, gift-container and unresolved
suffix-cue wording also remain UNKNOWN using curated indirect cues and existing negation
rules. A page naming only gift quantities does not acquire product-level MATCH by omission.
Main quantities before the cue or in separate clauses remain
eligible. Source size inference excludes only unambiguous gift quantities. Unknown wording
is not resolved by picking whichever quantity matches the case. Existing normalization,
unit conversion and tolerance remain P2/compare helpers; no duplicate size parser is added.
Trace scope_check records GIFT_CONTEXT/AMBIGUOUS_VOLUME_CONTEXT and policy R3 filters scope.

For skin-type comparisons, a shorter source summary does not negate a fuller, compatible
statement in the same source version. R4 still checks within-source contradictions first;
R9 accepts the fuller code/seed evidence only from that same version, and the final citations
include supporting passages. Another source or an unverified model mapping cannot suppress
the disagreement. CCR P1→P4: record policy-v1.4 and the trace-debug loop in tracking docs.

S2 P1 advances POLICY_VERSION to policy-v1.3 (v1.2 plus the approved MODEL_ERROR rule). Pure scope inference and stored passage
placements feed SourceObs; R7c joins copied listing passages with their reference family.
The run supplies stored full passage text for copy comparison, while citations retain the
validated extracted excerpts. Revoke admission changes only dependent freshness; the next
run preserves unaffected result versions. The first trace step records stale:mark with zero
model calls. Budget exhaustion with zero published results is PARTIAL.

Human decision at S2: a typed model error before any validated claim returns PARTIAL,
preserves stop_reason/error, and publishes five INSUFFICIENT findings with MODEL_ERROR
gaps and no citations. A failure after some sources preserves only code-verified findings;
it does not invent claims for unassessed fields. The old test_run expectations were explicitly
approved for this update; unrelated error expectations remain unchanged. The auxiliary
pre-wiring copy assertion was also approved for SINGLE_SOURCE plus an explicit R7c trail.
During revoke reassessment, this rule applies only to affected fields. Unaffected CURRENT
findings are revalidated through publish.py and retain their result IDs, versions and policy
trails, with current-revision confirmation and replacement review tasks where needed.
Exception: a prior revision's human approval expires. Policy returns NEEDS_REVIEW and a
REVIEW/SUPERSEDED trail; publish creates a new result version, retaining the historical
REVIEWED row and its citations. An unrelated source event cannot carry human approval
into the new revision without another review.

Reviewer state decisions remain in policy; publish.py validates and atomically stores the
revision-bound result, citations, rebuilt dependencies and review record. Unresolved evidence
requests stay OPEN; only a resolved field fulfills them. Claim rules reject unreadable/empty
INCI evidence, cap unknown scope, and use seed provenance for adverse family matches. Model
membership alone cannot accuse. Concentration compares ordered INCI items using P2-owned
regulatory_limits.json (flat ingredient-to-number mapping or a limits object); absent data
leaves UNCERTAIN with a note. The <=1% ordering boundary never implies a smaller cap.
Normalized concentration claims use ingredient plus percent (claimed_percent accepted).
All non-consistent claim findings require review; buyers receive only a neutral pending count.
CCR P1→P4: record policy-v1.3 in tracking/DECISIONS.md. CCR P1→P2: align normalized claim keys
free_from/concentration/treatment and supply the sourced regulatory mapping before S2 gate.

S1 P1 implements `policy-v1.1`: normalized comparison, ordered R1–R11, active notification requirement,
family independence, value-led templates, citation dependencies and rule trails. `SourceObs` carries stored
source/version/passage identity, kind/family/status/visibility/scope, normalized field value, quote and mapping
provenance; optional case/tenant/access fields permit explicit access filtering. Only policy chooses verdict,
review state and freshness. P2 remains the sole normalization/extraction implementation.

Reference/reference disagreement uses ACROSS_SOURCES; listing/reference disagreement uses LISTING_VS_SOURCE.
Self-conflict takes precedence once access, validity and scope have been checked. UNKNOWN scope caps the result
at UNCERTAIN. Positive highlight passages combine within a source; a partial highlight list is not a negation.
Empty normalized sets do not support a finding. A model mapping cannot create a conflict. Notification documents
enter only their dependent identifier fields; unrelated fields do not acquire those dependencies.

Publication validates every citation and dependency against stored evidence and case identity, checks contiguous
NFC/whitespace-normalized quotes, rejects inactive/superseded evidence and forbidden public text, and compares
the stored pinned revision with the current case revision atomically. Blocked decisions create no result or gap.
Identical decisions may be confirmed without a new result version. REQ accepts NOTIFICATION_DOC in S1;
registry, copy inference, claim-family and web rules remain in their scheduled later phases.

CCR P1→P4: record this version and the explicit reference/reference locus in tracking/DECISIONS.md.
