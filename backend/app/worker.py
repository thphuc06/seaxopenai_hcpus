"""Persisted queue drained inline or by the request background task."""
from threading import Lock
from time import sleep
from app import config, db
from app.pipeline.run import Extractor, Job, run

_lock = Lock()
_case_locks: dict[tuple[str, str], Lock] = {}


def execute_job(job_id: str, *, extractor: Extractor | None = None) -> None:
    with db.transaction() as connection:
        row = connection.execute("SELECT case_id FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return
    key = (str(config.settings.db_path), row["case_id"])
    with _lock:
        case_lock = _case_locks.setdefault(key, Lock())
    with case_lock:
        while True:
            with db.transaction() as connection:
                row = connection.execute("SELECT * FROM jobs WHERE case_id=? AND status='QUEUED' ORDER BY created_at LIMIT 1", (key[1],)).fetchone()
                if not row:
                    return
                job = Job(row["id"],row["case_id"],row["target_revision"],row["trigger_event_id"])
                connection.execute("UPDATE jobs SET status='RUNNING' WHERE id=?", (job.id,))
            if config.settings.demo_run_delay_s:
                sleep(config.settings.demo_run_delay_s)
            try:
                run(job, extractor=extractor)
            finally:
                with db.transaction() as connection:
                    connection.execute("UPDATE jobs SET status='FINISHED',finished_at=? WHERE id=?", (db.now_iso(),job.id))
