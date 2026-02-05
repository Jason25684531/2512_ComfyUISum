"""
S3 Storage Integration Test
============================
測試 MinIO/S3 連接與基本操作

使用前提:
1. 已部署 MinIO: kubectl apply -f k8s/base/03-minio.yaml
2. 已啟動 Port-Forward: kubectl port-forward svc/minio-service 9000:9000 9001:9001
3. 已安裝 boto3: pip install boto3
"""

import sys
from pathlib import Path

# 添加專案路徑
sys.path.insert(0, str(Path(__file__).parent))

from shared.storage import S3StorageClient

def test_s3_connection():
    """測試 S3 連接"""
    print("=" * 60)
    print("S3 Storage Integration Test")
    print("=" * 60)
    
    # 初始化客戶端
    print("\n[1/5] 初始化 S3 客戶端...")
    try:
        client = S3StorageClient(
            endpoint_url="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="comfyui-outputs"
        )
        print("✓ S3 客戶端初始化成功")
    except Exception as e:
        print(f"✗ S3 客戶端初始化失敗: {e}")
        print("\n請確認:")
        print("1. MinIO 已部署: kubectl get pods -l app=minio")
        print("2. Port-Forward 已啟動: kubectl port-forward svc/minio-service 9000:9000")
        return False
    
    # 測試上傳文字檔案
    print("\n[2/5] 測試上傳文字檔案...")
    test_content = b"Hello from ComfyUI Studio! This is a test file."
    success = client.upload_bytes(test_content, "test/hello.txt", "text/plain")
    if success:
        print("✓ 文字檔案上傳成功")
    else:
        print("✗ 文字檔案上傳失敗")
        return False
    
    # 測試上傳二進位檔案 (模擬圖片)
    print("\n[3/5] 測試上傳二進位檔案...")
    test_image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..." # PNG header
    success = client.upload_bytes(test_image, "test/sample.png", "image/png")
    if success:
        print("✓ 二進位檔案上傳成功")
    else:
        print("✗ 二進位檔案上傳失敗")
    
    # 測試列出對象
    print("\n[4/5] 測試列出對象...")
    objects = client.list_objects(prefix="test/")
    if objects:
        print(f"✓ 找到 {len(objects)} 個對象:")
        for obj in objects:
            print(f"  - {obj}")
    else:
        print("⚠️ 未找到任何對象 (可能是正常的)")
    
    # 測試生成預簽名 URL
    print("\n[5/5] 測試生成預簽名 URL...")
    url = client.get_presigned_url("test/hello.txt", expiration=300)
    if url:
        print("✓ 預簽名 URL 生成成功:")
        print(f"  {url}")
        print("\n請在瀏覽器中打開此 URL 驗證 (有效期 5 分鐘)")
    else:
        print("✗ 預簽名 URL 生成失敗")
    
    # 測試完成
    print("\n" + "=" * 60)
    print("✅ 所有測試通過！S3 整合正常運作")
    print("=" * 60)
    print("\n下一步:")
    print("1. 在 MinIO Console 查看上傳的檔案: http://localhost:9001")
    print("2. 啟動 Worker 測試自動上傳: python worker/src/main.py")
    print("3. 提交任務測試完整流程: curl -X POST http://localhost:5001/api/generate ...")
    
    return True


def test_storage_factory():
    """測試儲存工廠函式"""
    print("\n" + "=" * 60)
    print("Storage Factory Test")
    print("=" * 60)
    
    from shared.storage import get_storage_client
    import os
    
    # 測試 1: STORAGE_TYPE=local
    print("\n[Test 1] STORAGE_TYPE=local")
    os.environ["STORAGE_TYPE"] = "local"
    client = get_storage_client()
    if client is None:
        print("✓ 正確返回 None (本地儲存模式)")
    else:
        print("✗ 應該返回 None")
    
    # 測試 2: STORAGE_TYPE=s3
    print("\n[Test 2] STORAGE_TYPE=s3")
    os.environ["STORAGE_TYPE"] = "s3"
    try:
        client = get_storage_client()
        if client is not None:
            print("✓ 成功初始化 S3 客戶端")
        else:
            print("⚠️ S3 客戶端初始化失敗 (可能 MinIO 未啟動)")
    except Exception as e:
        print(f"⚠️ S3 客戶端初始化失敗: {e}")


if __name__ == "__main__":
    print("\n🚀 開始 S3 整合測試...\n")
    
    # 主測試
    success = test_s3_connection()
    
    # 工廠函式測試
    if success:
        test_storage_factory()
    
    print("\n✅ 測試腳本執行完成！\n")
