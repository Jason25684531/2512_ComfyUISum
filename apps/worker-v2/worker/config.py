from __future__ import annotations

from shared.runtime_settings import V2RuntimeSettings, resolve_v2_env_file, resolve_v2_repo_root


REPO_ROOT = resolve_v2_repo_root(__file__)
WorkerSettings = V2RuntimeSettings


def get_worker_settings() -> WorkerSettings:
    return WorkerSettings(_env_file=resolve_v2_env_file(REPO_ROOT))
