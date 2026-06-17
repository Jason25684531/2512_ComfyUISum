from __future__ import annotations

from pathlib import Path


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def exists(self, key: str) -> int:
        return 1 if key in self.values else 0

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def _build_runner(settings, fake_redis: FakeRedisClient):
    from shared.v2 import JobStore
    from worker.main import WorkerRunner
    from workflow_registry.registry import WorkflowRegistry

    registry = WorkflowRegistry.from_directory(Path(__file__).resolve().parents[2] / "packages" / "workflow_registry" / "manifests")
    store = JobStore(settings.database_url)
    store.initialize()
    return WorkerRunner(
        settings=settings,
        workflow_registry=registry,
        job_store=store,
        redis_client=fake_redis,
    )


def test_worker_marks_cancelled_before_engine_execution(settings) -> None:
    from app.models.job import JobPayload, JobStatus

    fake_redis = FakeRedisClient()
    runner = _build_runner(settings, fake_redis)
    job = JobPayload(task_type="text_to_image", params={"prompt": "cancel"})
    runner.job_store.create_job(job.model_dump(mode="json"))
    runner.job_store.update_job(
        str(job.job_id),
        status=JobStatus.QUEUED.value,
        updated_at=job.updated_at.isoformat(),
    )
    fake_redis.set(f"studio:v2:cancel:{job.job_id}", "1")

    runner.process_payload(job.model_dump_json())

    record = runner.job_store.get_job(str(job.job_id))
    assert record is not None
    assert record["status"] == JobStatus.CANCELLED.value
    assert record["output_path"] is None


def test_worker_masks_engine_failure(settings, monkeypatch) -> None:
    from app.models.job import JobPayload, JobStatus

    fake_redis = FakeRedisClient()
    runner = _build_runner(settings, fake_redis)
    job = JobPayload(task_type="text_to_image", params={"prompt": "boom"})
    runner.job_store.create_job(job.model_dump(mode="json"))
    runner.job_store.update_job(
        str(job.job_id),
        status=JobStatus.QUEUED.value,
        updated_at=job.updated_at.isoformat(),
    )

    def raise_engine_error(_job):
        raise RuntimeError("raw secret exception")

    monkeypatch.setattr(runner.engine, "execute", raise_engine_error)

    runner.process_payload(job.model_dump_json())

    record = runner.job_store.get_job(str(job.job_id))
    assert record is not None
    assert record["status"] == JobStatus.FAILED.value
    assert record["error_message"] == "Job execution failed."


def test_worker_persists_sanitized_engine_result_failure(settings, monkeypatch) -> None:
    from app.models.job import JobPayload, JobStatus
    from worker.engines.base import EngineResult

    fake_redis = FakeRedisClient()
    runner = _build_runner(settings, fake_redis)
    job = JobPayload(task_type="text_to_image", params={"prompt": "timeout"})
    runner.job_store.create_job(job.model_dump(mode="json"))
    runner.job_store.update_job(
        str(job.job_id),
        status=JobStatus.QUEUED.value,
        updated_at=job.updated_at.isoformat(),
    )

    monkeypatch.setattr(
        runner.engine,
        "execute",
        lambda _job: EngineResult(success=False, error_message="ComfyUI history polling timed out."),
    )

    runner.process_payload(job.model_dump_json())

    record = runner.job_store.get_job(str(job.job_id))
    assert record is not None
    assert record["status"] == JobStatus.FAILED.value
    assert record["error_message"] == "ComfyUI history polling timed out."
    assert record["output_path"] is None


def test_worker_cancels_after_engine_execution(settings, monkeypatch) -> None:
    from app.models.job import JobPayload, JobStatus
    from worker.engines.base import EngineResult

    fake_redis = FakeRedisClient()
    runner = _build_runner(settings, fake_redis)
    job = JobPayload(task_type="text_to_image", params={"prompt": "late cancel"})
    runner.job_store.create_job(job.model_dump(mode="json"))
    runner.job_store.update_job(
        str(job.job_id),
        status=JobStatus.QUEUED.value,
        updated_at=job.updated_at.isoformat(),
    )

    def mark_cancel_during_execute(_job):
        fake_redis.set(f"studio:v2:cancel:{job.job_id}", "1")
        return EngineResult(success=True, output_path=f"outputs/job_{job.job_id}/result.png")

    monkeypatch.setattr(runner.engine, "execute", mark_cancel_during_execute)

    runner.process_payload(job.model_dump_json())

    record = runner.job_store.get_job(str(job.job_id))
    assert record is not None
    assert record["status"] == JobStatus.CANCELLED.value
    assert record["output_path"] is None
