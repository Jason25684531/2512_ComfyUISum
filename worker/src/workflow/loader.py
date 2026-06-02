"""Workflow JSON loading and path resolution helpers."""

import json
from pathlib import Path

try:
    from ..workflow_registry import WorkflowRegistry
    from .legacy_maps import WORKFLOW_MAP
except ImportError:
    from workflow_registry import WorkflowRegistry
    from workflow.legacy_maps import WORKFLOW_MAP


PROJECT_ROOT = Path(__file__).resolve().parents[3]
API_WORKFLOW_FALLBACK_DIR = PROJECT_ROOT / "ComfyUIworkflow_api"


def _is_ui_workflow_data(workflow_data) -> bool:
    return isinstance(workflow_data, dict) and isinstance(workflow_data.get("nodes"), list)


def _load_json_file(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_workflow_path(workflow_name: str) -> Path:
    workflow_dir = WorkflowRegistry().workflow_dir

    try:
        entry = WorkflowRegistry(workflow_dir=workflow_dir).get(workflow_name)
        if entry.file and entry.path.exists():
            print(f"[Parser] config.json workflow file: {entry.file}")
            return entry.path
    except Exception as e:
        print(f"[Parser] Warning: failed to read config.json: {e}")

    filename = WORKFLOW_MAP.get(workflow_name, f"{workflow_name}.json")
    return workflow_dir / filename


def load_workflow(workflow_name: str) -> dict:
    workflow_path = get_workflow_path(workflow_name)

    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    workflow_data = _load_json_file(workflow_path)

    if _is_ui_workflow_data(workflow_data):
        fallback_path = API_WORKFLOW_FALLBACK_DIR / workflow_path.name
        if fallback_path.exists():
            print(f"[Parser] UI workflow detected; using API fallback: {fallback_path.name}")
            workflow_data = _load_json_file(fallback_path)
        else:
            raise ValueError(
                f"Workflow {workflow_path.name} is UI format and API fallback is missing: {fallback_path}"
            )

    if not isinstance(workflow_data, dict):
        raise TypeError(f"Workflow data must be dict, got {type(workflow_data).__name__}")

    return workflow_data
