"""
Backend Configuration
=====================
統一管理 Backend API 的配置參數。
繼承共用配置，並擴展 Backend 專用設定。
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
    JOB_STATUS_EXPIRE_SECONDS,
    COMFYUI_ROOT,
    COMFYUI_MODELS_DIR,
)

# ==========================================
# Backend 專用配置
# ==========================================

# Flask 配置
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5001"))

# ComfyUI 模型路徑（模型掃描用）
COMFYUI_CHECKPOINTS_DIR = COMFYUI_MODELS_DIR / "checkpoints"
COMFYUI_UNET_DIR = COMFYUI_MODELS_DIR / "unet"

# ==========================================
# [TEMP] Veo3 測試模式 (Veo3 Test Mode)
# ==========================================
# 當啟用時，veo3_long_video 工作流只要上傳圖片就直接返回測試視頻
VEO3_TEST_MODE = os.getenv("VEO3_TEST_MODE", "false").lower() == "true"
VEO3_TEST_VIDEO_PATH = os.getenv("VEO3_TEST_VIDEO_PATH", "tests/IU_Final/IU_Combine.mp4")

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
