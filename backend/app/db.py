"""SQLite foundation with settings defaults and explicit path overrides."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator, TypeAlias, Union
from . import config

JSON: TypeAlias = Union[None, bool, int, float, str, list["JSON"], dict[str, "JSON"]]
DBPath: TypeAlias = str | Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(value: JSON) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def loads(value: str) -> JSON:
    return json.loads(value)


def connect(path: DBPath | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(config.settings.db_path if path is None else path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


@contextmanager
def transaction(path: DBPath | None = None) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        with connection:
            yield connection
    finally:
        connection.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, name TEXT, brand TEXT, variant TEXT, market TEXT,
 dataset_origin TEXT NOT NULL, version TEXT, listing_id TEXT, web_json TEXT,
 price_vnd REAL, shop_name TEXT, official_store INTEGER, image_path TEXT);
CREATE TABLE IF NOT EXISTS cases (
 id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), tenant_id TEXT,
 revision INTEGER NOT NULL DEFAULT 0, material_revision INTEGER NOT NULL DEFAULT 0,
 status TEXT, dataset_origin TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), product_id TEXT REFERENCES products(id),
 kind TEXT NOT NULL, uri TEXT, owner TEXT, visibility TEXT, family TEXT,
 status TEXT NOT NULL DEFAULT 'ACTIVE', dataset_origin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_versions (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), version INTEGER NOT NULL,
 captured_at TEXT, sha256 TEXT NOT NULL, raw_path TEXT, is_current INTEGER NOT NULL,
 scope_json TEXT, UNIQUE(source_id, sha256), UNIQUE(source_id, version));
CREATE UNIQUE INDEX IF NOT EXISTS one_current_source ON source_versions(source_id) WHERE is_current=1;
CREATE TABLE IF NOT EXISTS passages (
 id TEXT PRIMARY KEY, source_version_id TEXT NOT NULL REFERENCES source_versions(id),
 locator TEXT NOT NULL, section TEXT, text TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(text, passage_id UNINDEXED, source_version_id UNINDEXED);
CREATE TABLE IF NOT EXISTS claims (
 id TEXT PRIMARY KEY, source_version_id TEXT REFERENCES source_versions(id), passage_id TEXT REFERENCES passages(id),
 field_key TEXT, raw_value TEXT, normalized_json TEXT, readability TEXT, extractor TEXT,
 prompt_version TEXT, created_at TEXT, quote TEXT);
CREATE TABLE IF NOT EXISTS field_results (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), field_key TEXT, result_version INTEGER,
 case_revision INTEGER, verdict TEXT, conflict_locus TEXT, scope_match TEXT, freshness TEXT,
 review_state TEXT, evidence_level TEXT, seller_attributable INTEGER, citations_json TEXT,
 depends_on_json TEXT, public_text TEXT, policy_version TEXT, run_id TEXT, created_at TEXT,
 superseded_by TEXT, notes_json TEXT, explain_json TEXT, stale_reason TEXT, stale_at TEXT,
 confirmed_run_id TEXT, confirmed_at TEXT, reviewed_by TEXT, prev_hash TEXT, chain_hash TEXT, chain_seq INTEGER);
CREATE TABLE IF NOT EXISTS gaps (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), field_key TEXT, missing_kind TEXT,
 needed_doc TEXT, known_ids_json TEXT, tried_json TEXT, status TEXT, run_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS evidence_requests (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), field_key TEXT, gap_id TEXT REFERENCES gaps(id),
 reason TEXT, requested_from TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS review_tasks (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), field_key TEXT,
 result_id TEXT REFERENCES field_results(id), reason_code TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS reviews (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), result_id TEXT REFERENCES field_results(id),
 case_revision INTEGER, reviewer_id TEXT, decision TEXT, reason TEXT, override_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, type TEXT, producer TEXT, resource_id TEXT,
 resource_version TEXT, payload_json TEXT, received_at TEXT, outcome TEXT, reason TEXT, event_id TEXT, run_id TEXT);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), case_revision INTEGER,
 trigger_event_id TEXT REFERENCES events(id), status TEXT, stop_reason TEXT, model TEXT,
 prompt_version TEXT, policy_version TEXT, llm_mode TEXT, budget_json TEXT, usage_json TEXT,
 started_at TEXT, finished_at TEXT, error TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), target_revision INTEGER NOT NULL,
 trigger_event_id TEXT REFERENCES events(id), status TEXT NOT NULL, run_id TEXT REFERENCES runs(id),
 created_at TEXT NOT NULL, finished_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_queued_job ON jobs(case_id) WHERE status='QUEUED';
CREATE TABLE IF NOT EXISTS trace_steps (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), seq INTEGER NOT NULL,
 step TEXT, actor TEXT, input_refs TEXT, output_refs TEXT, latency_ms REAL,
 tokens_in INTEGER, tokens_out INTEGER, error TEXT, detail TEXT, created_at TEXT,
 t_ms REAL, UNIQUE(run_id, seq));
CREATE TABLE IF NOT EXISTS passage_scopes (
 source_version_id TEXT REFERENCES source_versions(id), passage_id TEXT REFERENCES passages(id),
 scope_match TEXT, reason TEXT, decided_by TEXT, run_id TEXT, created_at TEXT,
 PRIMARY KEY(source_version_id, passage_id));
CREATE TABLE IF NOT EXISTS extraction_cache (
 source_version_id TEXT REFERENCES source_versions(id), prompt_version TEXT, extractor TEXT,
 extraction_json TEXT, ignored_instructions INTEGER, created_at TEXT,
 PRIMARY KEY(source_version_id, prompt_version, extractor));
CREATE TABLE IF NOT EXISTS vocab (
 field TEXT, surface TEXT, value_json TEXT, "by" TEXT, model TEXT, created_at TEXT, PRIMARY KEY(field, surface));
CREATE TABLE IF NOT EXISTS ocr_lines (
 source_version_id TEXT REFERENCES source_versions(id), idx INTEGER, text TEXT,
 x0 REAL, y0 REAL, x1 REAL, y1 REAL, conf REAL, w INTEGER, h INTEGER, PRIMARY KEY(source_version_id, idx));
CREATE TABLE IF NOT EXISTS marketplace_findings (
 product_id TEXT REFERENCES products(id), scan_id TEXT, seller_source_id TEXT REFERENCES sources(id),
 shop TEXT, field_key TEXT, value_json TEXT, display TEXT, cluster TEXT, outlier INTEGER, citation_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, product_id TEXT REFERENCES products(id), case_id TEXT REFERENCES cases(id),
 buyer_id TEXT, placed_at TEXT, case_revision INTEGER, snapshot_json TEXT, snapshot_hash TEXT, chain_head TEXT);
CREATE TABLE IF NOT EXISTS web_searches (
 id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), run_id TEXT REFERENCES runs(id), query TEXT,
 provider TEXT, mode TEXT, results_json TEXT, credits REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS embeddings (
 passage_id TEXT PRIMARY KEY REFERENCES passages(id), source_version_id TEXT REFERENCES source_versions(id),
 model TEXT, content_hash TEXT, vector_json TEXT, created_at TEXT);
"""


def init_db(path: DBPath | None = None) -> None:
    connection = connect(path)
    try:
        connection.executescript("BEGIN IMMEDIATE;" + SCHEMA + "COMMIT;")
    finally:
        connection.close()
