"""
Storage Service - 本地檔案系統儲存抽象層
=================================
本部署目標為單一伺服器、本地檔案系統輸出，退化為現有的 shutil/send_from_directory 行為。

使用範例:
    from shared.storage_service import storage

    # 上傳檔案
    storage.upload_file('/path/to/local/file.png', 'outputs/job-123/result.png')

    # 取得下載 URL
    url = storage.get_presigned_url('outputs/job-123/result.png')

    # 下載檔案
    storage.download_file('outputs/job-123/result.png', '/path/to/local/dest.png')
"""

import os
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LocalStorage:
    """
    本地檔案系統儲存（既有行為，Windows 開發用）
    """

    def __init__(self):
        from shared.config_base import STORAGE_OUTPUT_DIR
        self.output_dir = STORAGE_OUTPUT_DIR
        logger.info("✓ Storage Backend: local (檔案系統)")

    def upload_file(self, local_path: str, remote_key: str) -> bool:
        """
        本地模式：將檔案複製到 storage/outputs/
        remote_key 格式: outputs/filename.png → 複製到 STORAGE_OUTPUT_DIR/filename.png
        """
        try:
            src = Path(local_path)
            if not src.exists():
                logger.warning(f"⚠️ 來源檔案不存在: {local_path}")
                return False

            # 從 remote_key 取得檔名
            filename = Path(remote_key).name
            dest = self.output_dir / filename
            dest.parent.mkdir(parents=True, exist_ok=True)

            if src != dest:
                shutil.copy2(str(src), str(dest))
                logger.info(f"✓ [Local] 檔案已複製: {src} → {dest}")
            return True
        except Exception as e:
            logger.error(f"❌ [Local] 上傳失敗: {e}")
            return False

    def download_file(self, remote_key: str, local_path: str) -> bool:
        """本地模式：從 storage/outputs/ 複製到指定路徑"""
        try:
            filename = Path(remote_key).name
            src = self.output_dir / filename
            if not src.exists():
                logger.warning(f"⚠️ [Local] 檔案不存在: {src}")
                return False

            dest = Path(local_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            return True
        except Exception as e:
            logger.error(f"❌ [Local] 下載失敗: {e}")
            return False

    def get_presigned_url(self, remote_key: str, expires: int = 3600) -> Optional[str]:
        """本地模式：不產生 pre-signed URL，回傳 None（由 Flask send_from_directory 處理）"""
        return None

    def file_exists(self, remote_key: str) -> bool:
        """本地模式：檢查 storage/outputs/ 中是否存在"""
        filename = Path(remote_key).name
        return (self.output_dir / filename).exists()


def _create_storage():
    """工廠函式：本部署目標僅支援本地檔案系統儲存"""
    backend = os.getenv('STORAGE_BACKEND', 'local').lower()
    if backend != 'local':
        logger.warning("Only local filesystem storage is supported for this deployment; using local storage.")
    return LocalStorage()


# 模組級單例：import 時自動初始化
# 用法: from shared.storage_service import storage
storage = _create_storage()
