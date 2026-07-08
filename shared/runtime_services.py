from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.runtime_contract import RuntimeContractLoader
from shared.workflow_catalog import WorkflowCatalog, WorkflowResolution


def _get_catalog(project_root: Path) -> WorkflowCatalog:
    workflow_dir = project_root / "ComfyUIworkflow"
    return WorkflowCatalog.from_paths(workflow_dir / "config.json", workflow_dir)


def resolve_workflow_request(project_root: Path, workflow_name: str | None) -> WorkflowResolution:
    catalog = _get_catalog(project_root)
    return catalog.resolve(workflow_name or "text_to_image")


def build_job_data(
    *,
    project_root: Path,
    data: dict[str, Any],
    job_id: str,
    user_id: int | None,
    user_label: str,
    created_at: datetime,
) -> tuple[WorkflowResolution, dict[str, Any]]:
    resolution = resolve_workflow_request(project_root, data.get("workflow"))
    job_data = {
        "job_id": job_id,
        "prompt": data.get("prompt", ""),
        "prompts": data.get("prompts", []),
        "seed": data.get("seed", -1),
        "workflow": resolution.workflow_id,
        "workflow_requested": resolution.requested_id,
        "workflow_resolution": resolution.source,
        "user_id": user_id,
        "user_label": user_label,
        "model": data.get("model", "turbo_fp8"),
        "aspect_ratio": data.get("aspect_ratio", "1:1"),
        "batch_size": data.get("batch_size", 1),
        "images": data.get("images", {}),
        "audio": data.get("audio", ""),
        "video": data.get("video", ""),
        "retake_start": data.get("retake_start", 0),
        "retake_end": data.get("retake_end", 0),
        "created_at": created_at.isoformat(),
    }
    return resolution, job_data


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


__all__ = [
    "build_job_data",
    "build_runtime_config_payload",
    "build_runtime_diagnostics",
    "resolve_workflow_request",
]
