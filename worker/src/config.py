"""
Worker Configuration
====================
統一管理 Worker 的配置參數。
"""

import sys
from pathlib import Path

# 添加 shared 模組到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config_base import (
    get_env_bool,
    get_env_float,
    get_env_int,
    get_env_str,
    parse_csv_env,
    parse_key_int_map,
)
from shared.runtime_settings import (
    build_legacy_comfy_runtime_settings,
    build_shared_runtime_settings,
)


_SHARED_SETTINGS = build_shared_runtime_settings()
_COMFY_RUNTIME = build_legacy_comfy_runtime_settings(_SHARED_SETTINGS)

PROJECT_ROOT = _SHARED_SETTINGS.project_root
REDIS_HOST = _SHARED_SETTINGS.redis_host
REDIS_PORT = _SHARED_SETTINGS.redis_port
REDIS_PASSWORD = _SHARED_SETTINGS.redis_password
JOB_QUEUE = _SHARED_SETTINGS.job_queue
STORAGE_DIR = _SHARED_SETTINGS.storage_dir
STORAGE_INPUT_DIR = _SHARED_SETTINGS.storage_input_dir
STORAGE_OUTPUT_DIR = _SHARED_SETTINGS.storage_output_dir
WORKFLOW_DIR = _SHARED_SETTINGS.workflow_dir
WORKFLOW_CONFIG_PATH = _SHARED_SETTINGS.workflow_config_path
JOB_STATUS_EXPIRE_SECONDS = _SHARED_SETTINGS.job_status_expire_seconds
COMFYUI_ROOT = _SHARED_SETTINGS.comfyui_root

DEFAULT_UNET_MODEL = get_env_str(
    "DEFAULT_UNET_MODEL",
    "z-image\\z-image-turbo-fp8-e4m3fn.safetensors",
)
DEFAULT_CLIP_MODEL = get_env_str(
    "DEFAULT_CLIP_MODEL",
    "z-image\\qwen_3_4b.safetensors",
)
DEFAULT_VAE_MODEL = get_env_str(
    "DEFAULT_VAE_MODEL",
    "z-image\\ae.safetensors",
)

COMFY_HOST = _COMFY_RUNTIME.endpoint.host
COMFY_PORT = _COMFY_RUNTIME.endpoint.port
COMFYUI_SERVER_URL = _COMFY_RUNTIME.endpoint.http_url
COMFY_HTTP_URL = _COMFY_RUNTIME.endpoint.http_url
COMFY_WS_URL = _COMFY_RUNTIME.endpoint.ws_url
COMFYUI_INPUT_DIR = _COMFY_RUNTIME.input_dir
COMFYUI_OUTPUT_DIR = _COMFY_RUNTIME.output_dir
STORAGE_MODELS_DIR = _COMFY_RUNTIME.models_dir

# Worker 特定配置
TEMP_FILE_MAX_AGE_HOURS = get_env_int("TEMP_FILE_MAX_AGE_HOURS", 1)

# Phase 9/10: Reliability - operation-specific timeout settings
WORKER_TIMEOUT = get_env_int("WORKER_TIMEOUT", 3600)
COMFY_SUBMIT_TIMEOUT_SECONDS = get_env_float("COMFY_SUBMIT_TIMEOUT_SECONDS", 300.0)
COMFY_WS_WAIT_TIMEOUT_SECONDS = get_env_int("COMFY_WS_WAIT_TIMEOUT_SECONDS", WORKER_TIMEOUT)
COMFY_HISTORY_TIMEOUT_SECONDS = get_env_float("COMFY_HISTORY_TIMEOUT_SECONDS", 300.0)
OUTPUT_COPY_RETRY_COUNT = get_env_int("OUTPUT_COPY_RETRY_COUNT", 3)
OUTPUT_COPY_RETRY_DELAY_SECONDS = get_env_float("OUTPUT_COPY_RETRY_DELAY_SECONDS", 1.0)
OUTPUT_COPY_WAIT_SECONDS = get_env_float("OUTPUT_COPY_WAIT_SECONDS", 0.0)
COMFY_POLLING_INTERVAL = get_env_float("COMFY_POLLING_INTERVAL", 0.5)
COMFY_HTTP_TIMEOUT = get_env_float("COMFY_HTTP_TIMEOUT", 300.0)

# Managed Warmup 配置
SKIP_WARMUP = get_env_bool("SKIP_WARMUP", False)

_raw_warmup_mode = get_env_str("WARMUP_MODE", "managed").lower() or "managed"
if _raw_warmup_mode not in {"managed", "legacy", "off"}:
    _raw_warmup_mode = "managed"

WARMUP_MODE = "off" if SKIP_WARMUP else _raw_warmup_mode
WARMUP_STATUS_KEY = get_env_str("WARMUP_STATUS_KEY", "worker:warmup:status")
WARMUP_STATUS_TTL_SECONDS = get_env_int("WARMUP_STATUS_TTL_SECONDS", 86400)
WARMUP_DEFAULT_TIMEOUT = get_env_int("WARMUP_DEFAULT_TIMEOUT", 120)
WARMUP_MAX_PROFILES = get_env_int("WARMUP_MAX_PROFILES", 1)
WARMUP_PRIORITY_HANDOFF_SECONDS = get_env_float("WARMUP_PRIORITY_HANDOFF_SECONDS", 3.0)
WARMUP_PROFILE_NAMES = parse_csv_env("WARMUP_PROFILES", "default-image")
WARMUP_PROFILE_TIMEOUTS = parse_key_int_map("WARMUP_PROFILE_TIMEOUTS")
WARMUP_VIDEO_WORKFLOW_PATH = get_env_str("WARMUP_VIDEO_WORKFLOW_PATH", "")


def print_config() -> None:
    """輸出目前配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] Worker 配置")
    print("=" * 50)
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"WORKFLOW_DIR: {WORKFLOW_DIR}")
    print(f"WORKFLOW_CONFIG_PATH: {WORKFLOW_CONFIG_PATH}")
    print(f"COMFYUI_SERVER_URL: {COMFYUI_SERVER_URL}")
    print(f"COMFYUI_INPUT_DIR: {COMFYUI_INPUT_DIR}")
    print(f"COMFYUI_OUTPUT_DIR: {COMFYUI_OUTPUT_DIR}")
    print(f"STORAGE_MODELS_DIR: {STORAGE_MODELS_DIR}")
    print(f"WORKER_TIMEOUT: {WORKER_TIMEOUT}")
    print(f"WARMUP_MODE: {WARMUP_MODE}")
