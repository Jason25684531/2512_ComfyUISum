from __future__ import annotations

from pathlib import Path
import re


WINDOWS_PATH_PATTERN = re.compile(r"(^[A-Za-z]:[\\/])|(\\\\)|(^/)")


def assert_linux_first_runtime_path(value: str) -> None:
    assert value
    assert "\\" not in value
    assert "C:\\" not in value
    assert "D:\\" not in value
    assert not WINDOWS_PATH_PATTERN.search(value)


def test_runtime_persisted_paths_stay_storage_root_relative(settings) -> None:
    from app.models.job import JobPayload
    from shared.v2 import AssetStore, JobStore
    from worker.engines.mock_engine import MockEngine
    from workflow_registry.registry import WorkflowRegistry

    asset_store = AssetStore(settings.database_url)
    asset_store.initialize()
    asset_record = asset_store.create_asset("sample.txt", "assets/sample.txt")

    job_store = JobStore(settings.database_url)
    job_store.initialize()
    job = JobPayload(task_type="text_to_image", params={"prompt": "safe"})
    job_store.create_job(job.model_dump(mode="json"))

    registry = WorkflowRegistry.from_directory(Path(__file__).resolve().parents[2] / "packages" / "workflow_registry" / "manifests")
    engine = MockEngine(settings=settings, workflow_registry=registry)
    result = engine.execute(job)
    job_store.update_job(
        str(job.job_id),
        status="SUCCEEDED",
        updated_at=job.updated_at.isoformat(),
        output_path=result.output_path,
    )

    job_record = job_store.get_job(str(job.job_id))
    metadata = {"output_path": result.output_path}

    assert_linux_first_runtime_path(asset_record["asset_path"])
    assert_linux_first_runtime_path(job_record["output_path"])
    assert_linux_first_runtime_path(metadata["output_path"])
