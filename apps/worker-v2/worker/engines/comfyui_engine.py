from __future__ import annotations

import httpx

from app.models.job import JobPayload
from worker.engines.base import EngineAdapter, EngineResult


class ComfyUIEngine(EngineAdapter):
    def __init__(self, *, settings) -> None:
        self.settings = settings

    def execute(self, job_payload: JobPayload) -> EngineResult:
        raise NotImplementedError("ComfyUI workflow execution is not implemented in the v2 skeleton.")

    def health_check(self) -> bool:
        try:
            response = httpx.get(
                f"{self.settings.comfyui_base_url.rstrip('/')}/system_stats",
                timeout=3.0,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False
