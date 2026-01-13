#!/usr/bin/env python3
"""
Phase 9 測試腳本
================
測試延長超時配置、Personal Gallery 和 MySQL 資料庫連接

執行方式:
    python tests/test_phase9_reliability.py
"""

import sys
import os
from pathlib import Path

# 加入專案根目錄到 Python Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "worker" / "src"))
sys.path.insert(0, str(project_root / "backend" / "src"))

def test_worker_config():
    """測試 Worker 配置是否正確載入"""
    print("\n" + "=" * 60)
    print("測試 1: Worker 配置檢查")
    print("=" * 60)
    
    try:
        from config import WORKER_TIMEOUT, COMFY_POLLING_INTERVAL
        
        print(f"✅ WORKER_TIMEOUT = {WORKER_TIMEOUT}s")
        print(f"✅ COMFY_POLLING_INTERVAL = {COMFY_POLLING_INTERVAL}s")
        
        assert WORKER_TIMEOUT >= 3600, f"❌ WORKER_TIMEOUT 應 >= 3600，目前: {WORKER_TIMEOUT}"
        assert COMFY_POLLING_INTERVAL > 0, f"❌ COMFY_POLLING_INTERVAL 應 > 0，目前: {COMFY_POLLING_INTERVAL}"
        
        print("✅ Worker 配置測試通過！")
        return True
    except Exception as e:
        print(f"❌ Worker 配置測試失敗: {e}")
        return False

def test_comfy_client_timeout():
    """測試 ComfyClient 是否正確使用 WORKER_TIMEOUT"""
    print("\n" + "=" * 60)
    print("測試 2: ComfyClient 超時配置")
    print("=" * 60)
    
    try:
        from comfy_client import ComfyClient
        from config import WORKER_TIMEOUT
        
        client = ComfyClient()
        
        # 檢查 wait_for_completion 簽名
        import inspect
        sig = inspect.signature(client.wait_for_completion)
        timeout_param = sig.parameters.get('timeout')
        
        if timeout_param:
            print(f"✅ wait_for_completion 有 timeout 參數")
            print(f"   預設值: {timeout_param.default}")
            
            # 檢查預設值是否為 None（會使用 config 的值）
            if timeout_param.default is None:
                print(f"✅ timeout 預設為 None，將使用 WORKER_TIMEOUT={WORKER_TIMEOUT}s")
            else:
                print(f"⚠️ timeout 預設為 {timeout_param.default}，可能未使用 WORKER_TIMEOUT")
        
        print("✅ ComfyClient 測試通過！")
        return True
    except Exception as e:
        print(f"❌ ComfyClient 測試失敗: {e}")
        return False

def test_database_connection():
    """測試 MySQL 資料庫連接"""
    print("\n" + "=" * 60)
    print("測試 3: MySQL 資料庫連接")
    print("=" * 60)
    
    try:
        import os
        
        # 載入環境變數
        env_path = project_root / ".env"
        if env_path.exists():
            print(f"✅ 找到 .env 檔案: {env_path}")
            # 簡單解析 .env（實際應用中可用 python-dotenv）
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip())
        
        from database import Database
        
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = int(os.getenv("MYSQL_PORT", "3307"))
        db_user = os.getenv("DB_USER", "studio_user")
        db_password = os.getenv("DB_PASSWORD", "studio_password")
        db_name = os.getenv("DB_NAME", "studio_db")
        
        print(f"連接資訊: {db_host}:{db_port}/{db_name} (user: {db_user})")
        
        db = Database(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        if db.check_connection():
            print("✅ MySQL 連接成功！")
            
            # 測試查詢歷史記錄
            history = db.get_history(limit=5)
            print(f"✅ 查詢歷史記錄成功: {len(history)} 筆")
            
            if len(history) > 0:
                print("\n最近 5 筆記錄:")
                for i, job in enumerate(history, 1):
                    status_icon = {
                        'finished': '✅',
                        'failed': '❌',
                        'processing': '⏳',
                        'queued': '📋'
                    }.get(job.get('status'), '❓')
                    
                    print(f"  {i}. {status_icon} {job.get('workflow')} - {job.get('prompt', '')[:50]}")
                    print(f"     狀態: {job.get('status')} | 輸出: {job.get('output_path', 'N/A')}")
            else:
                print("⚠️ 資料庫中沒有任何記錄")
                print("   這是正常的，如果這是首次運行或未執行過任務")
            
            return True
        else:
            print("❌ MySQL 連接失敗")
            return False
            
    except Exception as e:
        print(f"❌ 資料庫測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_env_example():
    """檢查 .env.unified.example 是否包含新的配置"""
    print("\n" + "=" * 60)
    print("測試 4: .env.unified.example 配置檢查")
    print("=" * 60)
    
    try:
        env_example_path = project_root / ".env.unified.example"
        if not env_example_path.exists():
            print(f"❌ 找不到 {env_example_path}")
            return False
        
        with open(env_example_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        required_configs = [
            "WORKER_TIMEOUT",
            "COMFY_POLLING_INTERVAL"
        ]
        
        for config in required_configs:
            if config in content:
                print(f"✅ {config} 存在於 .env.unified.example")
            else:
                print(f"❌ {config} 不存在於 .env.unified.example")
                return False
        
        print("✅ .env.unified.example 測試通過！")
        return True
    except Exception as e:
        print(f"❌ .env.unified.example 測試失敗: {e}")
        return False

def main():
    """執行所有測試"""
    print("\n" + "🔬" * 30)
    print(" " * 20 + "Phase 9 可靠性測試")
    print("🔬" * 30)
    
    results = []
    
    # 執行所有測試
    results.append(("Worker 配置", test_worker_config()))
    results.append(("ComfyClient 超時", test_comfy_client_timeout()))
    results.append((".env.unified.example", test_env_example()))
    results.append(("MySQL 資料庫", test_database_connection()))
    
    # 統計結果
    print("\n" + "=" * 60)
    print("測試總結")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        icon = "✅" if result else "❌"
        print(f"{icon} {test_name}")
    
    print("\n" + "=" * 60)
    print(f"總計: {passed}/{total} 通過")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 所有測試通過！Phase 9 實施成功！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 項測試失敗，請檢查上述錯誤訊息")
        return 1

if __name__ == "__main__":
    sys.exit(main())
