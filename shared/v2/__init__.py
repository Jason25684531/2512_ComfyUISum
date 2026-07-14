from .constants import DEFAULT_OUTPUT_FILENAME_BY_TYPE, V2_CANCEL_KEY_PREFIX, V2_JOB_QUEUE_KEY
from .errors import (
    COMFYUI_OUTPUT_MISSING,
    COMFYUI_MODEL_VALIDATION_FAILED,
    COMFYUI_OUTPUT_DOWNLOAD_FAILED,
    COMFYUI_TIMEOUT,
    COMFYUI_UNAVAILABLE,
    ENGINE_EXECUTION_FAILED,
    INTERNAL_ERROR,
    INVALID_ASSET_UPLOAD,
    INVALID_PATH,
    JOB_NOT_FOUND,
    OUTPUT_NOT_FOUND,
    REDIS_UNAVAILABLE,
    UNKNOWN_ENGINE_MODE,
    WORKFLOW_BINDING_INVALID,
    WORKFLOW_NOT_FOUND,
)
from .job_store import AssetStore, JobStore
from .output_paths import (
    build_job_output_dir,
    build_output_relative_path,
    build_output_url,
    parse_output_path_to_url,
)
from .path_utils import (
    InvalidStoragePathError,
    ensure_storage_layout,
    resolve_storage_path,
    validate_linux_first_path,
    validate_relative_storage_path,
)


def __getattr__(name: str):
    if name == "resolve_repo_relative_path":
        from shared.runtime_settings import resolve_repo_relative_path

        return resolve_repo_relative_path
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from .status import LEGACY_STATUS_BY_V2_STATUS, map_v2_status_to_legacy

__all__ = [
    "COMFYUI_UNAVAILABLE",
    "COMFYUI_OUTPUT_MISSING",
    "COMFYUI_MODEL_VALIDATION_FAILED",
    "COMFYUI_OUTPUT_DOWNLOAD_FAILED",
    "COMFYUI_TIMEOUT",
    "DEFAULT_OUTPUT_FILENAME_BY_TYPE",
    "ENGINE_EXECUTION_FAILED",
    "InvalidStoragePathError",
    "INTERNAL_ERROR",
    "INVALID_ASSET_UPLOAD",
    "INVALID_PATH",
    "AssetStore",
    "JOB_NOT_FOUND",
    "JobStore",
    "LEGACY_STATUS_BY_V2_STATUS",
    "OUTPUT_NOT_FOUND",
    "REDIS_UNAVAILABLE",
    "UNKNOWN_ENGINE_MODE",
    "V2_CANCEL_KEY_PREFIX",
    "V2_JOB_QUEUE_KEY",
    "WORKFLOW_BINDING_INVALID",
    "WORKFLOW_NOT_FOUND",
    "build_job_output_dir",
    "build_output_relative_path",
    "build_output_url",
    "ensure_storage_layout",
    "map_v2_status_to_legacy",
    "parse_output_path_to_url",
    "resolve_storage_path",
    "resolve_repo_relative_path",
    "validate_linux_first_path",
    "validate_relative_storage_path",
]
