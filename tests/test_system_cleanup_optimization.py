import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = PROJECT_ROOT / "worker" / "src"
MAINTENANCE_LIB_PATH = PROJECT_ROOT / "scripts" / "maintenance_lib.py"
FRONTEND_INDEX_PATH = PROJECT_ROOT / "frontend" / "index.html"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_collect_deprecated_assets_flags_legacy_targets(tmp_path):
    maintenance_module = load_module("maintenance_lib_test_assets", MAINTENANCE_LIB_PATH)

    (tmp_path / "openspec" / "specs").mkdir(parents=True)
    (tmp_path / "k8s").mkdir(parents=True)
    (tmp_path / ".env.example.backup").write_text("legacy\n", encoding="utf-8")
    (tmp_path / "openspec" / "specs" / "project.md").write_text("legacy\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "k8s" / "deployment.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: studio\n",
        encoding="utf-8",
    )

    deprecated_assets = maintenance_module.collect_deprecated_assets(tmp_path)

    assert ".env.example.backup" in deprecated_assets
    assert "openspec/specs/project.md" in deprecated_assets
    assert any(asset.startswith("k8s") for asset in deprecated_assets)
    assert "docker-compose.yml" not in deprecated_assets


def test_detect_environment_rejects_ambiguous_contracts(tmp_path):
    maintenance_module = load_module("maintenance_lib_test_detect", MAINTENANCE_LIB_PATH)

    (tmp_path / ".env.local").write_text("STUDIO_ENV=local\n", encoding="utf-8")
    (tmp_path / ".env.twcc").write_text("STUDIO_ENV=twcc\n", encoding="utf-8")

    with pytest.raises(maintenance_module.MaintenanceError, match="Ambiguous environment selection"):
        maintenance_module.detect_environment(tmp_path, environ={})


def test_collect_local_cleanup_targets_skips_canonical_assets(tmp_path):
    maintenance_module = load_module("maintenance_lib_test_local_cleanup", MAINTENANCE_LIB_PATH)

    (tmp_path / ".env.local").write_text("STUDIO_ENV=local\n", encoding="utf-8")
    (tmp_path / "ComfyUIworkflow").mkdir(parents=True)
    (tmp_path / "ComfyUIworkflow" / "workflow.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "storage" / "outputs").mkdir(parents=True)
    (tmp_path / "storage" / "outputs" / "result.png").write_bytes(b"png")
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "backend" / "__pycache__").mkdir(parents=True)
    (tmp_path / "backend" / "__pycache__" / "config.cpython-311.pyc").write_bytes(b"cache")

    cleanup_targets = maintenance_module.collect_local_cleanup_targets(tmp_path)

    assert ".pytest_cache" in cleanup_targets
    assert "backend/__pycache__" in cleanup_targets
    assert ".env.local" not in cleanup_targets
    assert not any(target.startswith("ComfyUIworkflow") for target in cleanup_targets)
    assert not any(target.startswith("storage") for target in cleanup_targets)
    assert not any(target.endswith(".pyc") for target in cleanup_targets)


def test_build_twcc_actions_stays_non_destructive(tmp_path):
    maintenance_module = load_module("maintenance_lib_test_twcc", MAINTENANCE_LIB_PATH)

    (tmp_path / "frontend").mkdir(parents=True)
    twcc_actions = maintenance_module.build_twcc_actions(tmp_path, use_sudo=True)

    assert twcc_actions[0][:3] == ["sudo", "chmod", "755"]
    assert twcc_actions[1] == ["docker", "image", "prune", "-f"]
    assert all("system" not in action for command in twcc_actions for action in command)
    assert all("volume" not in action for command in twcc_actions for action in command)


def test_worker_config_keeps_normalized_comfy_urls(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    monkeypatch.setenv("COMFYUI_SERVER_URL", "https://example.com:9443/comfy")

    worker_config = load_module("worker_config_shared_refactor", WORKER_SRC / "config.py")

    assert worker_config.COMFY_HOST == "example.com"
    assert worker_config.COMFY_PORT == 9443
    assert worker_config.COMFYUI_SERVER_URL == "https://example.com:9443/comfy"
    assert worker_config.COMFY_WS_URL == "wss://example.com:9443/comfy/ws"


def test_frontend_index_uses_same_origin_api_base():
    content = FRONTEND_INDEX_PATH.read_text(encoding="utf-8")

    assert "function resolveApiBase()" in content
    assert "const API_BASE = window.API_BASE;" in content
    assert "window.API_URL || ''" not in content
