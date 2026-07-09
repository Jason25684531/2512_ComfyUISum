from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _tuple_of_strings(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


@dataclass(frozen=True)
class WorkflowFrontendMetadata:
    title: str
    description: str
    icon: str
    color: str
    inputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "inputs": list(self.inputs),
        }


@dataclass(frozen=True)
class WorkflowCatalogEntry:
    workflow_id: str
    file: str
    path: Path
    category: str
    description: str
    aliases: tuple[str, ...]
    mapping: dict[str, Any]
    prompt_map: dict[str, Any]
    image_map: dict[str, Any]
    audio_map: dict[str, Any]
    model_overrides: dict[str, Any]
    frontend: WorkflowFrontendMetadata

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.workflow_id,
            "aliases": list(self.aliases),
            "category": self.category,
            "description": self.description,
            "file": self.file,
            "frontend": self.frontend.to_dict(),
        }


@dataclass(frozen=True)
class WorkflowResolution:
    requested_id: str
    workflow_id: str
    entry: WorkflowCatalogEntry
    source: str

    @property
    def alias_hit(self) -> bool:
        return self.source != "canonical"


class WorkflowCatalog:
    def __init__(self, config_path: Path, workflow_dir: Path, raw_config: dict[str, Any]):
        self.config_path = Path(config_path)
        self.workflow_dir = Path(workflow_dir)
        self._raw_config = raw_config
        self._entries = self._build_entries(raw_config)
        self._alias_index = self._build_alias_index(self._entries)
        self._alias_hits: dict[str, int] = {}

    @classmethod
    def from_paths(cls, config_path: Path, workflow_dir: Path) -> "WorkflowCatalog":
        config_path = Path(config_path)
        workflow_dir = Path(workflow_dir)
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        return cls(config_path=config_path, workflow_dir=workflow_dir, raw_config=raw_config)

    @property
    def entries(self) -> dict[str, WorkflowCatalogEntry]:
        return dict(self._entries)

    @property
    def raw_config(self) -> dict[str, Any]:
        """公開的原始 config.json 內容（唯讀用途）。

        提供給 worker 的 WorkflowRegistry 取代直接存取私有屬性 ``_raw_config``。
        """
        return self._raw_config

    def resolve(self, workflow_name: str | None) -> WorkflowResolution:
        requested_id = (workflow_name or "text_to_image").strip() or "text_to_image"
        if requested_id in self._entries:
            return WorkflowResolution(
                requested_id=requested_id,
                workflow_id=requested_id,
                entry=self._entries[requested_id],
                source="canonical",
            )

        canonical_id = self._alias_index.get(requested_id)
        if canonical_id and canonical_id in self._entries:
            self._alias_hits[requested_id] = self._alias_hits.get(requested_id, 0) + 1
            return WorkflowResolution(
                requested_id=requested_id,
                workflow_id=canonical_id,
                entry=self._entries[canonical_id],
                source="alias",
            )

        raise KeyError(f"Unknown workflow: {requested_id}")

    def get_alias_hit_counts(self) -> dict[str, int]:
        return dict(self._alias_hits)

    def frontend_catalog(self) -> list[dict[str, Any]]:
        return [entry.to_public_dict() for entry in self._entries.values()]

    def validate(self) -> list[str]:
        errors: list[str] = []
        for entry in self._entries.values():
            if not entry.path.exists():
                errors.append(f"{entry.workflow_id}: workflow file is missing: {entry.file}")
                continue

            try:
                workflow = json.loads(entry.path.read_text(encoding="utf-8"))
                if isinstance(workflow, dict) and isinstance(workflow.get("nodes"), list):
                    fallback_path = self.workflow_dir.parent / "ComfyUIworkflow_api" / entry.file
                    if fallback_path.exists():
                        workflow = json.loads(fallback_path.read_text(encoding="utf-8"))
                if not isinstance(workflow, dict):
                    errors.append(f"{entry.workflow_id}: workflow file is invalid: {entry.file}")
                    continue
            except Exception:
                errors.append(f"{entry.workflow_id}: workflow file is invalid: {entry.file}")
                continue

            for field_name, target in entry.prompt_map.items():
                node_id = target.get("node_id")
                input_key = target.get("input_key", "prompt")
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.workflow_id}: prompt_map.{field_name} missing node {node_id}")
                elif not can_inject_prompt(node, input_key):
                    errors.append(
                        f"{entry.workflow_id}: prompt_map.{field_name} cannot inject {node_id}.{input_key}"
                    )

            for field_name, node_id in entry.image_map.items():
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.workflow_id}: image_map.{field_name} missing node {node_id}")
                elif not has_input_key(node, "image"):
                    errors.append(f"{entry.workflow_id}: image_map.{field_name} cannot inject {node_id}.image")

            for field_name, target in entry.audio_map.items():
                node_id = target.get("node_id")
                input_key = target.get("input_key", "audio")
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.workflow_id}: audio_map.{field_name} missing node {node_id}")
                elif not has_input_key(node, input_key):
                    errors.append(
                        f"{entry.workflow_id}: audio_map.{field_name} cannot inject {node_id}.{input_key}"
                    )

            mapping = entry.mapping or {}

            output_node_id = mapping.get("output_node_id")
            if output_node_id and find_workflow_node(workflow, output_node_id) is None:
                errors.append(f"{entry.workflow_id}: mapping.output_node_id missing node {output_node_id}")

            for seed_node_id in mapping.get("seed_node_ids", []):
                node = find_workflow_node(workflow, seed_node_id)
                if node is None:
                    errors.append(f"{entry.workflow_id}: mapping.seed_node_ids missing node {seed_node_id}")
                elif not has_input_key(node, "noise_seed"):
                    errors.append(
                        f"{entry.workflow_id}: mapping.seed_node_ids cannot inject {seed_node_id}.noise_seed"
                    )

            for param_name, target in mapping.get("param_map", {}).items():
                node_id = target.get("node_id")
                input_key = target.get("input_key", "value")
                node = find_workflow_node(workflow, node_id)
                if node is None:
                    errors.append(f"{entry.workflow_id}: mapping.param_map.{param_name} missing node {node_id}")
                elif not has_input_key(node, input_key):
                    errors.append(
                        f"{entry.workflow_id}: mapping.param_map.{param_name} cannot inject {node_id}.{input_key}"
                    )

        return errors

    def _build_entries(self, raw_config: dict[str, Any]) -> dict[str, WorkflowCatalogEntry]:
        entries: dict[str, WorkflowCatalogEntry] = {}
        for config_key, config in raw_config.items():
            workflow_id = str(config.get("id", config_key)).strip() or config_key
            frontend_config = config.get("frontend", {})
            frontend = WorkflowFrontendMetadata(
                title=str(frontend_config.get("title", workflow_id)),
                description=str(frontend_config.get("description", config.get("description", workflow_id))),
                icon=str(frontend_config.get("icon", "sparkles")),
                color=str(frontend_config.get("color", "blue")),
                inputs=_tuple_of_strings(frontend_config.get("inputs", [])),
            )
            mapping = config.get("mapping", {})
            audio_map = config.get("audio_map", {})
            if not audio_map and mapping.get("audio_node_id"):
                audio_map = {
                    "audio": {
                        "node_id": mapping["audio_node_id"],
                        "input_key": "audio",
                    }
                }

            entries[workflow_id] = WorkflowCatalogEntry(
                workflow_id=workflow_id,
                file=str(config.get("file", f"{workflow_id}.json")),
                path=self.workflow_dir / str(config.get("file", f"{workflow_id}.json")),
                category=str(config.get("category", "image")),
                description=str(config.get("description", "")),
                aliases=_tuple_of_strings(config.get("aliases", [])),
                mapping=mapping if isinstance(mapping, dict) else {},
                prompt_map=config.get("prompt_map", {}) if isinstance(config.get("prompt_map", {}), dict) else {},
                image_map=config.get("image_map", {}) if isinstance(config.get("image_map", {}), dict) else {},
                audio_map=audio_map if isinstance(audio_map, dict) else {},
                model_overrides=config.get("model_overrides", {})
                if isinstance(config.get("model_overrides", {}), dict)
                else {},
                frontend=frontend,
            )
        return entries

    @staticmethod
    def _build_alias_index(entries: dict[str, WorkflowCatalogEntry]) -> dict[str, str]:
        alias_index: dict[str, str] = {}
        for workflow_id, entry in entries.items():
            for alias in entry.aliases:
                alias_index[alias] = workflow_id
        return alias_index


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
