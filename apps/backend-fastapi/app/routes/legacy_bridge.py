# [LEGACY-BRIDGE] This module bridges legacy frontend to v2 API. Remove when frontend migrates.
from __future__ import annotations

from html import escape

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.job import JobPayload, JobStatus
from app.services.redis_client import QueueUnavailableError
from shared.v2.errors import JOB_NOT_FOUND, REDIS_UNAVAILABLE
from shared.v2.model_safety import sanitize_text_to_image_model, text_to_image_model_options
from shared.v2.output_paths import parse_output_path_to_url


router = APIRouter()
LEGACY_STATUS_BY_V2_STATUS = {
    JobStatus.CREATED: "queued",
    JobStatus.QUEUED: "queued",
    JobStatus.RUNNING: "running",
    JobStatus.SUCCEEDED: "finished",
    JobStatus.FAILED: "failed",
    JobStatus.CANCELLED: "cancelled",
}


class LegacyGenerateRequest(BaseModel):
    prompt: str = ""
    negative_prompt: str = ""
    workflow: str = ""
    seed: int = -1
    model: str = ""
    aspect_ratio: str = ""
    batch_size: int = 1
    width: int | None = None
    height: int | None = None
    steps: int | None = None
    images: dict = Field(default_factory=dict)


def _aspect_ratio_to_dimensions(aspect_ratio: str) -> tuple[int, int] | None:
    return {
        "1:1": (1024, 1024),
        "16:9": (1344, 768),
        "9:16": (768, 1344),
        "4:3": (1152, 896),
        "3:4": (896, 1152),
    }.get((aspect_ratio or "").strip())


def _legacy_bridge_status(v2_status: JobStatus) -> str:
    return LEGACY_STATUS_BY_V2_STATUS.get(v2_status, "failed")


def _public_error_message(record: dict) -> str:
    raw_message = record.get("error_message") or "Job failed. Please retry."
    return escape(str(raw_message), quote=True)


@router.get("/me", include_in_schema=False)
def legacy_me(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "logged_in": False,
        "authenticated": False,
        "mode": "local-v2",
        "user": {
            "id": "local",
            "name": "Local User",
            "email": "local@studio-core.invalid",
            "tier": settings.default_tier,
        },
    }


@router.get("/models", include_in_schema=False)
def legacy_models(request: Request) -> dict:
    registry = request.app.state.workflow_registry
    text_to_image_ready = registry.get("text_to_image") is not None
    settings = request.app.state.settings
    model_options = text_to_image_model_options()
    return {
        "success": True,
        "models": model_options,
        "by_task_type": {"text_to_image": text_to_image_model_options()},
        "unet_models": [model_options[0]["value"]],
        "checkpoint_models": [],
        "items": [
            {
                "id": "text_to_image",
                "name": "Text to Image",
                "task_type": "text_to_image",
                "engine_mode": settings.engine_mode,
                "execution_ready": text_to_image_ready,
            }
        ],
    }


@router.post("/generate", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def legacy_generate(payload: LegacyGenerateRequest, request: Request) -> dict:
    task_type = "text_to_image"

    registry = request.app.state.workflow_registry
    if registry.get(task_type) is None:
        raise HTTPException(status_code=422, detail="Unsupported workflow task type.")

    from app.routes.jobs import _now

    now = _now()
    dimensions = _aspect_ratio_to_dimensions(payload.aspect_ratio)
    params = {
        "prompt": payload.prompt,
        "negative_prompt": payload.negative_prompt,
        "seed": payload.seed,
        "model": sanitize_text_to_image_model(payload.model),
        "aspect_ratio": payload.aspect_ratio,
        "batch_size": payload.batch_size,
    }
    if payload.width is not None:
        params["width"] = payload.width
    elif dimensions is not None:
        params["width"] = dimensions[0]
    if payload.height is not None:
        params["height"] = payload.height
    elif dimensions is not None:
        params["height"] = dimensions[1]
    if payload.steps is not None:
        params["steps"] = payload.steps

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
        store.delete_job(str(job.job_id))
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
    legacy_status = _legacy_bridge_status(v2_status)
    result = {
        "job_id": job_id,
        "status": legacy_status,
        "state": legacy_status,
        "success": v2_status == JobStatus.SUCCEEDED,
    }

    if v2_status == JobStatus.SUCCEEDED and record.get("output_path"):
        output_url = parse_output_path_to_url(record["output_path"])
        result["output_url"] = output_url
        result["image_url"] = output_url
        result["image_path"] = output_url
        result["result_url"] = output_url
        result["output_path"] = record["output_path"]

    if v2_status == JobStatus.FAILED:
        error_message = _public_error_message(record)
        result["error_message"] = error_message
        result["error"] = error_message

    return result
