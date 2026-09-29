"""
Backend Configuration
=====================
統一管理 Backend API 的配置參數。
"""

import sys
from pathlib import Path

# 添加 shared 模組到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config_base import (
    COMFYUI_MODELS_DIR,
    COMFYUI_ROOT,
    JOB_QUEUE,
    JOB_STATUS_EXPIRE_SECONDS,
    PROJECT_ROOT,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    STORAGE_DIR,
    STORAGE_INPUT_DIR,
    STORAGE_OUTPUT_DIR,
    get_env_int,
    get_env_str,
)

# Flask 配置
FLASK_HOST = get_env_str("FLASK_HOST", "0.0.0.0") or "0.0.0.0"
FLASK_PORT = get_env_int("FLASK_PORT", 5001)
APP_SECRET_KEY = get_env_str("SECRET_KEY", "dev-secret-key-change-in-production")
MAX_UPLOAD_SIZE_MB = get_env_int("MAX_UPLOAD_SIZE_MB", 200)
CORS_ALLOWED_ORIGINS = get_env_str("CORS_ALLOWED_ORIGINS", "")
SESSION_COOKIE_SECURE = get_env_str("SESSION_COOKIE_SECURE", "")
WARMUP_STATUS_KEY = get_env_str("WARMUP_STATUS_KEY", "worker:warmup:status")
COMFY_HTTP_URL = get_env_str("COMFY_HTTP_URL", "http://127.0.0.1:8188")

# LINE is a Backend adapter concern; values are loaded from the active env
# contract and are never emitted by configuration diagnostics.
LINE_CHANNEL_SECRET = get_env_str("LINE_CHANNEL_SECRET", "").strip()
LINE_CHANNEL_ACCESS_TOKEN = get_env_str("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_PUBLIC_BASE_URL = get_env_str("LINE_PUBLIC_BASE_URL", "").strip().rstrip("/")
LINE_VIDEO_WORKFLOW_ID = get_env_str("LINE_VIDEO_WORKFLOW_ID", "ltx_i2v").strip() or "ltx_i2v"
LINE_PENDING_IMAGE_TTL = max(600, min(1800, get_env_int("LINE_PENDING_IMAGE_TTL", 1200)))
LINE_DOWNLOAD_TOKEN_TTL = max(60, get_env_int("LINE_DOWNLOAD_TOKEN_TTL", 1800))
LINE_JOB_MAPPING_TTL = max(600, get_env_int("LINE_JOB_MAPPING_TTL", 86400))
LINE_MAX_WEBHOOK_BYTES = max(1024, get_env_int("LINE_MAX_WEBHOOK_BYTES", 1024 * 1024))
LINE_MAX_IMAGE_BYTES = max(1024, get_env_int("LINE_MAX_IMAGE_BYTES", 10 * 1024 * 1024))
LINE_MAX_VIDEO_BYTES = 200 * 1024 * 1024
LINE_MAX_PREVIEW_BYTES = 1024 * 1024
LINE_API_TIMEOUT_SECONDS = max(1, get_env_int("LINE_API_TIMEOUT_SECONDS", 15))
LINE_NOTIFICATION_RETRY_LIMIT = max(1, get_env_int("LINE_NOTIFICATION_RETRY_LIMIT", 3))

# ComfyUI 模型路徑（模型掃描用）
COMFYUI_CHECKPOINTS_DIR = COMFYUI_MODELS_DIR / "checkpoints"
COMFYUI_UNET_DIR = COMFYUI_MODELS_DIR / "unet"
