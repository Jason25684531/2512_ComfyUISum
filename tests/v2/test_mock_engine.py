from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("task_type", "expected_suffix"),
    [
        ("text_to_image", ".png"),
        ("text_to_video", ".mp4"),
        ("tts", ".wav"),
    ],
)
def test_mock_engine_writes_relative_outputs(settings, task_type, expected_suffix) -> None:
    from app.models.job import JobPayload
    from worker.engines.mock_engine import MockEngine
    from workflow_registry.registry import WorkflowRegistry

    registry = WorkflowRegistry.from_directory(Path(__file__).resolve().parents[2] / "packages" / "workflow_registry" / "manifests")
    engine = MockEngine(settings=settings, workflow_registry=registry)
    job = JobPayload(task_type=task_type, params={"prompt": "hello"})

    result = engine.execute(job)

    assert result.success is True
    assert result.output_path.endswith(expected_suffix)
    assert "\\" not in result.output_path
    assert result.output_path.startswith(f"outputs/job_{job.job_id}/")
    assert (Path(settings.storage_root) / result.output_path).is_file()
