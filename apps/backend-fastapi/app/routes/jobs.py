from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app.models.job import JobCreateRequest, JobPayload, JobStatus
from app.services.redis_client import QueueUnavailableError
from shared.v2.errors import REDIS_UNAVAILABLE


router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_limit(limit: int) -> int:
    if limit <= 0:
        return 1
    if limit <= 20:
        return limit
    if limit <= 100:
        return limit
    return 100


def _load_job_or_404(request: Request, job_id: str) -> dict:
    record = request.app.state.job_store.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job was not found.")
    return record


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreateRequest, request: Request) -> dict:
    registry = request.app.state.workflow_registry
    if registry.get(payload.task_type) is None:
        raise HTTPException(status_code=422, detail="Unsupported workflow task type.")

    now = _now()
    job = JobPayload(
        task_type=payload.task_type,
        params=payload.params,
        input_assets=payload.input_assets,
        priority=payload.priority,
        session_id=payload.session_id,
        client_tag=payload.client_tag,
        created_at=now,
        updated_at=now,
    )

    store = request.app.state.job_store
    store.create_job(job.model_dump(mode="json"))

    try:
        request.app.state.queue_client.enqueue_job(job.model_dump_json())
    except QueueUnavailableError:
        failure_time = _now()
        store.update_job(
            str(job.job_id),
            status=JobStatus.FAILED.value,
            updated_at=failure_time.isoformat(),
            error_message=REDIS_UNAVAILABLE,
        )
        raise HTTPException(
            status_code=503,
            detail=REDIS_UNAVAILABLE,
        ) from None

    queued_time = _now()
    store.update_job(
        str(job.job_id),
        status=JobStatus.QUEUED.value,
        updated_at=queued_time.isoformat(),
    )
    record = store.get_job(str(job.job_id))
    return JobPayload.model_validate(record).model_dump(mode="json")


@router.get("/jobs")
def list_jobs(request: Request, offset: int = 0, limit: int = 20) -> dict:
    items, total = request.app.state.job_store.list_jobs(offset=offset, limit=_clamp_limit(limit))
    return {
        "items": [JobPayload.model_validate(item).model_dump(mode="json") for item in items],
        "total": total,
        "offset": offset,
        "limit": _clamp_limit(limit),
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    record = _load_job_or_404(request, job_id)
    return JobPayload.model_validate(record).model_dump(mode="json")


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict:
    store = request.app.state.job_store
    record = _load_job_or_404(request, job_id)
    current_status = JobStatus(record["status"])

    if current_status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Job is already finished.")

    update_time = _now().isoformat()
    try:
        request.app.state.queue_client.request_cancel(job_id)
    except QueueUnavailableError:
        raise HTTPException(status_code=503, detail=REDIS_UNAVAILABLE) from None

    if current_status == JobStatus.RUNNING:
        store.update_job(job_id, updated_at=update_time, cancel_requested=True)
    else:
        store.update_job(
            job_id,
            status=JobStatus.CANCELLED.value,
            updated_at=update_time,
            cancel_requested=True,
        )

    refreshed = store.get_job(job_id)
    return JobPayload.model_validate(refreshed).model_dump(mode="json")
