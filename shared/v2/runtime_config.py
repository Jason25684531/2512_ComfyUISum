from __future__ import annotations

from pathlib import Path


def resolve_repo_relative_path(raw_value: str, *, repo_root: str | Path) -> str:
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate.resolve().as_posix()
    return (Path(repo_root).resolve() / candidate).resolve().as_posix()
