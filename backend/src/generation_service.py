from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

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


def normalize_history_jobs(project_root: Path, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog = _get_catalog(project_root)
    normalized_jobs: list[dict[str, Any]] = []
    for job in jobs:
        item = dict(job)
        workflow_name = item.get("workflow")
        if workflow_name:
            try:
                item["workflow"] = catalog.resolve(str(workflow_name)).workflow_id
            except KeyError:
                item["workflow"] = str(workflow_name)

        output_path = item.get("output_path")
        if output_path:
            formatted_paths: list[str] = []
            for raw_path in str(output_path).split(","):
                candidate = raw_path.strip()
                if not candidate:
                    continue
                formatted_paths.append(f"/outputs/{Path(candidate).name}")
            item["output_path"] = ",".join(formatted_paths)

        normalized_jobs.append(item)
    return normalized_jobs
