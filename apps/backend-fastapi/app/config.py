from __future__ import annotations

from functools import lru_cache

from shared.runtime_settings import V2RuntimeSettings, resolve_v2_env_file, resolve_v2_repo_root


REPO_ROOT = resolve_v2_repo_root(__file__)
Settings = V2RuntimeSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_env_file=resolve_v2_env_file(REPO_ROOT))
