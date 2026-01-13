"""
Shared Utilities
================
專案共用的工具函式，供 Backend 和 Worker 使用。
避免代碼重複，提高維護性。
"""

import os
from pathlib import Path


def load_env(base_path: Path = None) -> None:
    """
    自動載入專案根目錄的 .env 檔案
    
    Args:
        base_path: 基礎路徑，預設為呼叫檔案的上上層目錄
    """
    if base_path is None:
        # 預設使用專案根目錄
        base_path = Path(__file__).parent.parent
    
    env_path = base_path / ".env"
    
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"✓ 已載入 .env 檔案: {env_path}")
    else:
        print(f"⚠️ .env 檔案不存在: {env_path}")


def get_project_root() -> Path:
    """
    取得專案根目錄的絕對路徑
    
    Returns:
        專案根目錄 Path 物件
    """
    return Path(__file__).parent.parent.resolve()
