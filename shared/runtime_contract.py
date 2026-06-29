from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from shared import env_resolution
from shared.workflow_catalog import WorkflowCatalog


def _get_env(env: Mapping[str, str], name: str, default: str = "") -> str:
    return env_resolution.read_env_str(name, default, env=env)


@dataclass(frozen=True)
class ServiceBindingSnapshot:
    configured_host: str
    resolved_host: str
    port: int
    alias_applied: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "configured_host": self.configured_host,
            "resolved_host": self.resolved_host,
            "port": self.port,
            "alias_applied": self.alias_applied,
        }


@dataclass(frozen=True)
class ComfyUIBindingSnapshot:
    url: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "status": self.status,
        }


@dataclass(frozen=True)
class RuntimeContract:
    runtime_profile: str
    deployment_topology: str
    api_origin: str
    redis: ServiceBindingSnapshot
    database: ServiceBindingSnapshot
    workflow_dir: Path
    workflow_config_path: Path
    workflow_config_exists: bool
    config_valid: bool
    validation_code: str
    secrets_ok: bool
    missing_secrets: tuple[str, ...]
    comfyui: ComfyUIBindingSnapshot

    def to_public_dict(self) -> dict[str, object]:
        return {
            "runtime_profile": self.runtime_profile,
            "deployment_topology": self.deployment_topology,
            "api_origin": self.api_origin,
            "workflow_dir": self.workflow_dir.as_posix(),
            "workflow_config_path": self.workflow_config_path.as_posix(),
            "workflow_config_exists": self.workflow_config_exists,
            "config_valid": self.config_valid,
            "validation_code": self.validation_code,
            "secrets_ok": self.secrets_ok,
            "missing_secrets": list(self.missing_secrets),
            "redis": self.redis.to_dict(),
            "database": self.database.to_dict(),
            "comfyui": self.comfyui.to_dict(),
        }


class RuntimeContractLoader:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        project_root: Path | None = None,
        platform_name: str | None = None,
    ):
        self.env = dict(env or os.environ)
        self.project_root = Path(project_root or Path(__file__).resolve().parents[1])
        self.platform_name = (platform_name or os.name).strip()

    def load(self) -> RuntimeContract:
        deployment_topology = _get_env(self.env, "DEPLOYMENT_TOPOLOGY", "local-dev") or "local-dev"
        runtime_profile = _get_env(self.env, "COMFYUI_RUNTIME_PROFILE", "")
        if not runtime_profile:
            runtime_profile = "windows" if self.platform_name.lower().startswith("win") else "linux"

        workflow_dir = self._resolve_path("WORKFLOW_DIR", self.project_root / "ComfyUIworkflow")
        workflow_config_path = workflow_dir / "config.json"
        workflow_config_exists = workflow_config_path.exists()
        config_valid = False
        if workflow_config_exists:
            try:
                catalog = WorkflowCatalog.from_paths(workflow_config_path, workflow_dir)
                config_valid = catalog.validate() == []
            except Exception:
                config_valid = False

        redis = self._resolve_service(
            host_name="REDIS_HOST",
            port_name="REDIS_PORT",
            default_host="localhost",
            default_port=6379,
            alias_names={"redis", "studio-redis"},
        )
        database = self._resolve_service(
            host_name="DB_HOST",
            port_name="DB_PORT",
            default_host="localhost",
            default_port=3306,
            alias_names={"mysql", "studio-mysql"},
        )
        api_origin = self._resolve_api_origin(deployment_topology)
        missing_secrets = self._missing_secrets(deployment_topology)
        secrets_ok = len(missing_secrets) == 0
        validation_code = "ready"
        if not secrets_ok:
            validation_code = "blocked"
        elif not config_valid:
            validation_code = "degraded"

        comfyui = self._resolve_comfyui_binding()

        return RuntimeContract(
            runtime_profile=runtime_profile,
            deployment_topology=deployment_topology,
            api_origin=api_origin,
            redis=redis,
            database=database,
            workflow_dir=workflow_dir,
            workflow_config_path=workflow_config_path,
            workflow_config_exists=workflow_config_exists,
            config_valid=config_valid,
            validation_code=validation_code,
            secrets_ok=secrets_ok,
            missing_secrets=missing_secrets,
            comfyui=comfyui,
        )

    def _resolve_path(self, env_name: str, default_path: Path) -> Path:
        raw_value = _get_env(self.env, env_name, "")
        if not raw_value:
            return default_path.resolve()
        path = Path(os.path.expandvars(os.path.expanduser(raw_value)))
        if path.is_absolute():
            return path.resolve()
        return (self.project_root / path).resolve()

    def _resolve_service(
        self,
        *,
        host_name: str,
        port_name: str,
        default_host: str,
        default_port: int,
        alias_names: set[str],
    ) -> ServiceBindingSnapshot:
        configured_host = _get_env(self.env, host_name, default_host) or default_host
        port = int(_get_env(self.env, port_name, str(default_port)) or str(default_port))
        resolution = env_resolution.resolve_service_host(
            configured_host,
            port,
            platform_name=self.platform_name,
            aliases=alias_names,
        )
        return ServiceBindingSnapshot(
            configured_host=resolution.configured_host,
            resolved_host=resolution.resolved_host,
            port=resolution.port,
            alias_applied=resolution.alias_applied,
        )

    def _resolve_api_origin(self, deployment_topology: str) -> str:
        configured_origin = _get_env(self.env, "PUBLIC_API_ORIGIN", "") or _get_env(self.env, "API_ORIGIN", "")
        if configured_origin:
            return configured_origin

        lb_domain = _get_env(self.env, "LB_DOMAIN", "")
        if deployment_topology.startswith("twcc") and lb_domain:
            return f"https://{lb_domain}"
        return "http://localhost:5000"

    def _missing_secrets(self, deployment_topology: str) -> tuple[str, ...]:
        required = ["DB_PASSWORD"]
        if deployment_topology.startswith("twcc"):
            required.extend(["TWCC_API_KEY", "TWCC_PROJECT_ID", "TWCC_GPU_VM_ID"])

        missing = [name for name in required if not _get_env(self.env, name, "")]
        return tuple(missing)

    def _resolve_comfyui_binding(self) -> ComfyUIBindingSnapshot:
        raw_url = _get_env(self.env, "COMFYUI_SERVER_URL", "")
        normalized = f"http://{raw_url}" if raw_url and "://" not in raw_url else raw_url
        parsed = env_resolution.parse_endpoint_url(
            raw_url, default_scheme="http", default_host="localhost", default_port=8188
        )
        if parsed is not None:
            return ComfyUIBindingSnapshot(url=normalized.rstrip("/"), status="healthy")

        host = _get_env(self.env, "COMFYUI_HOST", "localhost") or "localhost"
        port = _get_env(self.env, "COMFYUI_PORT", "8188") or "8188"
        return ComfyUIBindingSnapshot(url=f"http://{host}:{port}", status="healthy")
