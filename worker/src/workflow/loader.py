"""Workflow JSON loading and path resolution helpers."""

import json
from pathlib import Path

try:
    from ..config import WORKFLOW_CONFIG_PATH, WORKFLOW_DIR
except ImportError:
    from config import WORKFLOW_CONFIG_PATH, WORKFLOW_DIR

from shared.workflow_catalog import WorkflowCatalog


API_WORKFLOW_FALLBACK_DIRS = (
    WORKFLOW_DIR.parent / "ComfyUIworkflow_api",
    Path("/ComfyUIworkflow_api"),
)


def _is_ui_workflow_data(workflow_data) -> bool:
    return isinstance(workflow_data, dict) and isinstance(workflow_data.get("nodes"), list)


def _load_json_file(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_workflow_path(workflow_name: str) -> Path:
    catalog = WorkflowCatalog.from_paths(WORKFLOW_CONFIG_PATH, WORKFLOW_DIR)
    resolution = catalog.resolve(workflow_name)
    print(f"[Parser] config.json workflow file: {resolution.entry.file}")
    return resolution.entry.path


def load_workflow(workflow_name: str) -> dict:
    workflow_path = get_workflow_path(workflow_name)

    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    workflow_data = _load_json_file(workflow_path)

    if _is_ui_workflow_data(workflow_data):
        fallback_path = next(
            (candidate / workflow_path.name for candidate in API_WORKFLOW_FALLBACK_DIRS if (candidate / workflow_path.name).exists()),
            None,
        )
        if fallback_path is None:
            raise ValueError(
                f"Workflow {workflow_path.name} is UI format and API fallback is missing"
            )
        print(f"[Parser] UI workflow detected; using API fallback: {fallback_path}")
        workflow_data = _load_json_file(fallback_path)

    if _is_ui_workflow_data(workflow_data):
        raise ValueError(f"Workflow {workflow_path.name} API fallback is UI format")

    if not isinstance(workflow_data, dict):
        raise TypeError(f"Workflow data must be dict, got {type(workflow_data).__name__}")

    return workflow_data
