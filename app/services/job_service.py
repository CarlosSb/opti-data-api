from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.schemas import JobRecord, JobStatus


_jobs: dict[str, JobRecord] = {}
_lock = Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(
    job_type: str,
    callback_url: str | None = None,
    tenant_id: str | None = None,
    correlation_id: str | None = None,
) -> JobRecord:
    now = utc_now()
    job = JobRecord(
        job_id=str(uuid4()),
        type=job_type,
        status=JobStatus.queued,
        created_at=now,
        updated_at=now,
        callback_url=callback_url,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> JobRecord | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 50) -> list[JobRecord]:
    with _lock:
        return sorted(_jobs.values(), key=lambda job: job.created_at, reverse=True)[:limit]


def mark_processing(job_id: str) -> JobRecord | None:
    return _update_job(job_id, status=JobStatus.processing)


def mark_completed(job_id: str, result: dict) -> JobRecord | None:
    return _update_job(job_id, status=JobStatus.completed, result=result, error=None)


def mark_failed(job_id: str, error: str) -> JobRecord | None:
    return _update_job(job_id, status=JobStatus.failed, error=error)


def _update_job(job_id: str, **changes) -> JobRecord | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        updated = job.model_copy(update={**changes, "updated_at": utc_now()})
        _jobs[job_id] = updated
        return updated
