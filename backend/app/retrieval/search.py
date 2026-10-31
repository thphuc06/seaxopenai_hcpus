"""Case-filtered lexical/dense ranking. No publication or verdict decisions."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import logging
import math
import re
import unicodedata

from pydantic import JsonValue, ValidationError

from app import config, db
from app.budget import BudgetExceeded
from app.context import RunContext
from app.llm import embed
from app.llm.client import LLMError
from app.models import ScopeMatch
from app.pipeline.scope import infer_scope

logger = logging.getLogger(__name__)
_context: ContextVar[RunContext | None] = ContextVar("retrieval_run_context", default=None)


@dataclass
class SearchResult:
    hits: list[dict[str, JsonValue]]
    stages: dict[str, list[dict[str, JsonValue]]]


@dataclass(frozen=True)
class Passage:
    id: str
    sv_id: str
    locator: str
    section: str
    text: str
    header: str
    position: int
    scope: str
    kind: str
    origin: str

    @property
    def content(self) -> str:
        return self.header + "\n" + self.text

    def payload(self) -> dict[str, JsonValue]:
        return {"passage_id": self.id, "source_version_id": self.sv_id, "locator": self.locator,
                "section": self.section, "text": self.text, "header": self.header, "scope_match": self.scope,
                "source_kind": self.kind, "dataset_origin": self.origin}


@contextmanager
def run_context(ctx: RunContext) -> Iterator[None]:
    """Bind server-owned context at an authorized run boundary, never model args."""
    token = _context.set(ctx)
    try:
        yield
    finally:
        _context.reset(token)


def _authorize(case_id: str) -> None:
    ctx = _context.get()
    if ctx is None:
        return  # Read-only callers enforce the existing route's role ACL.
    with closing(db.connect()) as connection:
        case = connection.execute("SELECT tenant_id FROM cases WHERE id=?", (case_id,)).fetchone()
    if ctx.case_id != case_id or case is None or case["tenant_id"] != ctx.tenant_id:
        raise PermissionError("ACCESS_DENIED")


def _corpus(case_id: str, allowed_sv_ids: list[str] | None) -> list[Passage]:
    """Load current ACTIVE versions, then reuse the scope owner's rules."""
    with closing(db.connect()) as connection:
        product_row = connection.execute(
            "SELECT p.* FROM products p JOIN cases c ON c.product_id=p.id WHERE c.id=?", (case_id,)).fetchone()
        if product_row is None:
            return []
        product = dict(product_row)
        rows = connection.execute(
            "SELECT s.*, v.id AS source_version_id, v.scope_json FROM sources s "
            "JOIN source_versions v ON v.source_id=s.id "
            "WHERE s.case_id=? AND s.status='ACTIVE' AND v.is_current=1 ORDER BY v.id", (case_id,)).fetchall()
        allowed = None if allowed_sv_ids is None else set(allowed_sv_ids)
        result: list[Passage] = []
        for row in rows:
            sv_id = row["source_version_id"]
            if allowed is not None and sv_id not in allowed:
                continue
            passages = [dict(p) for p in connection.execute(
                "SELECT * FROM passages WHERE source_version_id=? ORDER BY rowid", (sv_id,))]
            source = dict(row)
            source["passages"] = passages
            source["passage_scopes"] = [dict(p) for p in connection.execute(
                "SELECT * FROM passage_scopes WHERE source_version_id=?", (sv_id,))]
            scope = infer_scope(source, product)
            for index, passage in enumerate(passages):
                match = scope.for_passage(passage["id"]).scope_match
                if match == ScopeMatch.MISMATCH:
                    continue
                section = passage["section"] or ""
                header = "[" + " | ".join(str(v or "") for v in (
                    row["kind"], product["name"], product["market"], product["variant"], section)) + "]"
                result.append(Passage(passage["id"], sv_id, passage["locator"], section,
                                      passage["text"], header, index, match.value, row["kind"], row["dataset_origin"]))
    return result


def tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return re.findall(r"[^\W_]+", "".join(c for c in folded if not unicodedata.combining(c)))


def bm25(passages: list[Passage], query: str) -> list[tuple[str, float]]:
    terms = set(tokens(query))
    documents = [Counter(tokens(p.content)) for p in passages]
    if not documents or not terms:
        return []
    average = sum(sum(doc.values()) for doc in documents) / len(documents) or 1.0
    frequency = Counter(term for doc in documents for term in doc)
    scores: list[tuple[str, float]] = []
    for passage, doc in zip(passages, documents):
        length = sum(doc.values())
        score = sum(math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                    * doc[term] * 2.2 / (doc[term] + 1.2 * (0.25 + 0.75 * length / average))
                    for term in terms if doc[term])
        if score > 0:
            scores.append((passage.id, score))
    return sorted(scores, key=lambda item: (-item[1], item[0]))


def rrf(*rankings: list[tuple[str, float]]) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (passage_id, _) in enumerate(ranking, 1):
            scores[passage_id] = scores.get(passage_id, 0.0) + 1.0 / (60 + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def _cached(passage: Passage) -> list[float] | None:
    with closing(db.connect()) as connection:
        row = connection.execute(
            "SELECT vector_json FROM embeddings WHERE model=? AND content_hash=? ORDER BY passage_id LIMIT 1",
            (config.settings.embed_model, embed.cache_identity(passage.content))).fetchone()
    if row is None:
        return None
    return embed.validate_vector(json.loads(row[0]))


def index_source_version(sv_id: str) -> None:
    """Store already persists lexical text. Dense indexing requires a bound run."""
    with closing(db.connect()) as connection:
        row = connection.execute("SELECT s.case_id FROM sources s JOIN source_versions v ON v.source_id=s.id WHERE v.id=?",
                                 (sv_id,)).fetchone()
    if row is None or row["case_id"] is None:
        return
    _authorize(row["case_id"])
    ctx = _context.get()
    if ctx is None or ctx.mode == "fallback":
        reason = "FALLBACK" if (ctx.mode if ctx else config.settings.llm_mode) == "fallback" else "RUN_CONTEXT_REQUIRED"
        logger.info("BM25 only: %s; source_version=%s", reason, sv_id)
        if ctx is not None:
            ctx.trace.step("retrieval:index", detail={"mode": "BM25 only", "reason": reason}, input_refs=[sv_id])
        return
    passages = _corpus(row["case_id"], [sv_id])
    try:
        _index_passages(passages, ctx)
    except (LLMError, BudgetExceeded, ValueError) as error:
        # The source is already committed. Optional indexing must not make the
        # ingest fail or lose usable lexical evidence; Budget remains sticky.
        code = str(error) if isinstance(error, (LLMError, BudgetExceeded)) else "INVALID_EMBEDDING_CACHE"
        logger.warning("BM25 only: %s; source_version=%s", code, sv_id)
        ctx.trace.step("retrieval:index", input_refs=[sv_id], error=code,
                       detail={"mode": "BM25 only", "stop_reason": code, "budget": ctx.budget.usage()})
        return
    ctx.trace.step("retrieval:index", input_refs=[sv_id], detail={"indexed": len(passages), "mode": ctx.mode.upper()})


def _index_passages(passages: list[Passage], ctx: RunContext) -> None:
    for passage in passages:
        ctx.budget.check_active()
        vector = _cached(passage)
        if vector is None:
            vector = embed.embed(passage.content, ctx=ctx, step="embed:ingest").vector
        ctx.budget.check_active()
        with db.transaction() as connection:
            connection.execute(
                "INSERT INTO embeddings(passage_id,source_version_id,model,content_hash,vector_json,created_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(passage_id) DO UPDATE SET model=excluded.model,content_hash=excluded.content_hash,"
                "vector_json=excluded.vector_json,created_at=excluded.created_at",
                (passage.id, passage.sv_id, config.settings.embed_model, embed.cache_identity(passage.content), json.dumps(vector), db.now_iso()))


def _dense(passages: list[Passage], query: str, errors: list[dict[str, JsonValue]]) -> list[tuple[str, float]]:
    ctx = _context.get()
    if ctx is None or ctx.mode == "fallback":
        reason = "FALLBACK" if (ctx.mode if ctx else config.settings.llm_mode) == "fallback" else "RUN_CONTEXT_REQUIRED"
        errors.append({"stage": "dense", "code": reason, "message": "BM25 only"})
        return []
    vectors: dict[str, list[float]] = {}
    for passage in passages:
        try:
            vector = _cached(passage)
        except (ValueError, ValidationError):
            errors.append({"stage": "dense", "code": "INVALID_CACHE", "passage_id": passage.id})
            continue
        if vector is None:
            errors.append({"stage": "dense", "code": "NOT_INDEXED", "passage_id": passage.id})
        else:
            vectors[passage.id] = vector
    if not vectors:
        return []
    query_vector = embed.embed(query, ctx=ctx, step="embed:query").vector
    query_norm = math.hypot(*query_vector)
    scores: list[tuple[str, float]] = []
    for passage_id, vector in vectors.items():
        if len(vector) != len(query_vector):
            errors.append({"stage": "dense", "code": "DIMENSION_MISMATCH", "passage_id": passage_id})
            continue
        norm = math.hypot(*vector)
        scores.append((passage_id, sum((a / norm) * (b / query_norm) for a, b in zip(vector, query_vector))))
    return sorted(scores, key=lambda item: (-item[1], item[0]))


def search(case_id: str, query: str, *, k: int = 8, mode: str = "auto",
           allowed_sv_ids: list[str] | None = None) -> SearchResult:
    if mode not in {"auto", "bm25", "dense", "hybrid"} or not 1 <= k <= 100:
        raise ValueError("INVALID_SEARCH_INPUT")
    # An explicit empty allowlist denies all evidence without touching storage.
    if allowed_sv_ids == []:
        return SearchResult([], {"bm25": []})
    _authorize(case_id)
    passages = _corpus(case_id, allowed_sv_ids)
    lexical = bm25(passages, query)
    errors: list[dict[str, JsonValue]] = []
    dense: list[tuple[str, float]] = []
    if mode != "bm25" and tokens(query):
        try:
            dense = _dense(passages, query, errors)
        except (LLMError, BudgetExceeded) as error:
            errors.append({"stage": "dense", "code": str(error), "message": "BM25 only"})
    fused = rrf(lexical, dense)
    selected = lexical if mode == "bm25" or not dense else dense if mode == "dense" else fused
    by_id = {p.id: p for p in passages}
    hits: list[dict[str, JsonValue]] = []
    for passage_id, score in selected[:k]:
        passage = by_id[passage_id]
        hit = passage.payload()
        hit["score"] = score
        hit["neighbours"] = [p.payload() for p in passages if p.sv_id == passage.sv_id
                              and p.section == passage.section and abs(p.position - passage.position) == 1]
        hits.append(hit)
    effective = "hybrid" if dense and mode in {"auto", "hybrid"} else "dense" if dense and mode == "dense" else "BM25 only"
    stages = {name: [{"passage_id": pid, "score": score} for pid, score in ranked]
              for name, ranked in (("bm25", lexical), ("dense", dense), ("fused", fused))}
    stages["errors"] = errors
    stages["metadata"] = [{"requested_mode": mode, "effective_mode": effective, "rrf_k": 60}]
    ctx = _context.get()
    if ctx is not None:
        ctx.trace.step("retrieval:search", detail={"mode": effective, "errors": errors}, output_refs=[h["passage_id"] for h in hits])
    return SearchResult(hits, stages)
