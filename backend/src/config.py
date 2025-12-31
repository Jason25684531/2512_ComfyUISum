"""
Backend Configuration
=====================
統一管理 Backend API 的配置參數。
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
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "mysecret")
JOB_QUEUE = os.getenv("JOB_QUEUE", "job_queue")

# ==========================================
# 本地儲存配置
# ==========================================
STORAGE_DIR = PROJECT_ROOT / "storage"
STORAGE_INPUT_DIR = STORAGE_DIR / "inputs"
STORAGE_OUTPUT_DIR = STORAGE_DIR / "outputs"

# 確保儲存目錄存在
STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Flask 配置
# ==========================================
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5001"))

# ==========================================
# 任務配置
# ==========================================
JOB_STATUS_EXPIRE_SECONDS = int(os.getenv("JOB_STATUS_EXPIRE_SECONDS", "3600"))

# ==========================================
# ComfyUI 配置 (用於模型掃描)
# ==========================================
_default_comfy_root = PROJECT_ROOT.parent / "ComfyUI_windows_portable" / "ComfyUI"
COMFYUI_ROOT = Path(os.getenv("COMFYUI_ROOT", str(_default_comfy_root)))
COMFYUI_MODELS_DIR = COMFYUI_ROOT / "models"
COMFYUI_CHECKPOINTS_DIR = COMFYUI_MODELS_DIR / "checkpoints"
COMFYUI_UNET_DIR = COMFYUI_MODELS_DIR / "unet"

# ==========================================
# 除錯輸出
# ==========================================
def print_config():
    """輸出目前配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] Backend 配置")
    print("=" * 50)
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  REDIS: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  FLASK: {FLASK_HOST}:{FLASK_PORT}")
    print(f"  STORAGE_OUTPUT_DIR: {STORAGE_OUTPUT_DIR}")
    print(f"  COMFYUI_ROOT: {COMFYUI_ROOT}")
    print(f"  COMFYUI_CHECKPOINTS_DIR: {COMFYUI_CHECKPOINTS_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_config()
