"""Load version-one product folders without product-specific knowledge."""
import logging
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from . import config, db, store

logger = logging.getLogger(__name__)


def read_object(path: Path) -> dict[str, db.JSON]:
    value = db.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _load_product_dir(path: str | Path, connection: sqlite3.Connection,
                      added: list[store.SourceVersionRef], *, case_id_override: str | None = None) -> str:
    folder = Path(path)
    if any("TODO" in item.read_text(encoding="utf-8") for item in folder.glob("*.json")):
        logger.warning("Skipping unfinished product folder: %s", folder)
        return ""
    product = read_object(folder / "product.json")
    product_id = str(product["product_id"])
    case_id = case_id_override or str(product["case_id"])
    snapshots = [(item, read_object(item)) for item in sorted(folder.glob("*.v1.json"))]
    with nullcontext(connection) as connection:
        previous = {row[0] for row in connection.execute("SELECT id FROM source_versions")}
        connection.execute("INSERT INTO products(id,name,brand,variant,market,dataset_origin,listing_id,web_json) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                           (product_id, product.get("name"), product.get("brand"), product.get("variant"), product.get("market"), product["dataset_origin"], product.get("listing_id"), db.dumps(product.get("web") or {})))
        connection.execute("INSERT INTO cases(id,product_id,tenant_id,revision,material_revision,status,dataset_origin,created_at) VALUES(?,?,?,0,0,'ACTIVE',?,?) ON CONFLICT(id) DO NOTHING",
                           (case_id, product_id, product.get("tenant_id"), product["dataset_origin"], db.now_iso()))
        bound = connection.execute("SELECT product_id FROM cases WHERE id=?", (case_id,)).fetchone()
        if bound[0] != product_id:
            raise ValueError("Case belongs to another product")
        for item, snapshot in snapshots:
            if snapshot["product_id"] != product_id or snapshot["version"] != 1:
                raise ValueError("Snapshot product/version does not match its seed folder")
            image = None
            if snapshot["kind"] == "PACKAGING_IMAGE":
                image = next((item.with_suffix(ext) for ext in (".png", ".jpg") if item.with_suffix(ext).exists()), None)
            ref = store.ingest(connection, snapshot, case_id=case_id, origin=str(snapshot["dataset_origin"]), raw_path=str(image) if image else None)
            if ref.id not in previous:
                added.append(ref)
            if snapshot["kind"] == "LISTING" and ref.id not in previous:
                connection.execute("UPDATE products SET price_vnd=?,shop_name=?,official_store=?,image_path=? WHERE id=?",
                                   (snapshot.get("price_vnd"), snapshot.get("shop_name"), snapshot.get("official_store"), snapshot.get("image_path"), product_id))
    return product_id


def load_product_dir(path: str | Path, *, case_id_override: str | None = None,
                     db_path: db.DBPath | None = None) -> str:
    added: list[store.SourceVersionRef] = []
    with db.transaction(db_path) as connection:
        product_id = _load_product_dir(path, connection, added, case_id_override=case_id_override)
    for ref in added:
        store.index_source(ref)
    return product_id


def reset(*, db_path: db.DBPath | None = None, fixtures_dir: str | Path | None = None) -> None:
    """Explicit demo reset, preserving the database file and its WAL ownership."""
    db.init_db(db_path)
    fixtures_dir = config.settings.fixtures_dir if fixtures_dir is None else fixtures_dir
    added: list[store.SourceVersionRef] = []
    with db.transaction(db_path) as connection:
        for table in ("embeddings", "web_searches", "orders", "marketplace_findings", "ocr_lines", "vocab", "extraction_cache", "passage_scopes", "reviews", "review_tasks", "evidence_requests", "gaps", "field_results", "claims", "jobs", "trace_steps", "runs", "events", "passages_fts", "passages", "source_versions", "sources", "cases", "products"):
            connection.execute(f'DELETE FROM "{table}"')
        for group in ("synthetic", "real"):
            for product in sorted((Path(fixtures_dir) / group).rglob("product.json")):
                _load_product_dir(product.parent, connection, added)
    for ref in added:
        store.index_source(ref)


def seed_if_empty(*, db_path: db.DBPath | None = None, fixtures_dir: str | Path | None = None) -> bool:
    db.init_db(db_path)
    with db.transaction(db_path) as connection:
        populated = connection.execute("SELECT 1 FROM products LIMIT 1").fetchone()
    if populated:
        return False
    reset(db_path=db_path, fixtures_dir=fixtures_dir)
    return True
