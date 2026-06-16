# [LEGACY-BRIDGE] This module bridges legacy frontend to v2 API. Remove when frontend migrates.
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.job import JobPayload, JobStatus
from app.services.redis_client import QueueUnavailableError


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
    # 1. 強制 task_type = "text_to_image"
    task_type = "text_to_image"
    
    # 2. 驗證 workflow registry 有此 task_type
    registry = request.app.state.workflow_registry
    if registry.get(task_type) is None:
        raise HTTPException(status_code=422, detail="Unsupported workflow task type.")

    # 3. 組裝 JobPayload
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
            error_message="Job queue is temporarily unavailable.",
        )
        raise HTTPException(
            status_code=503,
            detail="Job queue is temporarily unavailable.",
        ) from None

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
        "message": "Job queued."
    }


@router.get("/status/{job_id}", include_in_schema=False)
def legacy_status(job_id: str, request: Request) -> dict:
    store = request.app.state.job_store
    record = store.get_job(job_id)
    
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    v2_status = JobStatus(record["status"])
    
    # Status mapping
    status_mapping = {
        JobStatus.CREATED: "queued",
        JobStatus.QUEUED: "queued",
        JobStatus.RUNNING: "processing",
        JobStatus.SUCCEEDED: "finished",
        JobStatus.FAILED: "failed",
        JobStatus.CANCELLED: "cancelled",
    }
    
    legacy_status_str = status_mapping.get(v2_status, "failed")
    
    result = {
        "job_id": job_id,
        "status": legacy_status_str,
    }
    
    if v2_status == JobStatus.SUCCEEDED and record.get("output_path"):
        # 從 output_path 解析 filename，組裝相對 URL
        output_path = record["output_path"]
        filename = output_path.split("/")[-1]
        result["output_url"] = f"/api/v1/outputs/{job_id}/{filename}"
        
    if v2_status == JobStatus.FAILED:
        result["error_message"] = "Job failed. Please retry."
        
    return result
