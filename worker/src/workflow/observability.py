"""Manifest-driven workflow facts used by job tracking, never by dashboard routes."""
from __future__ import annotations

from typing import Any


class WorkflowAdapter:
    def __init__(self, entry):
        self.entry = entry
        self.meta = entry.observability

    def model(self, workflow: dict[str, Any], fallback: str = "unknown") -> str:
        source = self.meta.get("model_source", {})
        node = workflow.get(str(source.get("node_id")), {})
        inputs = node.get("inputs", {}) if isinstance(node, dict) else {}
        value = inputs.get(source.get("input")) if isinstance(inputs, dict) else None
        if value:
            return str(value)
        for node in workflow.values():
            if isinstance(node, dict) and node.get("class_type") in {"UNETLoader", "CheckpointLoaderSimple"}:
                inputs = node.get("inputs", {})
                if isinstance(inputs, dict):
                    return str(inputs.get("unet_name") or inputs.get("ckpt_name") or fallback)
        return fallback

    def node(self, workflow: dict[str, Any], node_id: object) -> dict[str, str]:
        key = str(node_id or "")
        node = workflow.get(key, {})
        node_type = str(node.get("class_type", "unknown")) if isinstance(node, dict) else "unknown"
        stage = "unknown"
        for item in self.meta.get("important_nodes", []):
            if str(item.get("node_id")) == key:
                stage = str(item.get("stage", "unknown"))
                break
        return {"node_id": key, "node_type": node_type, "stage": stage}

    def is_important(self, node_id: object) -> bool:
        return any(str(item.get("node_id")) == str(node_id) for item in self.meta.get("important_nodes", []))

    def expected_output_nodes(self) -> tuple[str, ...]:
        output = self.meta.get("output", {})
        return tuple(str(value) for value in output.get("node_ids", []) if str(value))

    def timeout_seconds(self) -> int:
        return max(1, int(self.meta.get("timeout_seconds", 3600)))
