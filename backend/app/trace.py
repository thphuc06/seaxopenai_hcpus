"""Persistent, serialized run sequence and run-relative timestamps."""
from contextlib import contextmanager
from datetime import datetime
from time import perf_counter
import sys
from typing import Iterator
from uuid import uuid4
from threading import Lock
from . import config, db

_counter_lock = Lock()
_duplicates: dict[str, int] = {}


def duplicate_events(*, increment: bool = False, reset: bool = False, db_path: db.DBPath | None = None) -> int:
    """Process-local metric; duplicate admission never adds durable rows."""
    key = str(db_path or config.settings.db_path)
    with _counter_lock:
        if reset:
            _duplicates[key] = 0
        if increment:
            _duplicates[key] = _duplicates.get(key, 0) + 1
        return _duplicates.get(key, 0)


class TraceWriter:
    def __init__(self, run_id: str, *, db_path: db.DBPath | None = None) -> None:
        self.run_id = run_id
        self.db_path = db_path

    def step(self, step: str, actor: str = "code", input_refs: db.JSON = None,
             output_refs: db.JSON = None, detail: db.JSON = None, latency_ms: float = 0,
             tokens_in: int = 0, tokens_out: int = 0, error: str | None = None) -> None:
        with db.transaction(self.db_path) as connection:
            run = connection.execute("SELECT started_at,created_at FROM runs WHERE id=?", (self.run_id,)).fetchone()
            if not run or not (run["started_at"] or run["created_at"]):
                raise ValueError("Trace requires a stored run start timestamp")
            now = db.now_iso()
            elapsed = (datetime.fromisoformat(now) - datetime.fromisoformat(run["started_at"] or run["created_at"])).total_seconds() * 1000
            previous = connection.execute("SELECT COALESCE(MAX(seq),0),COALESCE(MAX(t_ms),0) FROM trace_steps WHERE run_id=?", (self.run_id,)).fetchone()
            connection.execute("INSERT INTO trace_steps VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               ("trace_" + uuid4().hex, self.run_id, previous[0] + 1, step, actor,
                                db.dumps(input_refs), db.dumps(output_refs), latency_ms, tokens_in, tokens_out,
                                error, db.dumps(detail or {}), now, max(previous[1], elapsed, 0)))

    @contextmanager
    def timed(self, step: str, actor: str = "code") -> Iterator[None]:
        start = perf_counter()
        completed = False
        try:
            yield
            completed = True
        finally:
            failure = None if completed else sys.exc_info()[0]
            self.step(step, actor, latency_ms=(perf_counter() - start) * 1000,
                      error=failure.__name__ if failure else None)
