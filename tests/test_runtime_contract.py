import importlib
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reload_runtime_contract():
    module_name = "shared.runtime_contract"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def test_runtime_contract_resolves_windows_service_aliases(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    monkeypatch.setenv("DEPLOYMENT_TOPOLOGY", "local-dev")
    monkeypatch.setenv("REDIS_HOST", "studio-redis")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("DB_HOST", "studio-mysql")
    monkeypatch.setenv("DB_PORT", "3306")

    runtime_contract = _reload_runtime_contract()
    loader = runtime_contract.RuntimeContractLoader(
        env=os.environ.copy(),
        project_root=PROJECT_ROOT,
        platform_name="Windows",
    )

    contract = loader.load()

    assert contract.runtime_profile == "windows"
    assert contract.redis.configured_host == "studio-redis"
    assert contract.redis.resolved_host == "127.0.0.1"
    assert contract.redis.alias_applied is True
    assert contract.database.configured_host == "studio-mysql"
    assert contract.database.resolved_host == "127.0.0.1"
    assert contract.workflow_config_exists is True
    assert contract.config_valid is True


def test_runtime_contract_preserves_container_hosts_for_linux(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    monkeypatch.setenv("DEPLOYMENT_TOPOLOGY", "twcc-base-vm")
    monkeypatch.setenv("REDIS_HOST", "studio-redis")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("DB_HOST", "studio-mysql")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("PUBLIC_API_ORIGIN", "https://studio.example.com")

    runtime_contract = _reload_runtime_contract()
    loader = runtime_contract.RuntimeContractLoader(
        env=os.environ.copy(),
        project_root=PROJECT_ROOT,
        platform_name="Linux",
    )

    contract = loader.load()

    assert contract.runtime_profile == "linux"
    assert contract.api_origin == "https://studio.example.com"
    assert contract.redis.resolved_host == "studio-redis"
    assert contract.redis.alias_applied is False
    assert contract.database.resolved_host == "studio-mysql"
    assert contract.validation_code == "ready"


def test_runtime_contract_fails_closed_when_twcc_secrets_are_missing(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    monkeypatch.setenv("DEPLOYMENT_TOPOLOGY", "twcc-base-vm")
    monkeypatch.setenv("COMFYUI_SERVER_URL", "http://gpu-vm.internal:8188")
    monkeypatch.delenv("TWCC_API_KEY", raising=False)
    monkeypatch.delenv("TWCC_PROJECT_ID", raising=False)
    monkeypatch.delenv("TWCC_GPU_VM_ID", raising=False)

    runtime_contract = _reload_runtime_contract()
    loader = runtime_contract.RuntimeContractLoader(
        env=os.environ.copy(),
        project_root=PROJECT_ROOT,
        platform_name="Linux",
    )

    contract = loader.load()

    assert contract.validation_code == "blocked"
    assert contract.secrets_ok is False
    assert set(contract.missing_secrets) >= {
        "TWCC_API_KEY",
        "TWCC_PROJECT_ID",
        "TWCC_GPU_VM_ID",
    }

