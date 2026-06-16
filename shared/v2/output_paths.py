from __future__ import annotations

from pathlib import PurePosixPath

from shared.v2.errors import INVALID_PATH
from shared.v2.path_utils import InvalidStoragePathError, validate_relative_storage_path


def _validate_job_id(job_id: str) -> str:
    cleaned = (job_id or "").strip()
    if not cleaned:
        raise InvalidStoragePathError(INVALID_PATH)
    if any(token in cleaned for token in ("..", "/", "\\", ":")):
        raise InvalidStoragePathError(INVALID_PATH)
    return cleaned


def _validate_filename(filename: str) -> str:
    cleaned = (filename or "").strip()
    if not cleaned:
        raise InvalidStoragePathError(INVALID_PATH)
    if any(token in cleaned for token in ("..", "/", "\\", ":")):
        raise InvalidStoragePathError(INVALID_PATH)
    return cleaned


def build_job_output_dir(job_id: str, *, output_root: str = "outputs") -> str:
    safe_job_id = _validate_job_id(job_id)
    safe_output_root = validate_relative_storage_path(output_root)
    return validate_relative_storage_path(f"{safe_output_root}/job_{safe_job_id}")


def build_output_relative_path(job_id: str, filename: str, *, output_root: str = "outputs") -> str:
    safe_filename = _validate_filename(filename)
    return validate_relative_storage_path(f"{build_job_output_dir(job_id, output_root=output_root)}/{safe_filename}")


def build_output_url(job_id: str, filename: str, *, api_prefix: str = "/api/v1") -> str:
    safe_job_id = _validate_job_id(job_id)
    safe_filename = _validate_filename(filename)
    normalized_prefix = api_prefix.rstrip("/")
    return f"{normalized_prefix}/outputs/{safe_job_id}/{safe_filename}"


def parse_output_path_to_url(output_path: str, *, api_prefix: str = "/api/v1", output_root: str = "outputs") -> str:
    normalized = validate_relative_storage_path(output_path)
    path = PurePosixPath(normalized)
    safe_output_root = validate_relative_storage_path(output_root)
    parts = path.parts
    if len(parts) < 3 or parts[0] != safe_output_root:
        raise InvalidStoragePathError(INVALID_PATH)
    job_dir = parts[1]
    if not job_dir.startswith("job_") or job_dir == "job_":
        raise InvalidStoragePathError(INVALID_PATH)
    filename = parts[-1]
    return build_output_url(job_dir[4:], filename, api_prefix=api_prefix)
