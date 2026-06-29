from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from shared.runtime_contract import RuntimeContractLoader
from shared.workflow_catalog import WorkflowCatalog


def build_runtime_contract(project_root: Path) -> dict[str, Any]:
    contract = RuntimeContractLoader(project_root=project_root).load()
    return contract.to_public_dict()


def build_runtime_diagnostics(
    *,
    project_root: Path,
    redis_status: str,
    mysql_status: str,
    worker_status: str,
) -> dict[str, Any]:
    contract = RuntimeContractLoader(project_root=project_root).load()
    comfyui_status = contract.comfyui.status
    validation_status = contract.validation_code

    if redis_status != "healthy" or mysql_status not in {"healthy", "n/a"}:
        validation_status = "degraded"
    elif worker_status != "online" and contract.deployment_topology.startswith("twcc"):
        validation_status = "degraded"

    gpu_dependency = "external" if contract.deployment_topology.startswith("twcc") else "local"
    proxy_fix_enabled = os.environ.get("PROXY_FIX", "false").lower() == "true"

    return {
        "deployment_topology": contract.deployment_topology,
        "validation_status": validation_status,
        "proxy_fix_enabled": proxy_fix_enabled,
        "gpu_dependency": gpu_dependency,
        "runtime_profile": contract.runtime_profile,
        "config_valid": contract.config_valid,
        "workflow_config_exists": contract.workflow_config_exists,
        "workflow_dir": contract.workflow_dir.as_posix(),
        "comfyui": {
            "status": comfyui_status,
            "url": contract.comfyui.url,
        },
    }


def build_runtime_config_payload(project_root: Path) -> dict[str, Any]:
    contract = RuntimeContractLoader(project_root=project_root).load()
    workflow_dir = project_root / "ComfyUIworkflow"
    catalog = WorkflowCatalog.from_paths(workflow_dir / "config.json", workflow_dir)
    return {
        "runtime_profile": contract.runtime_profile,
        "deployment_topology": contract.deployment_topology,
        "api_origin": contract.api_origin,
        "workflow_catalog": catalog.frontend_catalog(),
    }
