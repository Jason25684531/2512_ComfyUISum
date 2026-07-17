"""Central state transitions; callers never construct ad-hoc job events."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from shared.error_sanitizer import sanitize_error
from shared.job_contracts import JobStatus, TERMINAL_STATUSES, duration_fields, event_key, iso_utc, is_valid_transition
from shared.output_receipts import read_receipts, remove_receipt, write_receipt


class JobTracker:
    def __init__(self, repository):
        self.repository = repository

    def create(self, job_id: str, request_id: str, *, workflow_id: str, workflow_version: str, workflow_category: str, model_name: str = "unknown", dispatch_payload: dict[str, Any] | None = None) -> None:
        now = iso_utc()
        job = {
            "job_id": job_id, "request_id": request_id, "status": JobStatus.CREATED.value,
            "workflow_id": workflow_id, "workflow_version": workflow_version, "workflow_category": workflow_category,
            "model_name": model_name, "submitted_at": now, "progress": 0, "retry_count": 0, "output_count": 0,
            "created_at": now, "updated_at": now,
        }
        submitted = {
            "event_key": event_key(job_id, "job_submitted"), "job_id": job_id, "event_type": "job_submitted",
            "stage": None, "resulting_status": JobStatus.CREATED.value, "node_id": None, "node_type": None,
            "progress_milestone": None, "error_code": None, "sanitized_message": None, "metadata": {}, "created_at": now,
        }
        if dispatch_payload is None:
            self.repository.create_job(job)
            self.repository.add_event(submitted)
        else:
            self.repository.create_job_with_dispatch(job, submitted, dispatch_payload)

    def event(self, job_id: str, event_type: str, *, resulting_status: str | None = None, stage: str | None = None,
              node_id: str | None = None, node_type: str | None = None, milestone: int | None = None,
              error_code: str | None = None, message: object | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.repository.add_event({
            "event_key": event_key(job_id, event_type, node_id=node_id or "", milestone=milestone), "job_id": job_id,
            "event_type": event_type, "stage": stage, "resulting_status": resulting_status, "node_id": node_id,
            "node_type": node_type, "progress_milestone": milestone, "error_code": error_code,
            "sanitized_message": sanitize_error(message) if message else None, "metadata": metadata or {}, "created_at": iso_utc(),
        })

    def transition(self, job_id: str, current: JobStatus, target: JobStatus, **updates: Any) -> bool:
        if not is_valid_transition(current, target):
            return False
        now = iso_utc()
        updates.update(status=target.value, updated_at=now, last_event_at=now)
        timestamp = {JobStatus.QUEUED: "queued_at", JobStatus.RUNNING: "started_at", JobStatus.COMPLETED: "completed_at",
                     JobStatus.FAILED: "failed_at", JobStatus.CANCELLED: "cancelled_at"}.get(target)
        if timestamp:
            updates[timestamp] = now
        job = self.repository.get_job(job_id) or {}
        parsed = {key: _parse_time(value) for key, value in job.items() if key.endswith("_at")}
        parsed.update({key: _parse_time(value) for key, value in updates.items() if key.endswith("_at")})
        updates.update(duration_fields(parsed))
        return self.repository.transition(job_id, (current.value,), updates)

    def fail(self, job_id: str, current: JobStatus, *, stage: str, code: str, message: object) -> bool:
        if not self.transition(job_id, current, JobStatus.FAILED, error_stage=stage, error_code=code,
                               sanitized_error_message=sanitize_error(message)):
            return False
        self.event(job_id, "job_failed", resulting_status="failed", stage=stage, error_code=code, message=message)
        return True

    def set_prompt_id(self, job_id: str, prompt_id: str) -> bool:
        return self.repository.update_if_status(job_id, JobStatus.RUNNING.value, {"comfyui_prompt_id": prompt_id, "updated_at": iso_utc()})

    def update_node(self, job_id: str, *, node_id: str, node_type: str, completed: bool = False) -> bool:
        updates = {"updated_at": iso_utc()}
        if completed:
            updates["last_completed_node_id"] = node_id
        else:
            updates.update(current_node_id=node_id, current_node_type=node_type)
        return self.repository.update_if_status(job_id, JobStatus.RUNNING.value, updates)

    def progress(self, job_id: str, value: int) -> bool:
        return self.repository.update_if_status(job_id, JobStatus.RUNNING.value, {"progress": max(0, min(100, int(value))), "updated_at": iso_utc()})

    def request_cancel(self, job_id: str, current: JobStatus) -> bool:
        if current is JobStatus.QUEUED:
            changed = self.transition(job_id, current, JobStatus.CANCELLED,
                                      error_stage="cancellation", error_code="CANCELLED_BY_CLIENT")
            if changed:
                self.event(job_id, "cancel_requested", resulting_status="queued", stage="cancellation", error_code="CANCELLED_BY_CLIENT")
                self.event(job_id, "job_cancelled", resulting_status="cancelled", stage="cancellation", error_code="CANCELLED_BY_CLIENT")
            return changed
        if current is JobStatus.RUNNING:
            changed = self.repository.update_if_status(job_id, current.value, {"cancel_requested_at": iso_utc(), "updated_at": iso_utc()})
            if changed:
                self.event(job_id, "cancel_requested", resulting_status="running", stage="cancellation", error_code="CANCELLED_BY_CLIENT")
            return changed
        return False

    def complete_with_output(self, job_id: str, *, path: Path, storage_uri: str, filename: str,
                             output_type: str, source_node_id: str | None = None,
                             metadata: dict[str, Any] | None = None) -> bool:
        """Only complete after the copied output exists and its metadata is durable."""
        if not path.is_file() or path.stat().st_size <= 0:
            raise FileNotFoundError(f"verified output missing: {path.name}")
        now = iso_utc()
        receipt = {"job_id": job_id, "filename": filename, "storage_uri": storage_uri,
                   "output_type": output_type, "source_node_id": source_node_id, "metadata": metadata or {}}
        write_receipt(path.parent, job_id, receipt)
        job = self.repository.get_job(job_id) or {}
        times = {key: _parse_time(value) for key, value in job.items() if key.endswith("_at")}
        times["completed_at"] = _parse_time(now)
        updates = {
            "status": JobStatus.COMPLETED.value, "completed_at": now, "updated_at": now,
            "last_event_at": now, "output_count": 1, **duration_fields(times),
        }
        output = {
            "job_id": job_id, "source_node_id": source_node_id, "output_type": output_type,
            "storage_uri": storage_uri, "filename": filename, "size_bytes": path.stat().st_size,
            "checksum": sha256(path.read_bytes()).hexdigest(), "metadata": metadata or {}, "persisted_at": now,
        }
        def event(event_type: str, message: str | None = None) -> dict[str, Any]:
            return {
                "event_key": event_key(job_id, event_type), "job_id": job_id, "event_type": event_type,
                "stage": "output_storage" if event_type != "job_completed" else None,
                "resulting_status": JobStatus.COMPLETED.value if event_type == "job_completed" else JobStatus.RUNNING.value,
                "node_id": source_node_id, "node_type": None, "progress_milestone": 100 if event_type == "job_completed" else None,
                "error_code": None, "sanitized_message": message, "metadata": metadata or {}, "created_at": now,
            }
        completed = self.repository.finalize_completed(job_id, updates, output, [
            event("output_received", "output verified"), event("output_persisted", "output metadata persisted"), event("job_completed"),
        ])
        if completed:
            remove_receipt(path.parent, job_id)
        return completed

    def replay_output_receipts(self, output_root: Path) -> int:
        """Finalize verified outputs after a database outage without rerunning ComfyUI."""
        replayed = 0
        for item in read_receipts(output_root):
            path = output_root / item["filename"]
            if self.complete_with_output(item["job_id"], path=path, storage_uri=item["storage_uri"],
                                         filename=item["filename"], output_type=item["output_type"],
                                         source_node_id=item.get("source_node_id"), metadata=item.get("metadata")):
                replayed += 1
        return replayed


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
