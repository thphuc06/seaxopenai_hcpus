import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import os
from unittest.mock import patch
from app import db, seed, store
from app.trace import TraceWriter


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "test.sqlite"
        db.init_db(self.path)

    def fixture(self, name="alpha", group="synthetic", marker="image_todo"):
        folder = self.root / group / name
        folder.mkdir(parents=True)
        product = {"product_id": name, "case_id": "case-" + name, "dataset_origin": "SYNTHETIC", "name": "Tên thử", "note": marker}
        snapshot = {"source_id": "src-" + name, "product_id": name, "kind": "LISTING", "version": 1, "dataset_origin": "SYNTHETIC", "price_vnd": 12345, "passages": [{"id": "local", "locator": "title", "text": "Nội dung"}]}
        (folder / "product.json").write_text(db.dumps(product), encoding="utf-8")
        (folder / "listing.v1.json").write_text(db.dumps(snapshot), encoding="utf-8")
        (folder / "listing.v2.json").write_text(db.dumps({**snapshot, "version": 2}), encoding="utf-8")
        return folder, snapshot

    def test_seed_groups_revision_idempotency_and_variants(self):
        self.fixture()
        self.fixture("beta", "real")
        self.fixture("hidden", "blind")
        self.assertTrue(seed.seed_if_empty(db_path=self.path, fixtures_dir=self.root))
        self.assertFalse(seed.seed_if_empty(db_path=self.path, fixtures_dir=self.root))
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 2)
            self.assertEqual([r[0] for r in con.execute("SELECT revision FROM cases")], [0, 0])
            self.assertEqual([r[0] for r in con.execute("SELECT version FROM source_versions")], [1, 1])
            self.assertEqual(con.execute("SELECT price_vnd FROM products LIMIT 1").fetchone()[0], 12345)

    def test_todo_case_sensitive(self):
        folder, _ = self.fixture(marker="TODO unfinished")
        with self.assertLogs("app.seed", level="WARNING"):
            self.assertEqual(seed.load_product_dir(folder, db_path=self.path), "")
        folder, _ = self.fixture("ready")
        self.assertEqual(seed.load_product_dir(folder, db_path=self.path), "ready")

    def test_versions_and_fts(self):
        folder, snapshot = self.fixture()
        seed.load_product_dir(folder, db_path=self.path)
        first = store.add_source_version(snapshot, case_id="case-alpha", origin="SYNTHETIC", db_path=self.path)
        again = store.add_source_version(dict(reversed(list(snapshot.items()))), case_id="case-alpha", origin="SYNTHETIC", db_path=self.path)
        self.assertEqual(first, again)
        updated = {**snapshot, "version": 2, "passages": [{"locator": "body", "text": "Khác"}]}
        second = store.add_source_version(updated, case_id="case-alpha", origin="SYNTHETIC", db_path=self.path)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(store.passages(first.id, db_path=self.path)), 1)
        self.assertEqual(store.current_sources("case-alpha", db_path=self.path)[0]["version"], 2)
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM passages_fts").fetchone()[0], 2)

    def test_rollback_foreign_keys_and_schema_repeat(self):
        db.init_db(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaction(self.path) as con:
                con.execute("INSERT INTO cases(id,product_id) VALUES('orphan','missing')")
        with self.assertRaises(RuntimeError):
            with db.transaction(self.path) as con:
                con.execute("INSERT INTO products(id,dataset_origin) VALUES('rollback','SYNTHETIC')")
                raise RuntimeError("abort")
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 0)

    def test_duplicate_cannot_cross_case_and_old_version_cannot_replace(self):
        folder, snapshot = self.fixture()
        seed.load_product_dir(folder, db_path=self.path)
        with self.assertRaises(ValueError):
            store.add_source_version(snapshot, case_id="other", origin="SYNTHETIC", db_path=self.path)
        with self.assertRaises(ValueError):
            store.add_source_version({**snapshot, "uri": "changed"}, case_id="case-alpha", origin="SYNTHETIC", db_path=self.path)
        self.assertEqual(len(store.current_sources("case-alpha", db_path=self.path)), 1)

    def test_schema_extended_tables_and_columns(self):
        with db.transaction(self.path) as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"embeddings", "passage_scopes", "extraction_cache", "vocab", "ocr_lines", "marketplace_findings", "orders", "web_searches", "passages_fts"} <= tables)
            columns = {row[1] for row in con.execute("PRAGMA table_info(field_results)")}
            self.assertTrue({"notes_json", "explain_json", "confirmed_run_id", "confirmed_at", "stale_reason", "stale_at", "prev_hash", "chain_hash", "chain_seq", "reviewed_by"} <= columns)

    def test_trace_reinstantiation_and_offset(self):
        with db.transaction(self.path) as con:
            con.execute("INSERT INTO runs(id,started_at) VALUES(?,?)", ("r", "2026-01-01T00:00:00+00:00"))
        TraceWriter("r", db_path=self.path).step("pin_revision")
        with TraceWriter("r", db_path=self.path).timed("scope_check", "code"):
            pass
        with db.transaction(self.path) as con:
            rows = con.execute("SELECT seq,t_ms FROM trace_steps ORDER BY seq").fetchall()
            self.assertEqual([r[0] for r in rows], [1, 2])
            self.assertGreater(rows[0][1], 1000)
            self.assertGreaterEqual(rows[1][1], rows[0][1])

    def test_reset_reloads_and_failed_product_rolls_back(self):
        folder, snapshot = self.fixture()
        seed.reset(db_path=self.path, fixtures_dir=self.root)
        seed.reset(db_path=self.path, fixtures_dir=self.root)
        bad, _ = self.fixture("bad")
        (bad / "listing.v1.json").write_text(db.dumps(snapshot), encoding="utf-8")
        with self.assertRaises(ValueError):
            seed.load_product_dir(bad, db_path=self.path)
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)

    def test_settings_defaults_startup_and_reload(self):
        from app import config
        from app.main import create_app
        from fastapi.testclient import TestClient

        folder, snapshot = self.fixture("settings-product")
        try:
            for name in ("first.sqlite", "second.sqlite"):
                configured_path = self.root / name
                with patch.dict(os.environ, {"DB_PATH": str(configured_path), "FIXTURES_DIR": str(self.root), "LLM_MODE": "fallback", "OCR_ENABLED": "0"}):
                    config.reload_settings()
                    with TestClient(create_app()) as client:
                        self.assertEqual(client.get("/api/health").status_code, 200)
                        self.assertTrue(configured_path.exists())
                        self.assertFalse(seed.seed_if_empty())
                        self.assertEqual(seed.load_product_dir(folder), "settings-product")
                        ref = store.add_source_version(snapshot, case_id="case-settings-product", origin="SYNTHETIC")
                        self.assertEqual(len(store.passages(ref.id)), 1)
                        self.assertEqual(len(store.current_sources("case-settings-product")), 1)
                        with db.transaction() as con:
                            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)
                            con.execute("INSERT INTO runs(id,started_at) VALUES(?,?)", ("configured-run", db.now_iso()))
                        TraceWriter("configured-run").step("pin_revision")
                        with db.transaction() as con:
                            self.assertEqual(con.execute("SELECT COUNT(*) FROM trace_steps").fetchone()[0], 1)
                        seed.reset()
                        with db.transaction() as con:
                            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)
                            self.assertEqual(con.execute("SELECT COUNT(*) FROM trace_steps").fetchone()[0], 0)
                        # Explicit overrides still select a separate database.
                        with db.transaction(self.path) as con:
                            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 0)
        finally:
            config.reload_settings()

    def test_reset_failure_preserves_previous_dataset(self):
        folder, _ = self.fixture("original")
        seed.load_product_dir(folder, db_path=self.path)
        with db.transaction(self.path) as con:
            con.execute("UPDATE cases SET revision=7")
        bad, _ = self.fixture("zbroken")
        (bad / "listing.v1.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            seed.reset(db_path=self.path, fixtures_dir=self.root)
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT revision FROM cases").fetchone()[0], 7)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)

    def test_new_version_privacy_and_reseed_commerce(self):
        folder, snapshot = self.fixture()
        snapshot["visibility"] = "PUBLIC"
        (folder / "listing.v1.json").write_text(db.dumps(snapshot), encoding="utf-8")
        seed.load_product_dir(folder, db_path=self.path)
        store.add_source_version({**snapshot, "version": 2, "visibility": "PRIVATE"}, case_id="case-alpha", origin="SYNTHETIC", db_path=self.path)
        with db.transaction(self.path) as con:
            con.execute("UPDATE products SET price_vnd=99999")
        seed.load_product_dir(folder, db_path=self.path)
        self.assertEqual(store.current_sources("case-alpha", db_path=self.path)[0]["visibility"], "PRIVATE")
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT price_vnd FROM products").fetchone()[0], 99999)

    def test_timed_error_is_sanitized_and_propagated(self):
        with db.transaction(self.path) as con:
            con.execute("INSERT INTO runs(id,started_at) VALUES(?,?)", ("failed", db.now_iso()))
        with self.assertRaisesRegex(ValueError, "private detail"):
            with TraceWriter("failed", db_path=self.path).timed("extract", "code"):
                raise ValueError("private detail")
        with db.transaction(self.path) as con:
            self.assertEqual(con.execute("SELECT error FROM trace_steps").fetchone()[0], "ValueError")

    def test_timed_success_inside_recovery_is_not_marked_failed(self):
        with db.transaction(self.path) as con:
            con.execute("INSERT INTO runs(id,started_at) VALUES(?,?)", ("recovery", db.now_iso()))
        try:
            raise ValueError("already handled")
        except ValueError:
            with TraceWriter("recovery", db_path=self.path).timed("scope_check"):
                pass
        with db.transaction(self.path) as con:
            self.assertIsNone(con.execute("SELECT error FROM trace_steps").fetchone()[0])

    def test_blank_evidence_validation_and_image_variants(self):
        folder, snapshot = self.fixture()
        seed.load_product_dir(folder, db_path=self.path)
        for kind in ("LISTING", "PACKAGING_IMAGE"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                store.add_source_version({**snapshot, "version": 2, "kind": kind, "passages": [{"locator": "image:full", "text": ""}]}, case_id="case-alpha", origin="SYNTHETIC", db_path=self.path)
        for suffix in (".png", ".jpg"):
            name = "image" + suffix[1:]
            image_folder, image_snapshot = self.fixture(name)
            image_snapshot.update(kind="PACKAGING_IMAGE", note="Intentionally unreadable", passages=[{"locator": "image:full", "text": ""}])
            (image_folder / "listing.v1.json").write_text(db.dumps(image_snapshot), encoding="utf-8")
            image_path = image_folder / ("listing.v1" + suffix)
            image_path.write_bytes(b"binary-image-input")
            seed.load_product_dir(image_folder, db_path=self.path)
            with db.transaction(self.path) as con:
                row = con.execute("SELECT raw_path,sha256 FROM source_versions WHERE source_id=?", ("src-" + name,)).fetchone()
                self.assertEqual(row["raw_path"], str(image_path))
            image_path.write_bytes(b"changed-image-input")
            with self.assertRaises(ValueError):
                store.add_source_version(image_snapshot, case_id="case-" + name, origin="SYNTHETIC", raw_path=str(image_path), db_path=self.path)
