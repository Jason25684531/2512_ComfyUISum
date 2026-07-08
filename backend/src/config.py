"""
Backend Configuration
=====================
統一管理 Backend API 的配置參數。
"""

import sys
from pathlib import Path

# 添加 shared 模組到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config_base import get_env_bool, get_env_int, get_env_str
from shared.runtime_settings import build_shared_runtime_settings


_SHARED_SETTINGS = build_shared_runtime_settings()

PROJECT_ROOT = _SHARED_SETTINGS.project_root
REDIS_HOST = _SHARED_SETTINGS.redis_host
REDIS_PORT = _SHARED_SETTINGS.redis_port
REDIS_PASSWORD = _SHARED_SETTINGS.redis_password
JOB_QUEUE = _SHARED_SETTINGS.job_queue
STORAGE_DIR = _SHARED_SETTINGS.storage_dir
STORAGE_INPUT_DIR = _SHARED_SETTINGS.storage_input_dir
STORAGE_OUTPUT_DIR = _SHARED_SETTINGS.storage_output_dir
JOB_STATUS_EXPIRE_SECONDS = _SHARED_SETTINGS.job_status_expire_seconds
COMFYUI_ROOT = _SHARED_SETTINGS.comfyui_root
COMFYUI_MODELS_DIR = _SHARED_SETTINGS.comfyui_models_dir

# Flask 配置
FLASK_DEBUG = get_env_bool("FLASK_DEBUG", False)
FLASK_HOST = get_env_str("FLASK_HOST", "0.0.0.0") or "0.0.0.0"
FLASK_PORT = get_env_int("FLASK_PORT", 5001)

# ComfyUI 模型路徑（模型掃描用）
COMFYUI_CHECKPOINTS_DIR = COMFYUI_MODELS_DIR / "checkpoints"
COMFYUI_UNET_DIR = COMFYUI_MODELS_DIR / "unet"

# [TEMP] Veo3 測試模式
VEO3_TEST_MODE = get_env_bool("VEO3_TEST_MODE", False)
VEO3_TEST_VIDEO_PATH = get_env_str("VEO3_TEST_VIDEO_PATH", "tests/IU_Final/IU_Combine.mp4")


def print_config() -> None:
    """輸出目前配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] Backend 配置")
    print("=" * 50)
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"REDIS_HOST: {REDIS_HOST}")
    print(f"REDIS_PORT: {REDIS_PORT}")
    print(f"JOB_QUEUE: {JOB_QUEUE}")
    print(f"STORAGE_DIR: {STORAGE_DIR}")
    print(f"COMFYUI_MODELS_DIR: {COMFYUI_MODELS_DIR}")
    print(f"FLASK_DEBUG: {FLASK_DEBUG}")
    print(f"FLASK_HOST: {FLASK_HOST}")
    print(f"FLASK_PORT: {FLASK_PORT}")
    print(f"VEO3_TEST_MODE: {VEO3_TEST_MODE}")
