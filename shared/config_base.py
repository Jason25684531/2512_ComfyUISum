"""
Shared Configuration Base
=========================
專案共用的配置參數，避免 Backend 和 Worker 配置重複。
各模組可繼承並擴展特定配置。
"""

import os
from pathlib import Path

# ==========================================
# 專案根目錄
# ==========================================
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ==========================================
# Redis 配置 (共用)
# ==========================================
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "mysecret")
JOB_QUEUE = os.getenv("JOB_QUEUE", "job_queue")

# ==========================================
# 資料庫配置 (共用)
# ==========================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "studio_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "studio_password")
DB_NAME = os.getenv("DB_NAME", "studio_db")

# ==========================================
# 本地儲存配置 (共用)
# ==========================================
STORAGE_DIR = PROJECT_ROOT / "storage"
STORAGE_INPUT_DIR = STORAGE_DIR / "inputs"
STORAGE_OUTPUT_DIR = STORAGE_DIR / "outputs"

# 確保儲存目錄存在
STORAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Workflow 配置 (共用)
# ==========================================
WORKFLOW_DIR = PROJECT_ROOT / "ComfyUIworkflow"
WORKFLOW_CONFIG_PATH = WORKFLOW_DIR / "config.json"

# ==========================================
# 任務配置 (共用)
# ==========================================
JOB_STATUS_EXPIRE_SECONDS = int(os.getenv("JOB_STATUS_EXPIRE_SECONDS", "3600"))

# ==========================================
# ComfyUI 配置 (共用)
# ==========================================
_default_comfy_root = PROJECT_ROOT.parent / "ComfyUI_windows_portable" / "ComfyUI"
COMFYUI_ROOT = Path(os.getenv("COMFYUI_ROOT", str(_default_comfy_root)))
COMFYUI_MODELS_DIR = COMFYUI_ROOT / "models"


def print_base_config():
    """輸出基礎配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] 共用配置")
    print("=" * 50)
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  REDIS: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  DB: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"  STORAGE_DIR: {STORAGE_DIR}")
    print(f"  WORKFLOW_DIR: {WORKFLOW_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_base_config()
