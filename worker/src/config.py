"""
Worker Configuration
====================
統一管理 Worker 的配置參數。
繼承共用配置，並擴展 Worker 專用設定。
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

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
)

# ==========================================
# Worker 專用配置
# ==========================================

# ComfyUI 連線配置
_raw_comfy_server_url = os.getenv("COMFYUI_SERVER_URL", "").strip()
if _raw_comfy_server_url and "://" not in _raw_comfy_server_url:
    _raw_comfy_server_url = f"http://{_raw_comfy_server_url}"

_default_comfy_host = os.getenv("COMFY_HOST", "127.0.0.1")
_default_comfy_port = int(os.getenv("COMFY_PORT", "8188"))

if _raw_comfy_server_url:
    _parsed_comfy_server = urlparse(_raw_comfy_server_url)
    _comfy_scheme = _parsed_comfy_server.scheme or "http"
    _comfy_base_path = _parsed_comfy_server.path.rstrip("/")
    COMFY_HOST = _parsed_comfy_server.hostname or _default_comfy_host
    COMFY_PORT = _parsed_comfy_server.port or _default_comfy_port
else:
    _comfy_scheme = "http"
    _comfy_base_path = ""
    COMFY_HOST = _default_comfy_host
    COMFY_PORT = _default_comfy_port

COMFYUI_SERVER_URL = f"{_comfy_scheme}://{COMFY_HOST}:{COMFY_PORT}{_comfy_base_path}"
COMFY_HTTP_URL = COMFYUI_SERVER_URL
COMFY_WS_URL = f"{'wss' if _comfy_scheme == 'https' else 'ws'}://{COMFY_HOST}:{COMFY_PORT}{_comfy_base_path}/ws"

# ComfyUI 資料夾路徑
COMFYUI_INPUT_DIR = Path(os.getenv(
    "COMFYUI_INPUT_DIR",
    str(COMFYUI_ROOT / "input")
))
COMFYUI_OUTPUT_DIR = Path(os.getenv(
    "COMFYUI_OUTPUT_DIR",
    str(COMFYUI_ROOT / "output")
))

# 確保 ComfyUI 輸入目錄存在
COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)

# 額外的儲存目錄
STORAGE_MODELS_DIR = STORAGE_DIR / "models"
STORAGE_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Worker 特定配置
TEMP_FILE_MAX_AGE_HOURS = int(os.getenv("TEMP_FILE_MAX_AGE_HOURS", "1"))

# Phase 9: Reliability - 延長超時配置
WORKER_TIMEOUT = int(os.getenv("WORKER_TIMEOUT", "2400"))  # 預設 40 分鐘
COMFY_POLLING_INTERVAL = float(os.getenv("COMFY_POLLING_INTERVAL", "0.5"))
COMFY_HTTP_TIMEOUT = float(os.getenv("COMFY_HTTP_TIMEOUT", "300.0"))

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
    print(f"  COMFY_HTTP_TIMEOUT: {COMFY_HTTP_TIMEOUT}")
    print(f"  COMFYUI_INPUT_DIR: {COMFYUI_INPUT_DIR}")
    print(f"  COMFYUI_OUTPUT_DIR: {COMFYUI_OUTPUT_DIR}")
    print(f"  STORAGE_OUTPUT_DIR: {STORAGE_OUTPUT_DIR}")
    print(f"  WORKFLOW_DIR: {WORKFLOW_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_config()
