"""
Worker Configuration
====================
統一管理 Worker 的配置參數。
優先使用環境變數，提供合理的預設值。
"""

import os
from pathlib import Path

# ==========================================
# 專案根目錄 (基於此檔案的位置計算)
# ==========================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

# ==========================================
# Redis 配置
# ==========================================
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
JOB_QUEUE = os.getenv("JOB_QUEUE", "job_queue")

# ==========================================
# ComfyUI 配置
# ==========================================
COMFY_HOST = os.getenv("COMFY_HOST", "127.0.0.1")
COMFY_PORT = int(os.getenv("COMFY_PORT", "8188"))
COMFY_HTTP_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"
COMFY_WS_URL = f"ws://{COMFY_HOST}:{COMFY_PORT}/ws"

# ComfyUI 資料夾路徑
# 預設值假設 ComfyUI 安裝在專案的上層目錄
# 生產環境請透過環境變數覆寫
_default_comfy_root = PROJECT_ROOT.parent / "ComfyUI_windows_portable" / "ComfyUI"
COMFYUI_INPUT_DIR = Path(os.getenv(
    "COMFYUI_INPUT_DIR",
    str(_default_comfy_root / "input")
))
COMFYUI_OUTPUT_DIR = Path(os.getenv(
    "COMFYUI_OUTPUT_DIR",
    str(_default_comfy_root / "output")
))

# ==========================================
# 本地儲存配置
# ==========================================
STORAGE_DIR = PROJECT_ROOT / "storage"
STORAGE_INPUT_DIR = STORAGE_DIR / "inputs"
STORAGE_OUTPUT_DIR = STORAGE_DIR / "outputs"
STORAGE_MODELS_DIR = STORAGE_DIR / "models"

# 確保儲存目錄存在
STORAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Workflow 配置
# ==========================================
WORKFLOW_DIR = PROJECT_ROOT / "ComfyUIworkflow"

# ==========================================
# Worker 配置
# ==========================================
TEMP_FILE_MAX_AGE_HOURS = int(os.getenv("TEMP_FILE_MAX_AGE_HOURS", "1"))
JOB_STATUS_EXPIRE_SECONDS = int(os.getenv("JOB_STATUS_EXPIRE_SECONDS", "3600"))

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
