from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "apps" / "backend-fastapi"
WORKER_ROOT = REPO_ROOT / "apps" / "worker-v2"
WORKFLOW_REGISTRY_ROOT = REPO_ROOT / "packages" / "workflow_registry"

for entry in (REPO_ROOT, BACKEND_ROOT, WORKER_ROOT, WORKFLOW_REGISTRY_ROOT):
    path_str = str(entry)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


class FakeQueueClient:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.payloads: list[str] = []
        self.cancel_requests: list[str] = []

    def health_check(self) -> bool:
        return self.available

    def enqueue_job(self, payload: str) -> None:
        if not self.available:
            from app.services.redis_client import QueueUnavailableError

            raise QueueUnavailableError("queue unavailable")
        json.loads(payload)
        self.payloads.append(payload)

    def request_cancel(self, job_id: str) -> None:
        if not self.available:
            from app.services.redis_client import QueueUnavailableError

            raise QueueUnavailableError("queue unavailable")
        self.cancel_requests.append(job_id)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENGINE_MODE", "mock")
    monkeypatch.setenv("COMFYUI_BASE_URL", "http://comfyui.internal:8188")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("STORAGE_ROOT", "./storage")
    monkeypatch.setenv("ASSET_ROOT", "assets")
    monkeypatch.setenv("OUTPUT_ROOT", "outputs")
    monkeypatch.setenv("ALLOW_EXTERNAL_API", "false")
    monkeypatch.setenv("DEFAULT_TIER", "draft")
    return Settings(
        app_env="test",
        engine_mode="mock",
        comfyui_base_url="http://comfyui.internal:8188",
        database_url=f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}",
        redis_url="redis://localhost:6379/0",
        storage_root="./storage",
        asset_root="assets",
        output_root="outputs",
        allow_external_api=False,
        default_tier="draft",
    )


@pytest.fixture
def fake_queue():
    return FakeQueueClient()


@pytest.fixture
def app(settings, fake_queue):
    from app.main import create_app
    from workflow_registry.registry import WorkflowRegistry

    registry = WorkflowRegistry.from_directory(WORKFLOW_REGISTRY_ROOT / "manifests")
    return create_app(settings=settings, queue_client=fake_queue, workflow_registry=registry)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)

@pytest.fixture
def client_with_broken_queue(settings):
    from app.main import create_app
    from workflow_registry.registry import WorkflowRegistry
    from fastapi.testclient import TestClient

    registry = WorkflowRegistry.from_directory(WORKFLOW_REGISTRY_ROOT / "manifests")
    broken_queue = FakeQueueClient(available=False)
    broken_app = create_app(settings=settings, queue_client=broken_queue, workflow_registry=registry)
    return TestClient(broken_app)
