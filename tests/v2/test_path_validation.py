from __future__ import annotations

import pytest


def test_validate_relative_storage_path_accepts_forward_slash_relative_path() -> None:
    from app.services.path_validator import validate_relative_storage_path

    assert (
        validate_relative_storage_path("outputs/job_123/result.png")
        == "outputs/job_123/result.png"
    )


@pytest.mark.parametrize(
    "raw_path",
    [
        r"C:\bad.png",
        "D:/bad.png",
        "//server/share/bad.png",
        "../escape.png",
        r"outputs\bad.png",
        "/absolute/path.png",
        "outputs/job_123/\x00bad.png",
    ],
)
def test_validate_relative_storage_path_rejects_windows_and_traversal_paths(raw_path) -> None:
    from app.services.path_validator import InvalidStoragePathError, validate_relative_storage_path

    with pytest.raises(InvalidStoragePathError):
        validate_relative_storage_path(raw_path)
