"""
Worker Configuration
====================
統一管理 Worker 的配置參數。
繼承共用配置，並擴展 Worker 專用設定。
"""

import os
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
)

# ==========================================
# Worker 專用配置
# ==========================================

# ComfyUI 連線配置
COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_PORT = int(os.getenv("COMFY_PORT", "8188"))
COMFY_HTTP_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"
COMFY_WS_URL = f"ws://{COMFY_HOST}:{COMFY_PORT}/ws"

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
WORKER_TIMEOUT = int(os.getenv("WORKER_TIMEOUT", "3600"))  # 預設 1 小時
COMFY_POLLING_INTERVAL = float(os.getenv("COMFY_POLLING_INTERVAL", "0.5"))

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
    print(f"  COMFYUI_INPUT_DIR: {COMFYUI_INPUT_DIR}")
    print(f"  COMFYUI_OUTPUT_DIR: {COMFYUI_OUTPUT_DIR}")
    print(f"  STORAGE_OUTPUT_DIR: {STORAGE_OUTPUT_DIR}")
    print(f"  WORKFLOW_DIR: {WORKFLOW_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_config()
