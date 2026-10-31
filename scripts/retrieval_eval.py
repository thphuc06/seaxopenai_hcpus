"""Freeze bilingual retrieval expectations before an offline ranking evaluation.

Outputs Markdown to stdout for P4; never writes docs or calls a paid provider.
The manifest is independent of candidate rankings and includes resolved stored IDs.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import BaseModel, ConfigDict

from app import config, db, seed
from app.budget import Budget, BudgetExceeded
from app.context import RunContext
from app.llm.client import LLMError, network_guard
from app.retrieval.search import index_source_version, run_context, search
from app.trace import TraceWriter


@dataclass(frozen=True)
class Question:
    language: str
    query: str
    source_id: str
    locator: str
    rationale: str


# Written from stored source passages before the first candidate search.
# These are evaluation inputs, not application vocabulary or expected verdicts.
QUESTIONS = (
    Question("VI", "Số tiếp nhận công bố trong hồ sơ là gì?", "DEMO-SRC-S1-NOTIFICATION", "page1#number", "The record passage states the notification identifier."),
    Question("VI", "To chuc nao chiu trach nhiem?", "DEMO-SRC-S1-NOTIFICATION", "page1#company", "The record identifies the responsible organization."),
    Question("VI", "Bài giới thiệu nêu thành phần nổi bật nào?", "DEMO-SRC-S2-BRAND", "highlights#ingredients", "The highlighted ingredient is stated in this passage."),
    Question("VI", "Nguồn mô tả kết cấu tạo bọt cho loại da nào?", "DEMO-SRC-S2-BRAND", "description#p1", "The description contains the foaming texture and skin statement."),
    Question("VI", "Serum có nói không chứa cồn và hương liệu không?", "DEMO-SRC-S4-LISTING", "highlights#free-from", "This is the seller's quoted absence claim, not a policy result."),
    Question("EN", "Which ingredients include Cocamidopropyl Betaine?", "DEMO-SRC-S2-BRAND", "ingredients", "The brand INCI list contains this ingredient."),
    Question("EN", "What Niacinamide percentage is advertised?", "DEMO-SRC-S4-LISTING", "highlights#concentration", "This seller passage states the percentage."),
    Question("EN", "Who is the responsible organization?", "DEMO-SRC-S1-NOTIFICATION", "page1#company", "English paraphrase of the Vietnamese organization passage."),
    Question("EN", "Does the seller claim alcohol and fragrance absence?", "DEMO-SRC-S4-LISTING", "highlights#free-from", "English paraphrase of the Vietnamese absence claim."),
    Question("EN", "What is the notification reference number?", "DEMO-SRC-S1-NOTIFICATION", "page1#number", "English paraphrase of the Vietnamese notification passage."),
)


class ExpectedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    language: str
    query: str
    case_id: str
    expected_passage_ids: list[str]
    rationale: str


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: str
    corpus_sha256: str
    status: str
    questions: list[ExpectedQuery]


@contextmanager
def corpus() -> Iterator[None]:
    keys = {key: os.environ.get(key) for key in ("DB_PATH", "LLM_MODE", "OCR_ENABLED")}
    with tempfile.TemporaryDirectory(prefix="retrieval-eval-") as folder:
        try:
            os.environ.update(DB_PATH=str(Path(folder) / "corpus.db"), LLM_MODE="fallback", OCR_ENABLED="0")
            config.reload_settings()
            db.init_db()
            for product in sorted((ROOT / "fixtures/synthetic").glob("*/product.json")):
                seed.load_product_dir(product.parent)
            yield
        finally:
            for key, value in keys.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            config.reload_settings()


def prepare() -> Manifest:
    questions: list[ExpectedQuery] = []
    with closing(db.connect()) as connection:
        rows = [tuple(row) for row in connection.execute("SELECT id,source_version_id,locator,section,text FROM passages ORDER BY id")]
        fingerprint = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()
        for item in QUESTIONS:
            row = connection.execute(
                "SELECT p.id,s.case_id FROM passages p JOIN source_versions v ON v.id=p.source_version_id "
                "JOIN sources s ON s.id=v.source_id WHERE s.id=? AND p.locator=? AND v.version=1",
                (item.source_id, item.locator)).fetchall()
            if len(row) != 1:
                raise ValueError("Expectation must resolve to exactly one stored passage")
            questions.append(ExpectedQuery(language=item.language, query=item.query, case_id=row[0]["case_id"],
                                           expected_passage_ids=[row[0]["id"]], rationale=item.rationale))
    return Manifest(version="retrieval-eval-v1", corpus_sha256=fingerprint, status="DRAFT", questions=questions)


def metrics(expected: list[list[str]], ranked: list[list[str]]) -> tuple[float, float]:
    if not expected or len(expected) != len(ranked) or any(not ids for ids in expected):
        raise ValueError("Nonempty aligned expectations required")
    recall = sum(len(set(want) & set(found[:3])) / len(set(want)) for want, found in zip(expected, ranked)) / len(expected)
    mrr = sum(next((1 / rank for rank, pid in enumerate(found, 1) if pid in want), 0.0)
              for want, found in zip(expected, ranked)) / len(expected)
    return recall, mrr


def evaluate(manifest: Manifest, mode: str) -> str:
    if manifest != prepare():
        raise ValueError("Manifest differs from the frozen source-based expectations or corpus")
    ranked: list[list[str]] = [[] for _ in manifest.questions]
    for case_id in sorted({item.case_id for item in manifest.questions}):
        ctx: RunContext | None = None
        if mode != "bm25":
            with db.transaction() as connection:
                case = connection.execute("SELECT tenant_id FROM cases WHERE id=?", (case_id,)).fetchone()
                run_id = "retrieval-eval-" + case_id
                connection.execute("INSERT INTO runs(id,case_id,started_at) VALUES(?,?,?)", (run_id, case_id, db.now_iso()))
                versions = [row[0] for row in connection.execute(
                    "SELECT v.id FROM source_versions v JOIN sources s ON s.id=v.source_id WHERE s.case_id=? AND v.is_current=1 ORDER BY v.id", (case_id,))]
            ctx = RunContext(run_id, case_id, case[0], 0, {}, "replay", Budget.from_settings(), TraceWriter(run_id))
            try:
                with run_context(ctx):
                    for version in versions:
                        index_source_version(version)
            except (LLMError, BudgetExceeded) as error:
                return f"{mode}: NOT VERIFIED — replay ingest unavailable ({error}). No dense/hybrid metric."
        # Finish each case's queries before creating another case's Budget.
        for index, question in enumerate(manifest.questions):
            if question.case_id != case_id:
                continue
            if ctx is None:
                result = search(question.case_id, question.query, k=100, mode="bm25")
            else:
                try:
                    with run_context(ctx):
                        result = search(question.case_id, question.query, k=100, mode=mode)
                except BudgetExceeded as error:
                    return f"{mode}: NOT VERIFIED — {error}. No dense/hybrid metric."
                if result.stages["errors"] or result.stages["metadata"][0]["effective_mode"] != mode:
                    return f"{mode}: NOT VERIFIED — {json.dumps(result.stages['errors'])}. No dense/hybrid metric."
            ranked[index] = [str(hit["passage_id"]) for hit in result.hits]
    lines = ["# Retrieval evaluation", "", "DRAFT expectations frozen before ranking; synthetic v1 corpus only.",
             "BM25 only; no dense/hybrid quality claim." if mode == "bm25" else f"Mode: {mode}, replay only.",
             "", "| Language | Queries | Recall@3 | MRR |", "|---|---:|---:|---:|"]
    for language in ("VI", "EN", "ALL"):
        selected = [i for i, item in enumerate(manifest.questions) if language == "ALL" or item.language == language]
        recall, mrr = metrics([manifest.questions[i].expected_passage_ids for i in selected], [ranked[i] for i in selected])
        lines.append(f"| {language} | {len(selected)} | {recall:.4f} | {mrr:.4f} |")
    lines.extend(["", "Per-query results (expected IDs remain in the immutable manifest):"])
    for question, found in zip(manifest.questions, ranked):
        lines.append(json.dumps({"query": question.query, "expected": question.expected_passage_ids, "ranked": found}, ensure_ascii=False))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    paths = parser.add_mutually_exclusive_group(required=True)
    paths.add_argument("--prepare", type=Path, help="Create immutable expectations; does not run search")
    paths.add_argument("--manifest", type=Path, help="Previously prepared expectations")
    parser.add_argument("--mode", choices=("bm25", "dense", "hybrid"), default="bm25")
    args = parser.parse_args()
    def reject_network(request: object) -> None:
        raise RuntimeError("Evaluation forbids provider network calls")
    with network_guard(reject_network), corpus():
        if args.prepare:
            with args.prepare.open("x", encoding="utf-8") as output:
                output.write(prepare().model_dump_json(indent=2) + "\n")
            print("Prepared DRAFT expected passage IDs; zero searches executed.")
        else:
            manifest = Manifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
            report = evaluate(manifest, args.mode)
            print(report)
            if "NOT VERIFIED" in report:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
