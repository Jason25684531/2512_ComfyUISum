from __future__ import annotations

import json
import logging
from pathlib import Path

from workflow_registry.models import WorkflowManifest


LOGGER = logging.getLogger(__name__)


class WorkflowRegistry:
    def __init__(self, manifests: dict[str, WorkflowManifest] | None = None) -> None:
        self._manifests = manifests or {}

    @classmethod
    def from_directory(cls, directory: Path) -> "WorkflowRegistry":
        manifests: dict[str, WorkflowManifest] = {}
        if not directory.exists():
            LOGGER.warning("Workflow manifest directory is missing: %s", directory)
            return cls(manifests)

        for manifest_path in sorted(directory.glob("*.json")):
            try:
                manifest = WorkflowManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
            except Exception:
                LOGGER.warning("Skipping invalid workflow manifest: %s", manifest_path)
                continue

            if manifest.task_type in manifests:
                LOGGER.warning("Duplicate workflow task_type ignored: %s", manifest.task_type)
                continue
            manifests[manifest.task_type] = manifest
        return cls(manifests)

    def get(self, task_type: str) -> WorkflowManifest | None:
        return self._manifests.get(task_type)

    def list_all(self) -> list[WorkflowManifest]:
        return [self._manifests[key] for key in sorted(self._manifests)]
