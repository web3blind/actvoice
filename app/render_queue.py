from __future__ import annotations

import json
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable

from app.config import SQLITE_DB_PATH
from app.models import RenderJob, RenderStatus
from app.render import RenderService
from app.store import ProjectStore


class RenderQueue:
    """SQLite-backed render queue for hosted MVP deployments.

    POST /render returns a queued job immediately, while worker threads perform
    deterministic server-side rendering. Job records are persisted in SQLite, so
    completed/failed status survives process restarts and interrupted
    queued/rendering jobs can be recovered on startup.
    """

    def __init__(
        self,
        store: ProjectStore,
        render_service: RenderService | None = None,
        max_workers: int | None = None,
        db_path: Path | None = None,
        auto_resume: bool = True,
    ):
        self.store = store
        self.render_service = render_service or RenderService(store)
        if self.render_service.store is not store:
            self.render_service.store = store
        workers = max_workers or int(os.getenv("ACTVOICE_RENDER_WORKERS", "1"))
        self.executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="actvoice-render")
        self.db_path = Path(db_path) if db_path is not None else getattr(store, "db_path", SQLITE_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs: Dict[str, RenderJob] = {}
        self._lock = threading.Lock()
        self._init_db()
        self._load_jobs()
        self._recover_interrupted_jobs()
        if auto_resume:
            self.resume_pending_jobs()

    def submit(self, project_id: str) -> RenderJob:
        job = RenderJob(project_id=project_id, status=RenderStatus.queued, progress=0.0)
        with self._lock:
            self.jobs[job.id] = job
            self._save_job_unlocked(job)
            snapshot = _copy_job(job)
        self.executor.submit(self._run_job, job.id)
        return snapshot

    def get_job(self, job_id: str) -> RenderJob:
        with self._lock:
            if job_id in self.jobs:
                return _copy_job(self.jobs[job_id])
            job = self._load_job_unlocked(job_id)
            self.jobs[job.id] = job
            return _copy_job(job)

    def save_job(self, job: RenderJob) -> None:
        """Persist an externally supplied job snapshot.

        This is mainly useful for tests and future admin/recovery tooling.
        """
        with self._lock:
            self.jobs[job.id] = _copy_job(job)
            self._save_job_unlocked(job)

    def resume_pending_jobs(self) -> None:
        for job in self._pending_jobs_snapshot():
            self.executor.submit(self._run_job, job.id)

    def _pending_jobs_snapshot(self) -> Iterable[RenderJob]:
        with self._lock:
            return [
                _copy_job(job)
                for job in self.jobs.values()
                if job.status in {RenderStatus.queued, RenderStatus.rendering}
            ]

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self.jobs.get(job_id) or self._load_job_unlocked(job_id)
            self.jobs[job_id] = job
            job.status = RenderStatus.rendering
            job.progress = 0.05
            job.error = None
            self._save_job_unlocked(job)
        try:
            project = self.store.get(job.project_id)
            artifact = self.render_service._render(project, job)
            project.artifact = artifact
            self.store.save(project)
            with self._lock:
                job.artifact = artifact
                job.status = RenderStatus.done
                job.progress = 1.0
                job.error = None
                self._save_job_unlocked(job)
        except Exception as exc:  # noqa: BLE001 - render jobs should fail as status, not crash worker
            with self._lock:
                job.status = RenderStatus.failed
                job.error = str(exc)
                self._save_job_unlocked(job)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS render_jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    error TEXT,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_render_jobs_project_id ON render_jobs(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs(status)")

    def _load_jobs(self) -> None:
        with self._connect() as conn:
            rows = conn.execute("SELECT data FROM render_jobs").fetchall()
        with self._lock:
            for row in rows:
                job = _job_from_json(row["data"])
                self.jobs[job.id] = job

    def _load_job_unlocked(self, job_id: str) -> RenderJob:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM render_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return _job_from_json(row["data"])

    def _save_job_unlocked(self, job: RenderJob) -> None:
        payload = json.dumps(_model_to_dict(job), ensure_ascii=False, indent=2)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO render_jobs (id, project_id, status, progress, error, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    project_id = excluded.project_id,
                    status = excluded.status,
                    progress = excluded.progress,
                    error = excluded.error,
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (job.id, job.project_id, str(job.status.value if hasattr(job.status, "value") else job.status), job.progress, job.error, payload),
            )

    def _recover_interrupted_jobs(self) -> None:
        changed = False
        with self._lock:
            for job in self.jobs.values():
                if job.status == RenderStatus.rendering:
                    job.status = RenderStatus.queued
                    job.progress = 0.0
                    job.error = "Recovered after process restart before render completed."
                    self._save_job_unlocked(job)
                    changed = True
        if changed:
            # No-op hook for clarity; persistence already happened per changed job.
            return


def _copy_job(job: RenderJob) -> RenderJob:
    if hasattr(job, "model_copy"):
        return job.model_copy(deep=True)
    return job.copy(deep=True)


def _model_to_dict(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _job_from_json(raw: str) -> RenderJob:
    if hasattr(RenderJob, "model_validate_json"):
        return RenderJob.model_validate_json(raw)
    return RenderJob.parse_raw(raw)
