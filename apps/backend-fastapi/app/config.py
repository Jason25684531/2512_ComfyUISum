from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from shared.runtime_settings import V2RuntimeSettings, resolve_v2_env_file, resolve_v2_repo_root


REPO_ROOT = resolve_v2_repo_root(__file__)


class Settings(V2RuntimeSettings):
    repo_root: ClassVar[Path] = REPO_ROOT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_env_file=resolve_v2_env_file(REPO_ROOT))
