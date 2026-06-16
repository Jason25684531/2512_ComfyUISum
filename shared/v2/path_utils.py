from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:(?:[\\/]|$)")
WINDOWS_UNC_PATTERN = re.compile(r"^(//|\\\\)[^/\\]+[\\/][^/\\]+")


class InvalidStoragePathError(ValueError):
    """Raised when a path violates the Linux-first storage contract."""


def validate_linux_first_path(value: str, *, key: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidStoragePathError(f"{key} must not be empty.")
    if "\x00" in cleaned:
        raise InvalidStoragePathError(f"{key} must not contain null bytes.")
    if "\\" in cleaned:
        raise InvalidStoragePathError(f"{key} must use forward slashes.")
    if WINDOWS_DRIVE_PATTERN.match(cleaned):
        raise InvalidStoragePathError(f"{key} must not use a Windows absolute path.")
    if WINDOWS_UNC_PATTERN.match(cleaned):
        raise InvalidStoragePathError(f"{key} must not use UNC paths.")
    return cleaned


def validate_relative_storage_path(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidStoragePathError("Persisted paths must not be empty.")
    if "\x00" in cleaned:
        raise InvalidStoragePathError("Persisted paths must not contain null bytes.")
    if "\\" in cleaned:
        raise InvalidStoragePathError("Persisted paths must use forward slashes only.")
    if WINDOWS_DRIVE_PATTERN.match(cleaned):
        raise InvalidStoragePathError("Persisted paths must not use Windows absolute paths.")
    if WINDOWS_UNC_PATTERN.match(cleaned):
        raise InvalidStoragePathError("Persisted paths must not use UNC paths.")

    path = PurePosixPath(cleaned)
    if path.is_absolute():
        raise InvalidStoragePathError("Persisted paths must be relative to STORAGE_ROOT.")

    normalized = path.as_posix()
    if normalized in {".", ".."}:
        raise InvalidStoragePathError("Persisted paths must point to a file or directory inside STORAGE_ROOT.")
    if any(part in {"..", "."} for part in path.parts):
        raise InvalidStoragePathError("Persisted paths must not traverse outside STORAGE_ROOT.")
    return normalized


def resolve_storage_path(storage_root: str | Path, relative_path: str) -> Path:
    root = Path(storage_root).resolve()
    safe_relative = validate_relative_storage_path(relative_path)
    resolved = (root / safe_relative).resolve()
    if not resolved.is_relative_to(root):
        raise InvalidStoragePathError("Resolved path escapes STORAGE_ROOT.")
    return resolved


def ensure_storage_layout(
    storage_root: str | Path,
    *,
    asset_root: str = "assets",
    output_root: str = "outputs",
) -> None:
    root = Path(storage_root).resolve()
    directories = [
        root / validate_relative_storage_path(asset_root),
        root / validate_relative_storage_path(output_root),
        root / "temp",
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
