"""Deterministic OTLP/JSON projection of stored traces; no content or network export."""
from datetime import datetime, timezone
from hashlib import sha256

from pydantic import JsonValue

from app import db
from app.api import read
from app.api.glassbox_contracts import OtelResponse


def _nanos(value: str) -> int:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    delta = stamp - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000


def _attribute(key: str, value: str | int | bool) -> dict[str, JsonValue]:
    kind = "boolValue" if isinstance(value, bool) else "intValue" if isinstance(value, int) else "stringValue"
    return {"key": key, "value": {kind: str(value) if kind == "intValue" else value}}


def export_run(run_id: str) -> OtelResponse:
    run = read.one("SELECT * FROM runs WHERE id=? AND case_id IS NOT NULL", (run_id,))
    steps = read.rows("SELECT * FROM trace_steps WHERE run_id=? ORDER BY seq,id", (run_id,))
    trace_id = sha256(("trace:" + run_id).encode()).hexdigest()[:32]
    root_id = sha256(("root:" + run_id).encode()).hexdigest()[:16]
    start = _nanos(str(run["started_at"] or run["created_at"]))
    end = _nanos(str(run["finished_at"] or run["started_at"] or run["created_at"]))
    spans: list[dict[str, JsonValue]] = []
    for step in steps:
        finish = max(start, _nanos(str(step["created_at"])))
        begin = max(start, finish - int(max(0, float(step["latency_ms"] or 0)) * 1_000_000))
        end = max(end, finish)
        attributes = [_attribute("passport.actor", str(step["actor"])), _attribute("passport.sequence", int(step["seq"]))]
        detail = db.loads(str(step["detail"] or "{}"))
        if step["actor"] == "llm" and isinstance(detail, dict) and isinstance(detail.get("model"), str):
            attributes += [_attribute("gen_ai.request.model", str(detail["model"])),
                           _attribute("gen_ai.usage.input_tokens", int(step["tokens_in"] or 0)),
                           _attribute("gen_ai.usage.output_tokens", int(step["tokens_out"] or 0)),
                           _attribute("passport.replayed", detail.get("replayed") is True)]
        # References, prompts, quotes, raw errors and arbitrary detail are deliberately excluded.
        spans.append({"traceId": trace_id, "spanId": sha256((run_id + ":" + str(step["id"])).encode()).hexdigest()[:16],
                      "parentSpanId": root_id, "name": str(step["step"]), "kind": 1,
                      "startTimeUnixNano": str(begin), "endTimeUnixNano": str(finish),
                      "attributes": attributes, "status": {"code": 2 if step["error"] else 0}})
    root: dict[str, JsonValue] = {"traceId": trace_id, "spanId": root_id, "name": "passport.run", "kind": 1,
        "startTimeUnixNano": str(start), "endTimeUnixNano": str(max(start, end)),
        "attributes": [_attribute("passport.mode", str(run["llm_mode"])), _attribute("passport.status", str(run["status"]))],
        "status": {"code": 2 if run["status"] in {"FAILED", "PARTIAL"} else 0}}
    return OtelResponse(resourceSpans=[{"resource": {"attributes": [_attribute("service.name", "product-truth-passport")]},
        "scopeSpans": [{"scope": {"name": "passport.stored-trace", "version": "1"}, "spans": [root, *spans]}]}])
