from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.routes.assets import router as assets_router
from app.routes.health import router as health_router
from app.routes.jobs import router as jobs_router
from app.routes.workflows import router as workflows_router
from app.services.path_validator import InvalidStoragePathError, ensure_storage_layout
from app.services.redis_client import RedisQueueClient
from shared.v2 import AssetStore, JobStore
from workflow_registry.registry import WorkflowRegistry


LOGGER = logging.getLogger(__name__)


def _default_registry() -> WorkflowRegistry:
    from pathlib import Path

    manifests_dir = Path(__file__).resolve().parents[3] / "packages" / "workflow_registry" / "manifests"
    return WorkflowRegistry.from_directory(manifests_dir)


def create_app(
    *,
    settings: Settings | None = None,
    queue_client: RedisQueueClient | None = None,
    workflow_registry: WorkflowRegistry | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    runtime_queue = queue_client or RedisQueueClient(
        redis_url=runtime_settings.redis_url,
        queue_key=runtime_settings.queue_key,
    )
    runtime_registry = workflow_registry or _default_registry()
    store = JobStore(runtime_settings.database_url)
    asset_store = AssetStore(runtime_settings.database_url)
    ensure_storage_layout(
        runtime_settings.storage_root,
        asset_root=runtime_settings.asset_root,
        output_root=runtime_settings.output_root,
    )
    store.initialize()
    asset_store.initialize()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        LOGGER.info(
            "Starting Studio Core v2 app",
            extra={
                "app_env": runtime_settings.app_env,
                "engine_mode": runtime_settings.engine_mode,
            },
        )
        yield
        shutdown = getattr(runtime_queue, "shutdown", None)
        if callable(shutdown):
            shutdown()

    app = FastAPI(title="Studio Core v2", version=runtime_settings.app_version, lifespan=lifespan)
    app.state.settings = runtime_settings
    app.state.queue_client = runtime_queue
    app.state.workflow_registry = runtime_registry
    app.state.job_store = store
    app.state.asset_store = asset_store

    api_router_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_router_prefix)
    app.include_router(assets_router, prefix=api_router_prefix)
    app.include_router(workflows_router, prefix=api_router_prefix)
    app.include_router(jobs_router, prefix=api_router_prefix)
    
    from app.routes.outputs import router as outputs_router
    app.include_router(outputs_router, prefix=api_router_prefix)

    from app.routes.legacy_bridge import router as legacy_bridge_router
    app.include_router(legacy_bridge_router, prefix="/api")

    from app.config import REPO_ROOT
    frontend_dir = REPO_ROOT / "frontend"

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/dashboard", include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(frontend_dir / "dashboard.html")

    @app.get("/dashboard.html", include_in_schema=False)
    async def serve_dashboard_legacy():
        return FileResponse(frontend_dir / "dashboard.html")

    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

    @app.exception_handler(InvalidStoragePathError)
    async def handle_invalid_storage_path(_: Request, __: InvalidStoragePathError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": "Invalid storage path."})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Don't mask custom 404 details with a generic "Route was not found."
        # If the detail is the default "Not Found", then we can override it.
        detail = "Route was not found." if exc.status_code == 404 and exc.detail == "Not Found" else exc.detail
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    return app


app = create_app()
