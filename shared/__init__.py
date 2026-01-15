"""
Shared Module
=============
專案共用的工具和配置模組。

注意：Database 類需要明確導入：from shared.database import Database
這是為了避免在缺少 mysql-connector-python 的環境中導致導入失敗。
"""

from .utils import load_env, get_project_root
from .config_base import (
    PROJECT_ROOT,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    JOB_QUEUE,
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    STORAGE_DIR,
    STORAGE_INPUT_DIR,
    STORAGE_OUTPUT_DIR,
    WORKFLOW_DIR,
    WORKFLOW_CONFIG_PATH,
    JOB_STATUS_EXPIRE_SECONDS,
    COMFYUI_ROOT,
    COMFYUI_MODELS_DIR,
)

__all__ = [
    'load_env',
    'get_project_root',
    'PROJECT_ROOT',
    'REDIS_HOST',
    'REDIS_PORT',
    'REDIS_PASSWORD',
    'JOB_QUEUE',
    'DB_HOST',
    'DB_PORT',
    'DB_USER',
    'DB_PASSWORD',
    'DB_NAME',
    'STORAGE_DIR',
    'STORAGE_INPUT_DIR',
    'STORAGE_OUTPUT_DIR',
    'WORKFLOW_DIR',
    'WORKFLOW_CONFIG_PATH',
    'JOB_STATUS_EXPIRE_SECONDS',
    'COMFYUI_ROOT',
    'COMFYUI_MODELS_DIR',
]
