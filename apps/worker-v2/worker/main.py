from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis

from app.models.job import JobPayload, JobStatus
from shared.v2 import JobStore
from worker.config import WorkerSettings, get_worker_settings
from worker.engines.comfyui_engine import ComfyUIEngine
from worker.engines.mock_engine import MockEngine
from workflow_registry.registry import WorkflowRegistry


LOGGER = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(
        self,
        *,
        settings: WorkerSettings,
        workflow_registry: WorkflowRegistry | None = None,
        job_store: JobStore | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.settings = settings
        self.workflow_registry = workflow_registry or self._default_registry()
        self.job_store = job_store or JobStore(settings.database_url)
        self.job_store.initialize()
        self.redis_client = redis_client or redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self.engine = self._build_engine()

    def _default_registry(self) -> WorkflowRegistry:
        from pathlib import Path

        manifests_dir = Path(__file__).resolve().parents[3] / "packages" / "workflow_registry" / "manifests"
        return WorkflowRegistry.from_directory(manifests_dir)

    def _build_engine(self):
        if self.settings.engine_mode == "comfyui":
            return ComfyUIEngine(settings=self.settings)
        return MockEngine(settings=self.settings, workflow_registry=self.workflow_registry)

    def process_payload(self, raw_payload: str) -> None:
        try:
            parsed = json.loads(raw_payload)
            job = JobPayload.model_validate(parsed)
        except Exception:
            LOGGER.warning("Worker received an invalid job payload.")
            return

        record = self.job_store.get_job(str(job.job_id))
        if record is not None and record["status"] == JobStatus.CANCELLED.value:
            self._clear_cancel(job.job_id)
            return

        if self.workflow_registry.get(job.task_type) is None:
            self._update_job(job, status=JobStatus.FAILED, error_message="Workflow manifest was not found.")
            return

        self._update_job(job, status=JobStatus.RUNNING)
        if self._cancel_requested(job.job_id):
            self._update_job(job, status=JobStatus.CANCELLED, cancel_requested=True)
            self._clear_cancel(job.job_id)
            return
        try:
            result = self.engine.execute(job)
        except NotImplementedError:
            self._update_job(job, status=JobStatus.FAILED, error_message="Engine execution is not available yet.")
            return
        except Exception:
            self._update_job(job, status=JobStatus.FAILED, error_message="Job execution failed.")
            return

        if self._cancel_requested(job.job_id):
            self._update_job(job, status=JobStatus.CANCELLED, cancel_requested=True)
            self._clear_cancel(job.job_id)
            return

        if result.success and result.output_path:
            self._update_job(job, status=JobStatus.SUCCEEDED, output_path=result.output_path)
            self._clear_cancel(job.job_id)
            return
        self._update_job(job, status=JobStatus.FAILED, error_message=result.error_message or "Job execution failed.")
        self._clear_cancel(job.job_id)

    def run_forever(self) -> None:
        while True:
            _, raw_payload = self.redis_client.brpop(self.settings.queue_key)
            self.process_payload(raw_payload)

    def _update_job(
        self,
        job: JobPayload,
        *,
        status: JobStatus,
        output_path: str | None = None,
        error_message: str | None = None,
        cancel_requested: bool | None = None,
    ) -> None:
        self.job_store.update_job(
            str(job.job_id),
            status=status.value,
            updated_at=datetime.now(timezone.utc).isoformat(),
            output_path=output_path,
            error_message=error_message,
            cancel_requested=cancel_requested,
        )

    def _cancel_requested(self, job_id) -> bool:
        try:
            return bool(self.redis_client.exists(f"studio:v2:cancel:{job_id}"))
        except Exception:
            record = self.job_store.get_job(str(job_id))
            return bool(record and record.get("cancel_requested"))

    def _clear_cancel(self, job_id) -> None:
        try:
            self.redis_client.delete(f"studio:v2:cancel:{job_id}")
        except Exception:
            return None


def main() -> None:
    WorkerRunner(settings=get_worker_settings()).run_forever()


if __name__ == "__main__":
    main()
