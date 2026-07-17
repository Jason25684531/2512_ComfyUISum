from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shared.config_base import (
    COMFYUI_MODELS_DIR,
    COMFYUI_ROOT,
    PROJECT_ROOT,
    STORAGE_DIR,
    ServiceEndpoint,
    resolve_path_setting,
    resolve_service_endpoint,
)


@dataclass(frozen=True)
class LegacyComfyRuntimeSettings:
    endpoint: ServiceEndpoint
    input_dir: Path
    output_dir: Path
    models_dir: Path


def build_legacy_comfy_runtime_settings() -> LegacyComfyRuntimeSettings:
    endpoint = resolve_service_endpoint(
        "COMFYUI_SERVER_URL", "COMFY_HOST", "COMFY_PORT", "127.0.0.1", 8188
    )
    input_dir = resolve_path_setting("COMFYUI_INPUT_DIR", COMFYUI_ROOT / "input", PROJECT_ROOT)
    output_dir = resolve_path_setting("COMFYUI_OUTPUT_DIR", COMFYUI_ROOT / "output", PROJECT_ROOT)
    models_dir = resolve_path_setting("STORAGE_MODELS_DIR", STORAGE_DIR / "models", PROJECT_ROOT)
    input_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    return LegacyComfyRuntimeSettings(endpoint, input_dir, output_dir, models_dir)


__all__ = ["LegacyComfyRuntimeSettings", "build_legacy_comfy_runtime_settings"]
