# [LEGACY-BRIDGE] This module bridges legacy frontend to v2 API. Remove when frontend migrates.
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.job import JobPayload, JobStatus
from app.services.redis_client import QueueUnavailableError
from shared.v2.errors import JOB_NOT_FOUND, REDIS_UNAVAILABLE
from shared.v2.output_paths import parse_output_path_to_url
from shared.v2.status import map_v2_status_to_legacy


router = APIRouter()


class LegacyGenerateRequest(BaseModel):
    prompt: str = ""
    workflow: str = ""
    seed: int = -1
    model: str = ""
    aspect_ratio: str = ""
    batch_size: int = 1
    images: dict = Field(default_factory=dict)


@router.post("/generate", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def legacy_generate(payload: LegacyGenerateRequest, request: Request) -> dict:
    task_type = "text_to_image"

    registry = request.app.state.workflow_registry
    if registry.get(task_type) is None:
        raise HTTPException(status_code=422, detail="Unsupported workflow task type.")

    from app.routes.jobs import _now

    now = _now()
    params = {
        "prompt": payload.prompt,
        "seed": payload.seed,
        "model": payload.model,
        "aspect_ratio": payload.aspect_ratio,
        "batch_size": payload.batch_size,
    }

    job = JobPayload(
        task_type=task_type,
        params=params,
        input_assets=[],
        priority=5,
        client_tag="legacy_frontend",
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
        raise HTTPException(status_code=503, detail=REDIS_UNAVAILABLE) from None

    queued_time = _now()
    store.update_job(
        str(job.job_id),
        status=JobStatus.QUEUED.value,
        updated_at=queued_time.isoformat(),
    )

    return {
        "job_id": str(job.job_id),
        "status": JobStatus.QUEUED.value.lower(),
        "task_type": job.task_type,
        "message": "Job queued.",
    }


@router.get("/status/{job_id}", include_in_schema=False)
def legacy_status(job_id: str, request: Request) -> dict:
    store = request.app.state.job_store
    record = store.get_job(job_id)

    if record is None:
        raise HTTPException(status_code=404, detail=JOB_NOT_FOUND)

    v2_status = JobStatus(record["status"])
    result = {
        "job_id": job_id,
        "status": map_v2_status_to_legacy(v2_status.value),
    }

    if v2_status == JobStatus.SUCCEEDED and record.get("output_path"):
        result["output_url"] = parse_output_path_to_url(record["output_path"])

    if v2_status == JobStatus.FAILED:
        result["error_message"] = "Job failed. Please retry."

    return result
