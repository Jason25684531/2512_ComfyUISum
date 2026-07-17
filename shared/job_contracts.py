"""Shared, dependency-free job observability contract."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from uuid import UUID


PAYLOAD_SCHEMA_VERSION = 2


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED})
ALLOWED_TRANSITIONS = {
    JobStatus.CREATED: frozenset({JobStatus.QUEUED, JobStatus.FAILED}),
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}),
}
LEGACY_STATUS = {
    JobStatus.CREATED: "queued",
    JobStatus.QUEUED: "queued",
    JobStatus.RUNNING: "processing",
    JobStatus.COMPLETED: "finished",
    JobStatus.FAILED: "failed",
    JobStatus.CANCELLED: "cancelled",
}

EVENT_TYPES = frozenset({
    "job_submitted", "validation_passed", "job_queued", "worker_claimed", "workflow_resolved",
    "workflow_loaded", "comfyui_submitted", "comfyui_started", "node_started", "node_completed",
    "output_received", "output_persisted", "job_completed", "job_failed", "cancel_requested",
    "job_cancelled", "job_retried", "job_timed_out",
})
ERROR_STAGES = frozenset({
    "backend_validation", "database_create", "redis_enqueue", "worker_claim", "workflow_resolve",
    "workflow_parse", "input_processing", "comfyui_connect", "comfyui_submit", "comfyui_execution",
    "output_collection", "output_storage", "database_finalize", "cancellation", "timeout", "unknown",
})
ERROR_CODES = frozenset({
    "VALIDATION_ERROR", "UNSUPPORTED_WORKFLOW", "WORKFLOW_NOT_FOUND", "WORKFLOW_PARSE_ERROR",
    "MODEL_NOT_FOUND", "INPUT_PROCESSING_ERROR", "DATABASE_WRITE_ERROR", "QUEUE_WRITE_ERROR",
    "WORKER_INTERNAL_ERROR", "COMFYUI_UNAVAILABLE", "COMFYUI_SUBMIT_ERROR", "COMFYUI_WEBSOCKET_ERROR",
    "COMFYUI_NODE_ERROR", "COMFYUI_TIMEOUT", "GPU_OUT_OF_MEMORY", "OUTPUT_NOT_FOUND",
    "OUTPUT_PERSIST_ERROR", "JOB_TIMEOUT", "CANCELLED_BY_CLIENT", "UNKNOWN_ERROR",
})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    value = value or utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def is_valid_transition(current: str | JobStatus, target: str | JobStatus) -> bool:
    try:
        current_status, target_status = JobStatus(current), JobStatus(target)
    except ValueError:
        return False
    return target_status in ALLOWED_TRANSITIONS.get(current_status, frozenset())


def duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    if not start or not end:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    result = int((end - start).total_seconds() * 1000)
    return result if result >= 0 else None


def duration_fields(job: dict) -> dict[str, int | None]:
    terminal_at = job.get("completed_at") or job.get("failed_at") or job.get("cancelled_at")
    return {
        "queue_wait_ms": duration_ms(job.get("queued_at"), job.get("started_at")),
        "execution_ms": duration_ms(job.get("started_at"), terminal_at),
        "total_ms": duration_ms(job.get("submitted_at"), terminal_at),
    }


def success_rate(completed: int, failed: int) -> float | None:
    denominator = completed + failed
    return None if denominator == 0 else completed / denominator


def validate_job_payload(payload: object) -> tuple[bool, str | None]:
    """Accept legacy v1 and current v2 without allowing a worker-generated identity."""
    if not isinstance(payload, dict):
        return False, "payload must be an object"
    version = payload.get("schema_version", 1)
    if not isinstance(version, int) or version not in (1, PAYLOAD_SCHEMA_VERSION):
        return False, "unsupported payload schema"
    try:
        UUID(str(payload.get("job_id")))
    except (ValueError, TypeError, AttributeError):
        return False, "invalid job_id"
    if version == PAYLOAD_SCHEMA_VERSION and not all(payload.get(key) for key in ("request_id", "workflow", "submitted_at")):
        return False, "incomplete v2 payload"
    return True, None


def event_key(job_id: str, event_type: str, *, attempt: int = 0, node_id: str = "", milestone: int | None = None) -> str:
    raw = f"{job_id}:{attempt}:{event_type}:{node_id}:{'' if milestone is None else milestone}"
    return sha256(raw.encode("utf-8")).hexdigest()
