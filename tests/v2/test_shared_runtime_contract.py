from __future__ import annotations

from pathlib import Path

import pytest


def test_shared_runtime_constants_remain_stable() -> None:
    from shared.v2.constants import V2_CANCEL_KEY_PREFIX, V2_JOB_QUEUE_KEY

    assert V2_JOB_QUEUE_KEY == "studio:v2:jobs"
    assert V2_CANCEL_KEY_PREFIX == "studio:v2:cancel:"


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("CREATED", "queued"),
        ("QUEUED", "queued"),
        ("RUNNING", "processing"),
        ("SUCCEEDED", "finished"),
        ("FAILED", "failed"),
        ("CANCELLED", "cancelled"),
    ],
)
def test_legacy_status_mapping_is_centralized(raw_status: str, expected: str) -> None:
    from shared.v2.status import map_v2_status_to_legacy

    assert map_v2_status_to_legacy(raw_status) == expected


def test_output_path_builder_returns_relative_outputs() -> None:
    from shared.v2.output_paths import build_job_output_dir, build_output_relative_path, build_output_url

    assert build_job_output_dir("abc-123") == "outputs/job_abc-123"
    assert build_output_relative_path("abc-123", "result.png") == "outputs/job_abc-123/result.png"
    assert build_output_url("abc-123", "result.png") == "/api/v1/outputs/abc-123/result.png"


@pytest.mark.parametrize("bad_job_id", ["", "../escape", "C:bad", r"bad\path", "bad/path"])
def test_output_path_builder_rejects_bad_job_id(bad_job_id: str) -> None:
    from shared.v2.output_paths import build_job_output_dir
    from shared.v2.path_utils import InvalidStoragePathError

    with pytest.raises(InvalidStoragePathError):
        build_job_output_dir(bad_job_id)


@pytest.mark.parametrize("bad_filename", ["", "../escape.png", "C:bad.png", r"bad\path.png", "bad/path.png"])
def test_output_path_builder_rejects_bad_filename(bad_filename: str) -> None:
    from shared.v2.output_paths import build_output_relative_path
    from shared.v2.path_utils import InvalidStoragePathError

    with pytest.raises(InvalidStoragePathError):
        build_output_relative_path("abc-123", bad_filename)


def test_canned_errors_are_non_empty_and_mask_raw_exception_strings() -> None:
    from shared.v2.errors import (
        COMFYUI_UNAVAILABLE,
        ENGINE_EXECUTION_FAILED,
        INTERNAL_ERROR,
        INVALID_ASSET_UPLOAD,
        INVALID_PATH,
        JOB_NOT_FOUND,
        OUTPUT_NOT_FOUND,
        REDIS_UNAVAILABLE,
        WORKFLOW_NOT_FOUND,
    )

    for message in [
        REDIS_UNAVAILABLE,
        JOB_NOT_FOUND,
        INVALID_ASSET_UPLOAD,
        INVALID_PATH,
        WORKFLOW_NOT_FOUND,
        ENGINE_EXECUTION_FAILED,
        COMFYUI_UNAVAILABLE,
        OUTPUT_NOT_FOUND,
        INTERNAL_ERROR,
    ]:
        assert message
        assert "{e}" not in message
        assert "Traceback" not in message


def test_shared_runtime_config_resolves_repo_relative_paths() -> None:
    from shared.v2.runtime_config import resolve_repo_relative_path

    repo_root = Path(__file__).resolve().parents[2]
    assert resolve_repo_relative_path("./storage", repo_root=repo_root).endswith("/storage")
    assert resolve_repo_relative_path("/tmp", repo_root=repo_root) == Path("/tmp").resolve().as_posix()
