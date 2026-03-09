"""
Storage Service - 統一儲存抽象層
=================================
根據 STORAGE_BACKEND 環境變數切換 local (檔案系統) 或 s3 (TWCC COS/MinIO) 模式。
- local 模式：退化為現有的 shutil/send_from_directory 行為，Windows 開發零影響
- s3 模式：用 boto3 操作 S3 相容物件儲存（TWCC COS / MinIO）

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


class S3Storage:
    """
    S3 相容物件儲存（TWCC COS / MinIO）
    必須指定 endpoint_url，否則 boto3 預設連向 AWS
    """

    def __init__(self):
        try:
            import boto3
            from botocore.exceptions import ClientError, EndpointConnectionError
        except ImportError:
            raise ImportError(
                "S3 儲存需要 boto3。請安裝: pip install boto3"
            )

        self.endpoint = os.getenv('S3_ENDPOINT')
        self.bucket = os.getenv('S3_BUCKET', 'studio-outputs')
        self.access_key = os.getenv('S3_ACCESS_KEY')
        self.secret_key = os.getenv('S3_SECRET_KEY')
        self.region = os.getenv('S3_REGION', '') or None

        if not self.endpoint:
            raise ValueError(
                "S3_ENDPOINT 未設定！TWCC COS 必須指定 endpoint_url，"
                "否則 boto3 會預設連向 AWS。"
                "請在 .env.twcc 中設定 S3_ENDPOINT=https://cos.twcc.ai"
            )

        # 初始化 S3 client（強制指定 endpoint_url）
        client_kwargs = {
            'service_name': 's3',
            'endpoint_url': self.endpoint,
            'aws_access_key_id': self.access_key,
            'aws_secret_access_key': self.secret_key,
        }
        if self.region:
            client_kwargs['region_name'] = self.region

        self.client = boto3.client(**client_kwargs)

        # 連線測試：確認 bucket 可存取
        try:
            self.client.head_bucket(Bucket=self.bucket)
            logger.info(f"✓ Storage Backend: s3 ({self.endpoint}/{self.bucket})")
        except Exception as e:
            logger.warning(
                f"⚠️ S3 Bucket 存取測試失敗 ({self.bucket}): {e}。"
                f"上傳/下載可能會失敗。請確認 Bucket 已建立且金鑰正確。"
            )

    def upload_file(self, local_path: str, remote_key: str) -> bool:
        """上傳檔案到 S3/COS"""
        try:
            src = Path(local_path)
            if not src.exists():
                logger.warning(f"⚠️ 來源檔案不存在: {local_path}")
                return False

            # 根據檔案副檔名設定 Content-Type
            content_type = self._guess_content_type(src.suffix)
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            self.client.upload_file(
                str(src), self.bucket, remote_key,
                ExtraArgs=extra_args
            )
            logger.info(f"✓ [S3] 已上傳: {remote_key} ({src.stat().st_size} bytes)")
            return True
        except Exception as e:
            logger.error(f"❌ [S3] 上傳失敗 ({remote_key}): {e}")
            return False

    def download_file(self, remote_key: str, local_path: str) -> bool:
        """從 S3/COS 下載檔案"""
        try:
            dest = Path(local_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.client.download_file(self.bucket, remote_key, str(dest))
            logger.info(f"✓ [S3] 已下載: {remote_key} → {dest}")
            return True
        except Exception as e:
            logger.error(f"❌ [S3] 下載失敗 ({remote_key}): {e}")
            return False

    def get_presigned_url(self, remote_key: str, expires: int = 3600) -> Optional[str]:
        """產生 Pre-signed URL（用於前端直接下載/顯示）"""
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': remote_key},
                ExpiresIn=expires
            )
            logger.debug(f"✓ [S3] Pre-signed URL: {remote_key} (expires={expires}s)")
            return url
        except Exception as e:
            logger.error(f"❌ [S3] Pre-signed URL 產生失敗 ({remote_key}): {e}")
            return None

    def file_exists(self, remote_key: str) -> bool:
        """檢查 S3/COS 上的檔案是否存在"""
        try:
            self.client.head_object(Bucket=self.bucket, Key=remote_key)
            return True
        except Exception:
            return False

    @staticmethod
    def _guess_content_type(suffix: str) -> Optional[str]:
        """根據副檔名猜測 MIME type"""
        mapping = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
        }
        return mapping.get(suffix.lower())


def _create_storage():
    """
    工廠函式：根據 STORAGE_BACKEND 環境變數建立對應的儲存實例
    - 'local' (預設): 使用本地檔案系統
    - 's3': 使用 S3 相容物件儲存
    """
    backend = os.getenv('STORAGE_BACKEND', 'local').lower()

    if backend == 's3':
        try:
            return S3Storage()
        except Exception as e:
            logger.warning(f"⚠️ S3 儲存初始化失敗，降級為本地: {e}")
            return LocalStorage()
    else:
        return LocalStorage()


# 模組級單例：import 時自動初始化
# 用法: from shared.storage_service import storage
storage = _create_storage()
