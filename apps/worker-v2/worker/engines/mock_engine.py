from __future__ import annotations

import base64
from pathlib import Path

from app.models.job import JobPayload
from shared.v2.path_utils import ensure_storage_layout, resolve_storage_path, validate_relative_storage_path
from worker.engines.base import EngineAdapter, EngineResult


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0ioAAAAASUVORK5CYII="
)
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
WAV_BYTES = (
    b"RIFF$\x00\x00\x00WAVEfmt "
    b"\x10\x00\x00\x00\x01\x00\x01\x00"
    b"@\x1f\x00\x00\x80>\x00\x00"
    b"\x02\x00\x10\x00data\x00\x00\x00\x00"
)


class MockEngine(EngineAdapter):
    def __init__(self, *, settings, workflow_registry) -> None:
        self.settings = settings
        self.workflow_registry = workflow_registry
        ensure_storage_layout(
            self.settings.storage_root,
            asset_root=self.settings.asset_root,
            output_root=self.settings.output_root,
        )

    def execute(self, job_payload: JobPayload) -> EngineResult:
        manifest = self.workflow_registry.get(job_payload.task_type)
        if manifest is None:
            return EngineResult(success=False, error_message="Workflow manifest was not found.")

        bytes_to_write = self._payload_for_output_type(manifest.output_type)
        relative_path = validate_relative_storage_path(
            f"{self.settings.output_root}/job_{job_payload.job_id}/{manifest.mock_output_filename}"
        )
        destination = resolve_storage_path(self.settings.storage_root, relative_path)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(bytes_to_write)
        return EngineResult(success=True, output_path=relative_path)

    def health_check(self) -> bool:
        return True

    @staticmethod
    def _payload_for_output_type(output_type: str) -> bytes:
        if output_type == "image":
            return PNG_BYTES
        if output_type == "video":
            return MP4_BYTES
        return WAV_BYTES
