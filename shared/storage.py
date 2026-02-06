"""
S3 Storage Module
=================
統一的 S3/MinIO 對象存儲管理模組
支援上傳、下載、預簽名 URL 生成等操作
"""

import os
import boto3
import logging
from pathlib import Path
from typing import Optional, Union
from botocore.exceptions import ClientError
from datetime import timedelta

logger = logging.getLogger(__name__)


class S3StorageClient:
    """S3/MinIO 對象存儲客戶端"""
    
    def __init__(
        self,
        endpoint_url: str = None,
        access_key: str = None,
        secret_key: str = None,
        bucket_name: str = "comfyui-outputs",
        region: str = "us-east-1"
    ):
        """
        初始化 S3 客戶端
        
        Args:
            endpoint_url: S3 端點 URL (MinIO 使用，AWS S3 不需要)
            access_key: Access Key ID
            secret_key: Secret Access Key
            bucket_name: 預設儲存桶名稱
            region: AWS 區域 (MinIO 可忽略)
        """
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL", "http://minio-service:9000")
        self.access_key = access_key or os.getenv("S3_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("S3_SECRET_KEY", "minioadmin")
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME", "comfyui-outputs")
        self.region = region or os.getenv("S3_REGION", "us-east-1")
        
        # 初始化 boto3 客戶端
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region,
                config=boto3.session.Config(signature_version='s3v4')
            )
            logger.info(f"✓ S3 客戶端初始化成功: {self.endpoint_url}")
            
            # 確保儲存桶存在
            self._ensure_bucket_exists()
            
        except Exception as e:
            logger.error(f"✗ S3 客戶端初始化失敗: {e}")
            raise
    
    def _ensure_bucket_exists(self):
        """確保儲存桶存在，不存在則創建"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"✓ 儲存桶 '{self.bucket_name}' 已存在")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # 儲存桶不存在，創建它
                try:
                    create_kwargs = {"Bucket": self.bucket_name}
                    if (not self.endpoint_url) and self.region and self.region != "us-east-1":
                        create_kwargs["CreateBucketConfiguration"] = {
                            "LocationConstraint": self.region
                        }
                    self.s3_client.create_bucket(**create_kwargs)
                    logger.info(f"✓ 已創建儲存桶: {self.bucket_name}")
                except Exception as create_error:
                    logger.error(f"✗ 創建儲存桶失敗: {create_error}")
                    raise
            else:
                logger.error(f"✗ 檢查儲存桶失敗: {e}")
                raise
    
    def upload_file(
        self,
        file_path: Union[str, Path],
        object_key: str,
        content_type: Optional[str] = None
    ) -> bool:
        """
        上傳檔案到 S3
        
        Args:
            file_path: 本地檔案路徑
            object_key: S3 對象鍵 (例如: outputs/job-123/result.png)
            content_type: MIME 類型 (可選)
        
        Returns:
            上傳成功返回 True，失敗返回 False
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"✗ 檔案不存在: {file_path}")
                return False
            
            # 自動偵測 content_type
            if not content_type:
                import mimetypes
                content_type, _ = mimetypes.guess_type(str(file_path))
                content_type = content_type or 'application/octet-stream'
            
            # 上傳檔案
            with open(file_path, 'rb') as f:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=object_key,
                    Body=f,
                    ContentType=content_type
                )
            
            logger.info(f"✓ 檔案已上傳: {object_key}")
            return True
            
        except Exception as e:
            logger.error(f"✗ 上傳檔案失敗: {e}")
            return False
    
    def upload_bytes(
        self,
        file_bytes: bytes,
        object_key: str,
        content_type: str = 'application/octet-stream'
    ) -> bool:
        """
        上傳二進位數據到 S3
        
        Args:
            file_bytes: 檔案的二進位數據
            object_key: S3 對象鍵
            content_type: MIME 類型
        
        Returns:
            上傳成功返回 True，失敗返回 False
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type
            )
            logger.info(f"✓ 二進位數據已上傳: {object_key}")
            return True
            
        except Exception as e:
            logger.error(f"✗ 上傳二進位數據失敗: {e}")
            return False
    
    def download_file(
        self,
        object_key: str,
        local_path: Union[str, Path]
    ) -> bool:
        """
        從 S3 下載檔案
        
        Args:
            object_key: S3 對象鍵
            local_path: 本地儲存路徑
        
        Returns:
            下載成功返回 True，失敗返回 False
        """
        try:
            local_path = Path(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.s3_client.download_file(
                Bucket=self.bucket_name,
                Key=object_key,
                Filename=str(local_path)
            )
            
            logger.info(f"✓ 檔案已下載: {object_key} -> {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"✗ 下載檔案失敗: {e}")
            return False
    
    def get_presigned_url(
        self,
        object_key: str,
        expiration: int = 3600
    ) -> Optional[str]:
        """
        生成預簽名 URL (供前端直接訪問)
        
        Args:
            object_key: S3 對象鍵
            expiration: 過期時間 (秒)，預設 1 小時
        
        Returns:
            預簽名 URL，失敗返回 None
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': object_key},
                ExpiresIn=expiration
            )
            logger.info(f"✓ 已生成預簽名 URL: {object_key}")
            return url
            
        except Exception as e:
            logger.error(f"✗ 生成預簽名 URL 失敗: {e}")
            return None
    
    def delete_file(self, object_key: str) -> bool:
        """
        刪除 S3 上的檔案
        
        Args:
            object_key: S3 對象鍵
        
        Returns:
            刪除成功返回 True，失敗返回 False
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            logger.info(f"✓ 檔案已刪除: {object_key}")
            return True
            
        except Exception as e:
            logger.error(f"✗ 刪除檔案失敗: {e}")
            return False
    
    def list_objects(self, prefix: str = "") -> list:
        """
        列出儲存桶中的對象
        
        Args:
            prefix: 對象鍵前綴 (用於過濾)
        
        Returns:
            對象列表
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                return []
            
            objects = [obj['Key'] for obj in response['Contents']]
            logger.info(f"✓ 列出對象: {len(objects)} 個")
            return objects
            
        except Exception as e:
            logger.error(f"✗ 列出對象失敗: {e}")
            return []


def get_storage_client(storage_type: str = None) -> Optional[S3StorageClient]:
    """
    工廠函式：根據配置獲取儲存客戶端
    
    Args:
        storage_type: 儲存類型 ('s3' 或 'local')，預設從環境變數讀取
    
    Returns:
        S3StorageClient 實例，如果配置為 local 則返回 None
    """
    storage_type = storage_type or os.getenv("STORAGE_TYPE", "local")
    
    if storage_type.lower() == "s3":
        try:
            return S3StorageClient()
        except Exception as e:
            logger.error(f"✗ 無法初始化 S3 客戶端: {e}")
            logger.warning("⚠️ 將回退到本地儲存模式")
            return None
    else:
        logger.info("ℹ️ 使用本地儲存模式")
        return None


# ==========================================
# 便捷函式
# ==========================================

def upload_to_s3(
    file_path: Union[str, Path],
    object_key: str,
    storage_client: S3StorageClient = None
) -> bool:
    """
    便捷函式：上傳檔案到 S3
    
    Args:
        file_path: 本地檔案路徑
        object_key: S3 對象鍵
        storage_client: S3StorageClient 實例 (可選)
    
    Returns:
        上傳成功返回 True，失敗返回 False
    """
    if storage_client is None:
        storage_client = get_storage_client()
    
    if storage_client is None:
        logger.warning("⚠️ S3 客戶端未初始化，跳過上傳")
        return False
    
    return storage_client.upload_file(file_path, object_key)


def get_presigned_url_from_s3(
    object_key: str,
    storage_client: S3StorageClient = None,
    expiration: int = 3600
) -> Optional[str]:
    """
    便捷函式：生成預簽名 URL
    
    Args:
        object_key: S3 對象鍵
        storage_client: S3StorageClient 實例 (可選)
        expiration: 過期時間 (秒)
    
    Returns:
        預簽名 URL，失敗返回 None
    """
    if storage_client is None:
        storage_client = get_storage_client()
    
    if storage_client is None:
        logger.warning("⚠️ S3 客戶端未初始化")
        return None
    
    return storage_client.get_presigned_url(object_key, expiration)


if __name__ == "__main__":
    # 測試代碼
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # 初始化客戶端
    client = S3StorageClient(
        endpoint_url="http://localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket_name="test-bucket"
    )
    
    # 測試上傳
    test_content = b"Hello, MinIO!"
    client.upload_bytes(test_content, "test/hello.txt", "text/plain")
    
    # 測試生成預簽名 URL
    url = client.get_presigned_url("test/hello.txt")
    print(f"預簽名 URL: {url}")
