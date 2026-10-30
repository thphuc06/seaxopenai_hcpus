# 05 — Contracts (code against these)

Paste this file into the first Codex task on contest day. Names here are binding; see [04-data-model.md](04-data-model.md) for enums.

## 1. Event envelope — `POST /internal/events`

```json
{
  "event_id": "evt_0001",
  "idempotency_key": "listing:demo-lst-01:v2",
  "type": "BOOTSTRAP | LISTING_CHANGED | SOURCE_CHANGED | EVIDENCE_ADDED | SOURCE_REVOKED",
  "schema_version": "1",
  "producer": "publisher-panel",
  "resource": {"kind": "LISTING | SOURCE | CASE", "id": "demo-lst-01", "version": 2},
  "changed_fields": ["price"],
  "payload": {},
  "occurred_at": "2026-10-24T09:00:00Z",
  "correlation_id": "demo-run-1"
}
```

Response: `{"event_id", "outcome": "ADMITTED|NOOP|DUPLICATE|REJECTED", "reason", "job_id": null|"job_…", "stale_fields": ["notification_number", ...]}`

Admission rules (code, in order):
1. `producer` in allowlist and role `OPERATOR|SYSTEM|SELLER` for that type → else `REJECTED`.
2. `idempotency_key` seen → `DUPLICATE` (no side effects).
3. `LISTING_CHANGED` with `changed_fields ⊆ {price, stock, promo}` → `NOOP`.
4. Find dependent results → mark STALE (for `SOURCE_CHANGED`, `SOURCE_REVOKED`, material `LISTING_CHANGED`).
5. Bump `case.revision`; enqueue one job per case (coalesce: if a job for the same case is QUEUED, update its target revision instead of adding another).

## 2. REST API

All paths below are served under the `/api` prefix (e.g. `GET /api/products/{id}/passport`). Phase 1 also adds `GET /products`, `GET /internal/events/catalog`, `POST /internal/demo/fire/{name}` (submit a fixture event), `GET /internal/events/log` and `GET /internal/runs`.

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/products/{product_id}/passport` | any | Read-only. Returns latest public results. Never enqueues. |
| GET | `/products/{product_id}/fields/{field_key}/evidence` | any | Public passages only for BUYER; all for REVIEWER |
| POST | `/internal/events` | OPERATOR, SYSTEM | Envelope above |
| POST | `/cases/{case_id}/evidence` | SELLER, REVIEWER | Upload text/image → new source version → emits `EVIDENCE_ADDED` |
| GET | `/review/queue` | REVIEWER | Open review tasks |
| POST | `/cases/{case_id}/reviews` | REVIEWER | `{result_id, case_revision, decision, reason, override?}`; 409 if `case_revision` ≠ current |
| GET | `/cases/{case_id}/history` | REVIEWER | Result versions, events, reviews |
| GET | `/internal/runs/{run_id}` | OPERATOR, REVIEWER | Run + trace steps |
| GET | `/internal/metrics` | OPERATOR | Counters: events by outcome, jobs, model calls, tokens, est. cost |
| POST | `/internal/demo/reset` | OPERATOR | Reload fixtures (demo only) |

Extended routes (design). Run and event routes live under `/internal` (`/internal/runs`, `/internal/metrics`,
`/internal/demo/reset`, `/internal/events`).

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/products/{product_id}/fields/{field_key}/explain` | any (filtered) | Decision path: trigger event → source snapshots (hash) → claims → policy rules → verdict → publish gate → reviews. Private sources and reviews only for REVIEWER/OPERATOR |
| GET | `/sources/{source_version_id}/image` | any (filtered) | Label image of a `PACKAGING_IMAGE` source; `?as_role=` because `<img>` cannot send headers |
| GET | `/cases/{case_id}/search?q=&mode=` | REVIEWER, OPERATOR | "Ask the evidence": hybrid retrieval (BM25 + embeddings → RRF → rerank) over the case's usable sources; returns passages and every stage, never an answer |
| GET | `/cases/{case_id}/chain` | REVIEWER, OPERATOR | Recompute the result hash chain → `{valid, rows, head \| broken_at}` |
| GET | `/cases/{case_id}/graph` | REVIEWER, OPERATOR | Sources → fields that depend on / cite them (dependency view) |
| POST | `/orders` | any (buyer) | Freeze the buyer-visible Passport into an evidence receipt (snapshot + hash + chain head) |
| GET | `/orders`, `/orders/{order_id}` | any | Receipt, plus a diff "then vs now" per field |
| GET | `/products/{product_id}/marketplace` | any (filtered) | Other sellers' listings: tally by independent clusters for buyers; shops, quotes, clusters, outliers for REVIEWER |
| POST | `/internal/marketplace/{product_id}/scan` | OPERATOR | Ingest other sellers' listings (outside the case; never changes the Passport) |
| GET | `/internal/runs` | OPERATOR, REVIEWER | Recent runs with `usage` (model calls incl. agent requests, tokens) |
| GET | `/internal/runs/{run_id}/otel` | OPERATOR, REVIEWER | OTLP/JSON spans, OpenTelemetry GenAI conventions (`invoke_agent`, `execute_tool`, `chat`), content capture off |
| GET | `/internal/observability` | OPERATOR, REVIEWER | Live counters: verdicts, model calls live/replayed/avoided, by step, publish gate, agent stops, gap stops, learned vocabulary |
| GET | `/internal/eval/metrics` | OPERATOR, REVIEWER | Latest offline scorecard written by `scripts/metrics.py` |
| POST | `/cases/{case_id}/web-search` | OPERATOR | Phase 8: admits a `WEB_SEARCH_REQUESTED` event (idempotency key = case + revision); the run searches, snapshots pages, re-assesses |
| GET | `/cases/{case_id}/web-search` | REVIEWER, OPERATOR | Audit: queries → results (domain, class, score, decision, reason) and stored snapshots (url, sha256, captured_at, passages) |

Reviewer `OVERRIDE` goes through the same publish rules as a run: forbidden wording → 422; a verdict other than
`INSUFFICIENT` without a stored citation → 422 `NO_CITATION` (fixed after the 2026-10-24 review).

Role is sent as header `X-Demo-Role: BUYER|SELLER|REVIEWER|OPERATOR` and `X-Demo-Actor: <id>` (simulated auth; backend checks it on every route).

### Passport response

```json
{
  "product_id": "demo-prod-01",
  "dataset_origin": "SYNTHETIC",
  "last_checked_at": "2026-10-24T09:01:12Z",
  "run_status": "COMPLETED",
  "fields": [
    {
      "field_key": "skin_type",
      "label": "CONFLICT_IN_SOURCE",
      "public_text": "The brand page says different things about skin type. Not attributed to the seller.",
      "verdict": "CONFLICTING",
      "conflict_locus": "WITHIN_SOURCE",
      "freshness": "CURRENT",
      "review_state": "NEEDS_REVIEW",
      "checked_at": "2026-10-24T09:01:12Z",
      "citations": [
        {"passage_id": "psg_12", "source_kind": "BRAND_PAGE", "source_version": 1, "locator": "title", "excerpt": "...dry skin..."},
        {"passage_id": "psg_14", "source_kind": "BRAND_PAGE", "source_version": 1, "locator": "description#p2", "excerpt": "...normal to oily..."}
      ]
    }
  ],
  "disclaimer": "Describes what the checked sources say. Not a certification of authenticity or safety."
}
```

## 3. LLM extraction schema (Pydantic, strict)

```python
class ExtractedClaim(BaseModel):
    field_key: Literal["volume", "skin_type", "key_ingredients", "inci_list",
                       "notification_number", "responsible_company"]
    raw_value: str | None          # verbatim text, None if unreadable
    passage_id: str                # must be one of the passage ids given in the prompt
    quote: str | None              # exact substring of that passage
    readability: Literal["READABLE", "PARTIAL", "UNREADABLE"]
    # model proposes normalised value; code re-normalises and wins on disagreement
    proposed_skin_types: list[Literal["DRY","NORMAL","OILY","COMBINATION","SENSITIVE","ACNE_PRONE","ALL"]] | None
    proposed_ingredients: list[str] | None
    proposed_volume_ml: float | None

class ClaimExtraction(BaseModel):
    source_version_id: str
    claims: list[ExtractedClaim]
    ignored_instructions_detected: bool   # true if source text tried to instruct the model
```

Validation in code after parse: `passage_id` exists in this source version; `quote` is a substring of passage text (after whitespace normalisation) → else drop the claim and log `INVALID_LOCATOR`.

## 4. Manager action (Agents SDK `output_type`)

```python
class ManagerAction(BaseModel):
    action: Literal["RETRIEVE_EVIDENCE", "REEXTRACT", "COMPARE_SEMANTIC",
                    "REQUEST_EVIDENCE", "PROPOSE_COMPLETE", "PROPOSE_REVIEW"]
    field_key: str
    gap_id: str | None
    question: str            # narrow question, e.g. "Which skin type does this exact variant target?"
    reason: str              # one sentence, stored in trace
    expected_output: str
```

The server adds tenant, actor, case, ACL and budget from `CaseContext`. The model never supplies them.

**Known risk:** `output_type` may fail on models that prefix a reasoning block. Fallback: end the Manager with a typed
`submit_action(action, reason)` tool and the specialist with `submit_evidence_bundle(...)`, both with `StopAtTools`.
Actions offered: `PROPOSE_COMPLETE | PROPOSE_REVIEW | REQUEST_EVIDENCE`. `smoke.py` decides which one to use.

## 5. Tools (function tools; all go through `tools.gate()` = ACL + budget + timeout + trace)

| Tool | Args (model-provided) | Returns |
|---|---|---|
| `get_case_context` | — | scope, fields, current results, open gaps |
| `search_brand_corpus` | `query: str`, `field_key: str` | passages filtered by server to the case's product/market/version |
| `read_source_region` | `passage_id: str` | passage text + neighbours |
| `compare_exact_fields` | `field_key: str` | code comparison result |
| `compare_semantic_claims` | `claim_ids: list[str]` | proposed relation `SUPPORTS|CONTRADICTS|UNRELATED` + passage ids (proposal only) |
| `get_field_policy` | `field_key: str` | evidence requirements |
| `propose_evidence_request` | `field_key, needed_doc, reason` | request draft (app validates before writing) |
| `propose_review_case` | `field_key, reason` | review task draft |
| `retrieve_product_evidence` | `question, field_key` | **retrieval specialist** via `as_tool` → `EvidenceBundle` |

Tool result envelope:

```json
{"status": "OK|PARTIAL|NOT_FOUND|ACCESS_DENIED|SOURCE_UNAVAILABLE|INVALID_INPUT|BUDGET_EXCEEDED",
 "data": {}, "refs": ["psg_12"], "warnings": [], "retryable": false, "usage": {}}
```

`NOT_FOUND` means "not found in the current search scope", never "does not exist".

## 6. EvidenceBundle (retrieval specialist output)

```python
class EvidencePassage(BaseModel):
    passage_id: str
    source_id: str
    source_version: int
    locator: str
    excerpt: str
    stance: Literal["SUPPORTS", "CONTRADICTS", "MENTIONS", "UNCLEAR"]

class EvidenceBundle(BaseModel):
    question: str
    queries_tried: list[str]
    passages: list[EvidencePassage]
    fields_covered: list[str]
    fields_missing: list[str]
    stop_reason: Literal["ENOUGH", "NO_NEW_INFO", "NO_VALID_SOURCE", "BUDGET", "REPEATED_QUERY"]
```

## 7. Budget (in `CaseContext`, shared across Manager + specialist)

```python
@dataclass
class Budget:
    manager_turns: int = 3
    retrieval_hops: int = 2
    model_calls: int = 10
    tool_calls: int = 16
    deadline_s: float = 75.0
```

Exceeding any limit → tool returns `BUDGET_EXCEEDED`; harness stops the loop → run `PARTIAL`, `stop_reason="BUDGET"`.

**Budget scope (design requirement):** one `Budget` per run covers every model call (extraction, vocabulary, claim
audit and agent), with a hard deadline, and the run ends `PARTIAL` + `stop_reason` on exhaustion. Count the agent's
submit turn in `max_turns`. Estimate: the demo story needs roughly 30 model calls in total, so decide the per-run
number before coding.
