from __future__ import annotations

from fastapi import APIRouter, Request

from worker.engines.comfyui_engine import ComfyUIEngine


router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    queue_client = request.app.state.queue_client
    redis_ok = queue_client.health_check()
    comfyui_ok = None

    if settings.engine_mode == "comfyui":
        comfyui_ok = ComfyUIEngine(settings=settings).health_check()

    status = "ok" if redis_ok and (comfyui_ok in {None, True}) else "degraded"
    return {
        "status": status,
        "app_version": settings.app_version,
        "environment": settings.app_env,
        "engine_mode": settings.engine_mode,
        "redis_ok": redis_ok,
        "comfyui_ok": comfyui_ok,
    }
