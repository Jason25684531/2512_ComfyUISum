from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from shared.runtime_settings import V2RuntimeSettings, resolve_v2_env_file, resolve_v2_repo_root


REPO_ROOT = resolve_v2_repo_root(__file__)


class WorkerSettings(V2RuntimeSettings):
    repo_root: ClassVar[Path] = REPO_ROOT


def get_worker_settings() -> WorkerSettings:
    return WorkerSettings(_env_file=resolve_v2_env_file(REPO_ROOT))
