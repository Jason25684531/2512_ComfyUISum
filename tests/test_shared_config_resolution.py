"""Tests for the consolidated shared config resolution layer.

Covers specs/shared-config-resolution/spec.md:
- single env accessor (injected mapping, no secret logging)
- single Windows docker-alias host rule (+ MySQL port preservation in config_base)
- single ComfyUI URL parser
- backward-compatible config_base shell
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared import env_resolution as er  # noqa: E402


# --------------------------------------------------------------------------- #
# Env accessor
# --------------------------------------------------------------------------- #

def test_read_env_str_uses_injected_mapping_without_touching_os_environ():
    env = {"DB_HOST": "  db.internal  "}
    assert er.read_env_str("DB_HOST", env=env) == "db.internal"
    assert er.read_env_str("MISSING", "fallback", env=env) == "fallback"


def test_read_env_typed_helpers():
    env = {"P": "8188", "F": "1.5", "B": "TRUE", "EMPTY": "  "}
    assert er.read_env_int("P", 0, env=env) == 8188
    assert er.read_env_int("EMPTY", 7, env=env) == 7
    assert er.read_env_float("F", 0.0, env=env) == 1.5
    assert er.read_env_bool("B", env=env) is True
    assert er.read_env_bool("MISSING", True, env=env) is True


def test_env_accessor_never_logs_secret_values(caplog):
    secrets = {
        "DB_PASSWORD": "super-secret-db",
        "REDIS_PASSWORD": "super-secret-redis",
        "SECRET_KEY": "super-secret-key",
        "S3_SECRET_KEY": "super-secret-s3",
        "TWCC_API_KEY": "super-secret-twcc",
    }
    with caplog.at_level(logging.DEBUG):
        for name in secrets:
            er.read_env_str(name, env=secrets)
    for value in secrets.values():
        assert value not in caplog.text


# --------------------------------------------------------------------------- #
# Service host resolution (single rule)
# --------------------------------------------------------------------------- #

def test_windows_docker_alias_rewritten_to_loopback():
    result = er.resolve_service_host(
        "studio-redis", 6379, platform_name="Windows", aliases={"redis", "studio-redis"}
    )
    assert result.resolved_host == "127.0.0.1"
    assert result.alias_applied is True
    assert result.port == 6379


def test_linux_host_left_unchanged():
    result = er.resolve_service_host(
        "studio-mysql", 3306, platform_name="Linux", aliases={"mysql", "studio-mysql"}
    )
    assert result.resolved_host == "studio-mysql"
    assert result.alias_applied is False


def test_non_alias_host_on_windows_left_unchanged():
    result = er.resolve_service_host(
        "10.0.0.5", 6379, platform_name="Windows", aliases={"redis", "studio-redis"}
    )
    assert result.resolved_host == "10.0.0.5"
    assert result.alias_applied is False


# --------------------------------------------------------------------------- #
# ComfyUI / endpoint URL parsing (single parser)
# --------------------------------------------------------------------------- #

def test_parse_full_url():
    parsed = er.parse_endpoint_url(
        "https://gpu-node:8188/comfy", default_scheme="http", default_host="localhost", default_port=8188
    )
    assert parsed is not None
    assert (parsed.scheme, parsed.host, parsed.port, parsed.base_path) == ("https", "gpu-node", 8188, "/comfy")


def test_parse_bare_host_port_gets_default_scheme():
    parsed = er.parse_endpoint_url(
        "gpu-node:9000", default_scheme="http", default_host="localhost", default_port=8188
    )
    assert parsed is not None
    assert parsed.scheme == "http"
    assert parsed.host == "gpu-node"
    assert parsed.port == 9000


def test_parse_empty_returns_none():
    assert er.parse_endpoint_url("", default_scheme="http", default_host="localhost", default_port=8188) is None
    assert er.parse_endpoint_url("   ", default_scheme="http", default_host="localhost", default_port=8188) is None


# --------------------------------------------------------------------------- #
# Backward-compatible config_base shell + parity with runtime_contract
# --------------------------------------------------------------------------- #

def _reload(module_name: str):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def test_config_base_public_names_preserved(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    config_base = _reload("shared.config_base")
    # public names that existing call sites import
    for name in ("REDIS_HOST", "REDIS_PORT", "DB_HOST", "DB_PORT", "WORKFLOW_DIR"):
        assert hasattr(config_base, name)
    assert callable(config_base.get_env_str)
    assert callable(config_base.resolve_service_endpoint)
    assert callable(config_base.ServiceEndpoint)
    # ServiceEndpoint URL composition still works for worker ComfyUI config
    endpoint = config_base.resolve_service_endpoint(
        "COMFYUI_SERVER_URL", "COMFY_HOST", "COMFY_PORT", "127.0.0.1", 8188
    )
    assert endpoint.http_url.startswith("http")


def test_config_base_windows_mysql_port_bump_preserved(monkeypatch):
    """config_base keeps the Windows alias 3306 -> MYSQL_PORT/3307 behavior."""
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    config_base = _reload("shared.config_base")

    # Windows alias on default 3306 -> 127.0.0.1 + MYSQL_PORT/3307 bump
    host, port = config_base._resolve_db_endpoint_for(
        env={"DB_HOST": "studio-mysql", "DB_PORT": "3306"}, platform_name="Windows"
    )
    assert host == "127.0.0.1"
    assert port == 3307

    # Windows alias with explicit non-3306 port -> keep the explicit port
    host2, port2 = config_base._resolve_db_endpoint_for(
        env={"DB_HOST": "studio-mysql", "DB_PORT": "3310"}, platform_name="Windows"
    )
    assert host2 == "127.0.0.1"
    assert port2 == 3310

    # Linux -> no rewrite, no bump
    host3, port3 = config_base._resolve_db_endpoint_for(
        env={"DB_HOST": "studio-mysql", "DB_PORT": "3306"}, platform_name="Linux"
    )
    assert host3 == "studio-mysql"
    assert port3 == 3306


def test_runtime_contract_and_config_base_share_alias_rule(monkeypatch):
    """Both layers resolve the same Windows docker alias the same way."""
    monkeypatch.setenv("DB_PASSWORD", "test-password")
    monkeypatch.setenv("DEPLOYMENT_TOPOLOGY", "local-dev")
    monkeypatch.setenv("REDIS_HOST", "studio-redis")
    runtime_contract = _reload("shared.runtime_contract")
    loader = runtime_contract.RuntimeContractLoader(
        env={"DB_PASSWORD": "x", "DEPLOYMENT_TOPOLOGY": "local-dev", "REDIS_HOST": "studio-redis"},
        project_root=PROJECT_ROOT,
        platform_name="Windows",
    )
    contract = loader.load()
    assert contract.redis.resolved_host == "127.0.0.1"
    assert contract.redis.alias_applied is True
