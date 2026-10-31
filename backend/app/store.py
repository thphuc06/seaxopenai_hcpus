"""Versioned source ingestion, independent of extraction."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import importlib
import logging
from pathlib import Path
import sqlite3
from uuid import uuid4
from . import db

logger = logging.getLogger(__name__)


def index_source(ref: SourceVersionRef) -> None:
    """Optional indexing is diagnostic only; persisted evidence remains usable."""
    for module_name, function in (("app.retrieval.search", "index_source_version"), ("app.pipeline.ocr", "index_image")):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name and (module_name == error.name or module_name.startswith(error.name + ".")):
                logger.warning("Index hook unavailable: %s; source_version=%s", module_name, ref.id)
                continue
            raise
        try:
            getattr(module, function)(ref.id)
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            logger.error("Index hook failed: %s; source_version=%s", module_name, ref.id)


@dataclass(frozen=True)
class SourceVersionRef:
    id: str
    source_id: str
    version: int


def ingest(connection: sqlite3.Connection, snapshot: dict[str, db.JSON], *, case_id: str | None,
           origin: str, raw_path: str | None = None) -> SourceVersionRef:
    source_id = str(snapshot["source_id"])
    # Canonical JSON envelope binds metadata and image content without ambiguous concatenation.
    content: db.JSON = snapshot
    if raw_path:
        content = {"snapshot": snapshot, "image_sha256": hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()}
    sha = hashlib.sha256(db.dumps(content).encode("utf-8")).hexdigest()
    owner = connection.execute("SELECT case_id, product_id FROM sources WHERE id=?", (source_id,)).fetchone()
    if owner and (owner["case_id"] != case_id or owner["product_id"] != snapshot["product_id"]):
        raise ValueError("Source belongs to another case or product")
    existing = connection.execute("SELECT id, version FROM source_versions WHERE source_id=? AND sha256=?", (source_id, sha)).fetchone()
    if existing:
        return SourceVersionRef(existing["id"], source_id, existing["version"])
    version = int(str(snapshot["version"]))
    latest = connection.execute("SELECT MAX(version) FROM source_versions WHERE source_id=?", (source_id,)).fetchone()[0]
    if latest is not None and version <= latest:
        raise ValueError("New content must have a newer source version")
    visibility = snapshot.get("visibility", "PRIVATE")
    if visibility not in ("PUBLIC", "PRIVATE"):
        raise ValueError("Invalid source visibility")
    connection.execute("INSERT INTO sources(id,case_id,product_id,kind,uri,owner,visibility,family,status,dataset_origin) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,uri=excluded.uri,owner=excluded.owner,visibility=excluded.visibility,family=excluded.family",
                       (source_id, case_id, snapshot["product_id"], snapshot["kind"], snapshot.get("uri"), snapshot.get("owner"), visibility, snapshot.get("family"), "ACTIVE", origin))
    connection.execute("UPDATE source_versions SET is_current=0 WHERE source_id=?", (source_id,))
    sv_id = "sv_" + uuid4().hex
    connection.execute("INSERT INTO source_versions VALUES(?,?,?,?,?,?,?,?)", (sv_id, source_id, version, snapshot.get("captured_at"), sha, raw_path, 1, db.dumps(snapshot.get("scope") or {})))
    passages = snapshot.get("passages", [])
    if not isinstance(passages, list) or not passages:
        raise ValueError("passages must be a nonempty list")
    for passage in passages:
        if not isinstance(passage, dict):
            raise ValueError("passage must be an object")
        text = passage.get("text")
        if not isinstance(text, str):
            raise ValueError("Passage text must be a string")
        if not text.strip() and not (snapshot["kind"] == "PACKAGING_IMAGE" and raw_path and snapshot.get("note")):
            raise ValueError("Blank text requires a documented unreadable image")
        passage_id = "psg_" + uuid4().hex
        connection.execute("INSERT INTO passages VALUES(?,?,?,?,?)", (passage_id, sv_id, passage["locator"], passage.get("section"), passage["text"]))
        connection.execute("INSERT INTO passages_fts VALUES(?,?,?)", (passage["text"], passage_id, sv_id))
    return SourceVersionRef(sv_id, source_id, version)


def add_source_version(snapshot: dict[str, db.JSON], *, case_id: str | None, origin: str,
                       raw_path: str | None = None, db_path: db.DBPath | None = None) -> SourceVersionRef:
    with db.transaction(db_path) as connection:
        previous = {row[0] for row in connection.execute("SELECT id FROM source_versions WHERE source_id=?", (snapshot["source_id"],))}
        ref = ingest(connection, snapshot, case_id=case_id, origin=origin, raw_path=raw_path)
    if ref.id not in previous:
        index_source(ref)
    return ref


def passages(sv_id: str, *, db_path: db.DBPath | None = None) -> list[dict[str, db.JSON]]:
    with db.transaction(db_path) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM passages WHERE source_version_id=? ORDER BY rowid", (sv_id,))]


def current_sources(case_id: str, *, db_path: db.DBPath | None = None) -> list[dict[str, db.JSON]]:
    with db.transaction(db_path) as connection:
        return [dict(row) for row in connection.execute("SELECT s.*,v.id AS source_version_id,v.version,v.scope_json FROM sources s JOIN source_versions v ON v.source_id=s.id WHERE s.case_id=? AND v.is_current=1", (case_id,))]
