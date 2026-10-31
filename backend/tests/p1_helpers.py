"""Synthetic inputs for core tests, independent of demo fixtures and gold."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator
from uuid import uuid4
import pytest
from pydantic import JsonValue
from app import config, db, store
from app.models import EventEnvelope, SourceKind, SourceStatus, ScopeMatch
from app.pipeline.policy import SourceObs


def observation(source: str = "label", field: str = "volume", value: JsonValue = None,
                kind: SourceKind = SourceKind.PACKAGING_IMAGE, **overrides: object) -> SourceObs:
    attributes = dict(source_id=source,source_version_id=source+"-v1",source_version=1,
        source_kind=kind,family=source,status=SourceStatus.ACTIVE,visibility="PUBLIC",scope_match=ScopeMatch.MATCH,
        field_key=field,passage_id=source+"-passage",locator="paragraph:1",quote="Source statement",
        normalized=value if value is not None else {"value":83,"unit":"ml"})
    attributes.update(overrides)
    return SourceObs(**attributes)


@dataclass
class CoreDB:
    product_id: str = "unit-product"
    case_id: str = "unit-case"

    def rows(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, JsonValue]]:
        with closing(db.connect()) as connection:
            return [dict(row) for row in connection.execute(sql,params)]

    def dump(self) -> list[str]:
        with closing(db.connect()) as connection:
            return list(connection.iterdump())

    def source(self, source_id: str = "unit-label", kind: str = "PACKAGING_IMAGE", *,
               text: str = "Volume: 83 ml.", visibility: str = "PUBLIC", version: int = 1) -> SourceObs:
        snapshot = {"source_id":source_id,"product_id":self.product_id,"kind":kind,"version":version,
            "captured_at":"2026-10-31T03:00:00Z","visibility":visibility,"family":source_id,
            "scope":{"product":self.product_id,"variant":"83ml","market":"VN"},
            "passages":[{"locator":"paragraph:1","section":"body","text":text}]}
        with db.transaction() as connection:
            ref = store.ingest(connection,snapshot,case_id=self.case_id,origin="SYNTHETIC")
        passage = store.passages(ref.id)[0]
        return observation(source_id,kind=SourceKind(kind),source_version_id=ref.id,source_version=version,
                           passage_id=passage["id"],quote=text,visibility=visibility)

    def run(self, revision: int = 0) -> dict[str, JsonValue]:
        run_id = "unit-run-" + uuid4().hex
        with db.transaction() as connection:
            connection.execute("INSERT INTO runs(id,case_id,case_revision,status,llm_mode,created_at,started_at) "
                               "VALUES(?,?,?,'RUNNING','fallback',?,?)", (run_id,self.case_id,revision,db.now_iso(),db.now_iso()))
        return {"id":run_id,"case_revision":revision}

    def event(self, event_type: str = "BOOTSTRAP", *, key: str | None = None, resource_kind: str = "CASE",
              resource_id: str | None = None, changed_fields: list[str] | None = None,
              producer: str = "publisher-panel") -> EventEnvelope:
        identity = uuid4().hex
        return EventEnvelope(event_id="unit-event-"+identity,idempotency_key=key or identity,type=event_type,schema_version="1",
            producer=producer,resource={"kind":resource_kind,"id":resource_id or self.case_id,"version":1},
            changed_fields=changed_fields or [],payload={"case_id":self.case_id,"product_id":self.product_id},
            occurred_at="2026-10-31T03:00:00Z",correlation_id=identity)


@pytest.fixture
def core_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[CoreDB]:
    harness = CoreDB()
    try:
        with monkeypatch.context() as env:
            env.setenv("DB_PATH",str(tmp_path/"core.db"))
            env.setenv("LLM_MODE","fallback")
            env.setenv("WORKER_INLINE","1")
            env.setenv("OCR_ENABLED","0")
            env.setenv("DEMO_RUN_DELAY_S","0")
            config.reload_settings()
            db.init_db()
            with db.transaction() as connection:
                connection.execute("INSERT INTO products(id,name,brand,variant,market,dataset_origin,listing_id) "
                                   "VALUES(?,'Test sample','Test lab','83ml','VN','SYNTHETIC','unit-listing')", (harness.product_id,))
                connection.execute("INSERT INTO cases(id,product_id,tenant_id,created_at) VALUES(?,?,'unit-tenant',?)",
                                   (harness.case_id,harness.product_id,db.now_iso()))
            yield harness
    finally:
        config.reload_settings()
