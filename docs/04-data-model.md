# 04 — Data model, enums, vocabulary

SQLite. All IDs are strings (`case_…`, `src_…`, `sv_…`, `psg_…`, `clm_…`, `res_…`, `run_…`). Timestamps are ISO-8601 UTC.

## Fields checked (demo)

| field_key | Type after normalisation | Notes |
|---|---|---|
| `volume` | `{value: float, unit: "ml" \| "g"}` | `fl oz` → ml (×29.5735); `473ml` == `473 ml` == `16 fl oz` (±1%) |
| `skin_type` | set of `SkinType` | Controlled vocabulary below |
| `key_ingredients` | set of `IngredientKey` (+ optional `%`) | Highlighted ingredients, **not** the full INCI |
| `inci_list` | ordered list of INCI names | Used to check "mentioned but absent" |
| `notification_number` | string, normalised (strip spaces, upper) | Synthetic case only; format `DEMO-CBMP-xxxxx` |
| `responsible_company` | string, normalised (casefold, strip legal suffix) | Synthetic case only |

`SkinType`: `DRY`, `NORMAL`, `OILY`, `COMBINATION`, `SENSITIVE`, `ACNE_PRONE`, `ALL`.
Mapping examples: "da khô" / "dry skin" → `DRY`; "da thường đến da dầu" / "normal to oily" → `{NORMAL, OILY}`; "mọi loại da" / "all skin types" → `ALL`.
`ALL` is compatible with any set; `{DRY}` vs `{NORMAL, OILY}` is a conflict.

`IngredientKey` (demo list): `CERAMIDES`, `HYALURONIC_ACID`, `NIACINAMIDE`, `SALICYLIC_ACID`, `GLYCERIN`, `ZINC`. Synonyms table in `normalize.py` (e.g. "Ceramide NP/AP/EOP" → `CERAMIDES`, "BHA" → `SALICYLIC_ACID`).

## Enums (orthogonal, stored)

| Enum | Values |
|---|---|
| `Verdict` | `CONSISTENT`, `CONFLICTING`, `SINGLE_SOURCE`, `INSUFFICIENT`, `UNCERTAIN`, `NOT_APPLICABLE` |
| `ConflictLocus` (when CONFLICTING) | `WITHIN_SOURCE`, `ACROSS_SOURCES`, `LISTING_VS_SOURCE` |
| `ScopeMatch` | `MATCH`, `MISMATCH`, `UNKNOWN` |
| `Freshness` | `CURRENT`, `STALE`, `UNKNOWN` |
| `Readability` | `READABLE`, `PARTIAL`, `UNREADABLE` |
| `ReviewState` | `AUTO_DRAFT`, `NEEDS_REVIEW`, `REVIEWED`, `SUPERSEDED` |
| `EvidenceLevel` | `LISTING`, `PRODUCT_VERSION`, `BATCH`, `UNIT` (demo: LISTING / PRODUCT_VERSION only) |
| `DatasetOrigin` | `REAL`, `SYNTHETIC` (+ trace flag `REPLAY`) |
| `SourceKind` | `LISTING`, `BRAND_PAGE`, `NOTIFICATION_DOC`, `PACKAGING_IMAGE`, `SELLER_UPLOAD`, `REGISTRY_RECORD` (added in Phase 5: a lookup in the MOCK registry becomes a cited source), `WEB_PAGE` (Phase 8: a non-official page found by web search and snapshotted by code; confirms only) |
| `SourceStatus` | `ACTIVE`, `SUPERSEDED`, `REVOKED`, `UNAVAILABLE` |
| `RunStatus` | `QUEUED`, `RUNNING`, `COMPLETED`, `PARTIAL`, `WAITING_EVIDENCE`, `WAITING_REVIEW`, `FAILED`, `CANCELLED` |
| `Role` | `BUYER`, `SELLER`, `REVIEWER`, `OPERATOR`, `SYSTEM` |
| Passage scope (`passage_scopes.scope_match`) | `MATCH`, `MISMATCH`, `UNKNOWN`, **`AGENT`** — the agent proposed that a passage naming no size applies; usable, but every result citing it is `NEEDS_REVIEW`. `decided_by` = `CODE` (pre-pass) / `LIVE` / `REPLAY` / `FIXED_WORKFLOW` **Contest (PROPOSAL BR-05a):** a placement whose anchor is a code-decided MATCH of the same variant is stored as `MATCH` with `decided_by = AGENT_VERIFIED` and counts like a code decision; without a valid anchor it stays `AGENT` → `NEEDS_REVIEW`. |
| Vocabulary provenance (`vocab.by`) | `seed` (`app/data/vocab_seed.json`), `model` (learned at run time), `reviewer` — only `seed`/`reviewer` may raise a conflict (AGENTS.md rule 14) |

## Buyer label mapping (UI only)

Evaluate top to bottom, first match wins:

| Condition | Buyer label | Sub-text |
|---|---|---|
| `freshness = STALE` | **Stale** | "A source this relied on changed on {date}. Re-checking." |
| no result yet / run RUNNING | **Not checked yet** / **Updating** | — |
| `CONFLICTING` + `WITHIN_SOURCE` | **Conflict in source** | "The brand page says different things. Not attributed to the seller." |
| `CONFLICTING` (other loci) | **Conflicting** | "Sources disagree. Under review." |
| `SINGLE_SOURCE` | **Single source** | "Stated by {source} only; not independently confirmed." |
| `CONSISTENT` | **Consistent** | "Consistent across {n} sources checked." |
| `INSUFFICIENT` / `UNCERTAIN` | **Not verified** | "{gap.reason}" |
| run FAILED | **Could not update** | "This says nothing about the product." |

## Tables

```text
products(id, name, brand, variant, market, dataset_origin)
cases(id, product_id, tenant_id, revision INT, material_revision INT, status, dataset_origin, created_at)
sources(id, case_id NULL, product_id, kind SourceKind, uri, owner, visibility PUBLIC|PRIVATE, family, status SourceStatus)
source_versions(id, source_id, version INT, captured_at, sha256, raw_path, is_current BOOL)
passages(id, source_version_id, locator, section, text)               -- FTS5 virtual table passages_fts(text)
claims(id, source_version_id, passage_id, field_key, raw_value, normalized_json, scope_json,
       readability, extractor_model, prompt_version, created_at)
field_results(id, case_id, field_key, result_version INT, case_revision INT,
              verdict, conflict_locus NULL, scope_match, freshness, review_state, evidence_level,
              seller_attributable BOOL, citations_json, depends_on_json, public_text, policy_version,
              run_id, created_at, superseded_by NULL)
gaps(id, case_id, field_key, missing_kind, needed_doc, known_ids_json, tried_json, status)
evidence_requests(id, case_id, field_key, gap_id, reason, requested_from SELLER|BRAND, status, created_at)
review_tasks(id, case_id, field_key, result_id, reason_code, status)
reviews(id, case_id, result_id, case_revision, reviewer_id, decision APPROVE|OVERRIDE|REJECT, reason, override_json, created_at)
events(id, idempotency_key UNIQUE, type, producer, resource_id, resource_version, payload_json,
       received_at, outcome ADMITTED|NOOP|DUPLICATE|REJECTED, reason)
runs(id, case_id, case_revision, trigger_event_id, status, stop_reason, model, prompt_version, policy_version,
     llm_mode LIVE|REPLAY, budget_json, usage_json, started_at, finished_at)
trace_steps(id, run_id, seq, step, actor code|llm|human, input_refs, output_refs, latency_ms, tokens_in, tokens_out, error)
```

### Extended schema — extra columns and tables

The list above is the core. Build these from the start if the matching feature is in scope:

```text
-- extra columns
products(+ version, listing_id)            sources(+ dataset_origin)          source_versions(+ scope_json)
claims(+ quote; extractor instead of extractor_model; no scope_json — scope is per source version / passage)
field_results(+ notes_json, explain_json            -- decision trail for "Why?"
              + stale_reason, stale_at              -- set by admission on a dependent source event
              + confirmed_run_id, confirmed_at      -- same decision re-confirmed by a later run (no new version)
              + reviewed_by
              + prev_hash, chain_hash, chain_seq)   -- hash chain per case (hash only immutable columns)
events(+ event_id, run_id)                 runs(+ error, created_at)          gaps(+ run_id, created_at)
trace_steps(+ detail JSON, created_at, t_ms)        -- t_ms = offset from run start (waterfall)

-- extra tables
passage_scopes(source_version_id, passage_id, scope_match, reason, decided_by, run_id, created_at)   -- PK(sv, passage)
extraction_cache(source_version_id, prompt_version, extractor, extraction_json, ignored_instructions, created_at)
vocab(field, surface, value_json, by, model, created_at)          -- learned vocabulary, PK(field, surface)
ocr_lines(source_version_id, idx, text, x0, y0, x1, y1, conf, w, h)   -- code OCR boxes on label images
marketplace_findings(product_id, scan_id, seller_source_id, shop, field_key, value_json, display, cluster, outlier,
                     citation_json, created_at)                    -- other sellers' listings, outside the case
orders(id, product_id, case_id, buyer_id, placed_at, case_revision, snapshot_json, snapshot_hash, chain_head)
web_searches(id, case_id, run_id, query, provider, mode, results_json, credits, created_at)
                                                                   -- Phase 8: every query, result, domain class and decision
products(+ web_json)                                              -- {enabled, brand_domains} for web discovery
                                                                   -- evidence receipt at purchase
passages_fts(text, passage_id, source_version_id)                  -- FTS5 virtual table
```

## Dependencies (`depends_on_json`)

Each `FieldResult` lists the `(source_id, source_version_id)` pairs it used. Invalidation query: on event for `source_id` → all current results whose `depends_on` contains it → `freshness = STALE`.

Example for the synthetic brand: `notification_number` and `responsible_company` depend on `src_demo_notification`; `volume` depends on listing + packaging only → unaffected by revoke.
