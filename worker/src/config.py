"""
Worker Configuration
====================
統一管理 Worker 的配置參數。
繼承共用配置，並擴展 Worker 專用設定。
"""

import sys
from pathlib import Path

# 添加 shared 模組到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ==========================================
# 繼承共用配置
# ==========================================
from shared.config_base import (
    PROJECT_ROOT,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    JOB_QUEUE,
    STORAGE_DIR,
    STORAGE_INPUT_DIR,
    STORAGE_OUTPUT_DIR,
    WORKFLOW_DIR,
    WORKFLOW_CONFIG_PATH,
    JOB_STATUS_EXPIRE_SECONDS,
    COMFYUI_ROOT,
    get_env_bool,
    get_env_float,
    get_env_int,
    get_env_str,
    parse_csv_env,
    parse_key_int_map,
    resolve_path_setting,
    resolve_service_endpoint,
)

# ==========================================
# Worker 專用配置
# ==========================================

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

# ComfyUI 連線配置
_comfy_endpoint = resolve_service_endpoint(
    "COMFYUI_SERVER_URL",
    "COMFY_HOST",
    "COMFY_PORT",
    "127.0.0.1",
    8188,
)
COMFY_HOST = _comfy_endpoint.host
COMFY_PORT = _comfy_endpoint.port
COMFYUI_SERVER_URL = _comfy_endpoint.http_url
COMFY_HTTP_URL = COMFYUI_SERVER_URL
COMFY_WS_URL = _comfy_endpoint.ws_url

# ComfyUI 資料夾路徑
COMFYUI_INPUT_DIR = resolve_path_setting(
    "COMFYUI_INPUT_DIR",
    COMFYUI_ROOT / "input",
    PROJECT_ROOT,
)
COMFYUI_OUTPUT_DIR = resolve_path_setting(
    "COMFYUI_OUTPUT_DIR",
    COMFYUI_ROOT / "output",
    PROJECT_ROOT,
)

# 確保 ComfyUI 輸入目錄存在
COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)

# 額外的儲存目錄
STORAGE_MODELS_DIR = STORAGE_DIR / "models"
STORAGE_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Worker 特定配置
TEMP_FILE_MAX_AGE_HOURS = get_env_int("TEMP_FILE_MAX_AGE_HOURS", 1)

# Phase 9: Reliability - 延長超時配置
WORKER_TIMEOUT = get_env_int("WORKER_TIMEOUT", 2400)  # 預設 40 分鐘
COMFY_POLLING_INTERVAL = get_env_float("COMFY_POLLING_INTERVAL", 0.5)
COMFY_HTTP_TIMEOUT = get_env_float("COMFY_HTTP_TIMEOUT", 300.0)

# ==========================================
# Managed Warmup 配置
# ==========================================
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

# ==========================================
# 除錯輸出
# ==========================================
def print_config():
    """輸出目前配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] Worker 配置")
    print("=" * 50)
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  REDIS: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  COMFY: {COMFY_HOST}:{COMFY_PORT}")
    print(f"  COMFYUI_SERVER_URL: {COMFYUI_SERVER_URL}")
    print(f"  DEFAULT_UNET_MODEL: {DEFAULT_UNET_MODEL}")
    print(f"  COMFY_HTTP_TIMEOUT: {COMFY_HTTP_TIMEOUT}")
    print(f"  WARMUP_MODE: {WARMUP_MODE}")
    print(f"  WARMUP_PROFILES: {WARMUP_PROFILE_NAMES}")
    print(f"  WARMUP_MAX_PROFILES: {WARMUP_MAX_PROFILES}")
    print(f"  COMFYUI_INPUT_DIR: {COMFYUI_INPUT_DIR}")
    print(f"  COMFYUI_OUTPUT_DIR: {COMFYUI_OUTPUT_DIR}")
    print(f"  STORAGE_OUTPUT_DIR: {STORAGE_OUTPUT_DIR}")
    print(f"  WORKFLOW_DIR: {WORKFLOW_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_config()
