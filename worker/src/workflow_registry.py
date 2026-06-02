import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LEGACY_ALIASES = {
    "multi_blend": "multi_image_blend",
    "single_image_edit": "image_edit",
}

_CONFIG_MODULE = sys.modules.get("config")
_CACHED_DEFAULT_PATHS = None
if _CONFIG_MODULE is not None and hasattr(_CONFIG_MODULE, "WORKFLOW_CONFIG_PATH") and hasattr(_CONFIG_MODULE, "WORKFLOW_DIR"):
    _CACHED_DEFAULT_PATHS = (
        Path(_CONFIG_MODULE.WORKFLOW_CONFIG_PATH),
        Path(_CONFIG_MODULE.WORKFLOW_DIR),
    )


def _default_workflow_paths() -> tuple[Path, Path]:
    if _CACHED_DEFAULT_PATHS is not None:
        return _CACHED_DEFAULT_PATHS

    try:
        from .config import WORKFLOW_CONFIG_PATH, WORKFLOW_DIR
    except ImportError:
        from config import WORKFLOW_CONFIG_PATH, WORKFLOW_DIR

    return Path(WORKFLOW_CONFIG_PATH), Path(WORKFLOW_DIR)


@dataclass(frozen=True)
class WorkflowEntry:
    name: str
    file: str
    path: Path
    mapping: dict[str, Any]
    prompt_map: dict[str, Any]
    image_map: dict[str, Any]
    audio_map: dict[str, Any]
    model_overrides: dict[str, Any]


class WorkflowRegistry:
    def __init__(self, config_path: Path = None, workflow_dir: Path = None):
        default_config_path, default_workflow_dir = _default_workflow_paths()
        self.config_path = Path(config_path) if config_path is not None else default_config_path
        self.workflow_dir = Path(workflow_dir) if workflow_dir is not None else default_workflow_dir
        self._config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def resolve_name(self, workflow_name: str) -> str:
        if workflow_name in self._config:
            return workflow_name
        alias = LEGACY_ALIASES.get(workflow_name)
        if alias in self._config:
            return alias
        return workflow_name

    def get(self, workflow_name: str) -> WorkflowEntry:
        resolved_name = self.resolve_name(workflow_name)
        config = self._config.get(resolved_name, {})
        filename = config.get("file", f"{workflow_name}.json")
        mapping = config.get("mapping", {})
        audio_map = config.get("audio_map", {})
        if not audio_map and mapping.get("audio_node_id"):
            audio_map = {
                "audio": {
                    "node_id": mapping["audio_node_id"],
                    "input_key": "audio",
                }
            }

        return WorkflowEntry(
            name=resolved_name,
            file=filename,
            path=self.workflow_dir / filename,
            mapping=mapping,
            prompt_map=config.get("prompt_map", {}),
            image_map=config.get("image_map", {}),
            audio_map=audio_map,
            model_overrides=config.get("model_overrides", {}),
        )

    def resolve_runtime_profile(self) -> str:
        configured_profile = os.getenv("COMFYUI_RUNTIME_PROFILE", "").strip()
        if configured_profile:
            return configured_profile.lower()

        system_name = platform.system().strip().lower()
        if system_name.startswith("win"):
            return "windows"
        return "linux"

    def get_model_overrides(self, workflow_name: str) -> tuple[str, list[dict[str, Any]]]:
        entry = self.get(workflow_name)
        profile = self.resolve_runtime_profile()
        profile_overrides = entry.model_overrides.get(profile, [])
        if not isinstance(profile_overrides, list):
            return profile, []
        return profile, [item for item in profile_overrides if isinstance(item, dict)]

    def iter_entries(self):
        for workflow_name in self._config:
            yield self.get(workflow_name)

    def validate_configured_workflows(self) -> list[str]:
        errors: list[str] = []
        for entry in self.iter_entries():
            workflow = self._load_runtime_workflow(entry)
            if workflow is None:
                errors.append(f"{entry.name}: workflow file is missing or invalid: {entry.file}")
                continue

            for field_name, target in entry.prompt_map.items():
                node_id = target.get("node_id")
                input_key = target.get("input_key", "prompt")
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.name}: prompt_map.{field_name} missing node {node_id}")
                elif not can_inject_prompt(node, input_key):
                    errors.append(f"{entry.name}: prompt_map.{field_name} cannot inject {node_id}.{input_key}")

            for field_name, node_id in entry.image_map.items():
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.name}: image_map.{field_name} missing node {node_id}")
                elif not has_input_key(node, "image"):
                    errors.append(f"{entry.name}: image_map.{field_name} cannot inject {node_id}.image")

            for field_name, target in entry.audio_map.items():
                node_id = target.get("node_id")
                input_key = target.get("input_key", "audio")
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.name}: audio_map.{field_name} missing node {node_id}")
                elif not has_input_key(node, input_key):
                    errors.append(f"{entry.name}: audio_map.{field_name} cannot inject {node_id}.{input_key}")

        return errors

    def _load_runtime_workflow(self, entry: WorkflowEntry) -> dict[str, Any] | None:
        try:
            data = json.loads(entry.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("nodes"), list):
                fallback_path = self.workflow_dir.parent / "ComfyUIworkflow_api" / entry.file
                if fallback_path.exists():
                    data = json.loads(fallback_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None


def find_workflow_node(workflow: dict[str, Any], node_id: Any):
    node_key = str(node_id)
    node = workflow.get(node_key)
    if isinstance(node, dict):
        return node

    nodes = workflow.get("nodes")
    if isinstance(nodes, list):
        for item in nodes:
            if isinstance(item, dict) and str(item.get("id")) == node_key:
                return item
    return None


def has_input_key(node: dict[str, Any], input_key: str) -> bool:
    inputs = node.get("inputs")
    if isinstance(inputs, dict):
        return input_key in inputs
    if isinstance(inputs, list):
        return any(isinstance(item, dict) and item.get("name") == input_key for item in inputs)
    return False


def can_inject_prompt(node: dict[str, Any], input_key: str) -> bool:
    if has_input_key(node, input_key):
        return True
    widgets_values = node.get("widgets_values")
    if isinstance(widgets_values, list):
        return len(widgets_values) > 0
    if isinstance(widgets_values, dict):
        return any(key in widgets_values for key in (input_key, "prompt", "text", "string"))
    return False
