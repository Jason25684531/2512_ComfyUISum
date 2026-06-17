from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
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
FRONTEND_PAGE_ALIASES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/dashboard": "dashboard.html",
    "/dashboard.html": "dashboard.html",
    "/login": "login.html",
    "/login.html": "login.html",
    "/profile": "profile.html",
    "/profile.html": "profile.html",
}
FRONTEND_FILE_ALIASES = {
    "/config.js": "config.js",
    "/motion-workspace.js": "motion-workspace.js",
    "/image-utils.js": "image-utils.js",
    "/build-icons.js": "build-icons.js",
    "/tailwind.generated.css": "tailwind.generated.css",
    "/style.css": "style.css",
}
FRONTEND_MOUNTS = {
    "/frontend": ".",
    "/image": "image",
    "/vendor": "vendor",
    "/front": "front",
}


def _default_registry() -> WorkflowRegistry:
    manifests_dir = Path(__file__).resolve().parents[3] / "packages" / "workflow_registry" / "manifests"
    return WorkflowRegistry.from_directory(manifests_dir)


def _build_frontend_handler(frontend_dir: Path, relative_path: str):
    async def serve_frontend_file():
        target = frontend_dir / relative_path
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Frontend asset not found.")
        return FileResponse(target)

    return serve_frontend_file


def _register_frontend_routes(app: FastAPI, frontend_dir: Path) -> None:
    for route_path, relative_path in FRONTEND_PAGE_ALIASES.items():
        route_name = route_path.strip("/").replace("/", "-") or "root"
        app.add_api_route(
            route_path,
            _build_frontend_handler(frontend_dir, relative_path),
            methods=["GET"],
            include_in_schema=False,
            name=f"frontend-page-{route_name}",
        )

    for route_path, relative_path in FRONTEND_FILE_ALIASES.items():
        route_name = route_path.strip("/").replace("/", "-") or relative_path.replace("/", "-")
        app.add_api_route(
            route_path,
            _build_frontend_handler(frontend_dir, relative_path),
            methods=["GET"],
            include_in_schema=False,
            name=f"frontend-asset-{route_name}",
        )

    for mount_path, relative_path in FRONTEND_MOUNTS.items():
        directory = frontend_dir / relative_path
        if directory.is_dir():
            app.mount(mount_path, StaticFiles(directory=directory), name=mount_path.strip("/") or "frontend")


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

    _register_frontend_routes(app, frontend_dir)

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
