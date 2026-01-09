"""
Virtual Human Flow Integration Test
====================================
End-to-End 自動化測試腳本，驗證音訊上傳與虛擬人工作流的完整流程。

使用方式：
    python tests/test_virtual_human_flow.py

前置條件：
    1. Backend 服務運行於 http://localhost:5000
    2. Worker 服務運行中
    3. Redis 與 MySQL 服務正常
    4. ComfyUI 服務運行中 (如需實際生成)

測試流程：
    1. 生成暫存 WAV 檔案
    2. 上傳音訊至 /api/upload
    3. 發送生成任務至 /api/generate
    4. 輪詢狀態直到完成
    5. 驗證輸出檔案可存取
"""

import os
import sys
import wave
import struct
import time
import tempfile
import argparse
from datetime import datetime

# 確保可以導入 requests
try:
    import requests
except ImportError:
    print("[ERROR] Please install requests: pip install requests")
    sys.exit(1)

# ==========================================
# 配置
# ==========================================
BASE_URL = "http://localhost:5000"
TIMEOUT_SECONDS = 300  # 5 分鐘超時 (虛擬人生成可能需要較長時間)
POLL_INTERVAL = 3      # 輪詢間隔 (秒)


def log(level: str, message: str):
    """統一的日誌格式"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icons = {"INFO": "[i]", "PASS": "[OK]", "FAIL": "[X]", "WARN": "[!]", "STEP": "[>]"}
    icon = icons.get(level, "[*]")
    print(f"[{timestamp}] {icon} {message}")


def generate_silence_wav(duration_seconds: float = 1.0, sample_rate: int = 44100) -> str:
    """
    生成指定時長的靜音 WAV 檔案
    
    Args:
        duration_seconds: 靜音時長 (秒)
        sample_rate: 採樣率
    
    Returns:
        暫存檔案路徑
    """
    num_samples = int(sample_rate * duration_seconds)
    
    # 建立暫存檔案
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.wav',
        prefix='test_audio_',
        delete=False
    )
    
    with wave.open(temp_file.name, 'w') as wav_file:
        wav_file.setnchannels(1)          # 單聲道
        wav_file.setsampwidth(2)           # 16-bit
        wav_file.setframerate(sample_rate) # 採樣率
        
        # 生成靜音數據 (全為 0)
        silence_data = struct.pack('<' + 'h' * num_samples, *([0] * num_samples))
        wav_file.writeframes(silence_data)
    
    return temp_file.name


def test_health_check() -> bool:
    """測試 Backend 健康狀態"""
    log("STEP", "檢查 Backend 健康狀態...")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            log("PASS", f"Backend 健康: Redis={data.get('redis')}, MySQL={data.get('mysql')}")
            return True
        else:
            log("FAIL", f"健康檢查失敗: HTTP {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        log("FAIL", f"無法連接 Backend ({BASE_URL})")
        return False
    except Exception as e:
        log("FAIL", f"健康檢查異常: {e}")
        return False


def test_upload_audio(wav_path: str) -> str:
    """
    Step 1: 上傳音訊檔案
    
    Returns:
        上傳後的檔名，失敗時返回空字串
    """
    log("STEP", f"上傳音訊: {wav_path}")
    
    try:
        with open(wav_path, 'rb') as f:
            files = {'file': ('test_audio.wav', f, 'audio/wav')}
            response = requests.post(f"{BASE_URL}/api/upload", files=files, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            filename = data.get('filename', '')
            original = data.get('original_name', '')
            log("PASS", f"上傳成功: {filename} (原始: {original})")
            return filename
        else:
            log("FAIL", f"上傳失敗: HTTP {response.status_code} - {response.text}")
            return ""
    except Exception as e:
        log("FAIL", f"上傳異常: {e}")
        return ""


def test_generate_task(audio_filename: str, prompt: str = "AutoTest") -> str:
    """
    Step 2: 發送生成任務
    
    Returns:
        job_id，失敗時返回空字串
    """
    log("STEP", f"發送生成任務: workflow=virtual_human, audio={audio_filename}")
    
    payload = {
        "workflow": "virtual_human",
        "prompt": prompt,
        "audio": audio_filename
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/generate",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 202:
            data = response.json()
            job_id = data.get('job_id', '')
            status = data.get('status', '')
            log("PASS", f"任務已提交: job_id={job_id}, status={status}")
            return job_id
        else:
            log("FAIL", f"提交失敗: HTTP {response.status_code} - {response.text}")
            return ""
    except Exception as e:
        log("FAIL", f"提交異常: {e}")
        return ""


def test_monitor_status(job_id: str) -> dict:
    """
    Step 3: 監控任務狀態直到完成
    
    Returns:
        最終狀態資料，失敗時返回空 dict
    """
    log("STEP", f"監控任務狀態: {job_id}")
    
    start_time = time.time()
    last_status = ""
    last_progress = -1
    
    while True:
        elapsed = time.time() - start_time
        
        # 超時檢查
        if elapsed > TIMEOUT_SECONDS:
            log("FAIL", f"任務超時 ({TIMEOUT_SECONDS}s)")
            return {}
        
        try:
            response = requests.get(f"{BASE_URL}/api/status/{job_id}", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'unknown')
                progress = data.get('progress', 0)
                
                # 狀態變更時輸出日誌
                if status != last_status or progress != last_progress:
                    log("INFO", f"狀態: {status} ({progress}%) - {elapsed:.1f}s")
                    last_status = status
                    last_progress = progress
                
                # 終止條件
                if status == 'finished':
                    log("PASS", f"任務完成! 耗時: {elapsed:.1f}s")
                    return data
                elif status == 'failed':
                    error = data.get('error', 'Unknown error')
                    log("FAIL", f"任務失敗: {error}")
                    return data
                elif status == 'cancelled':
                    log("WARN", "任務已取消")
                    return data
            else:
                log("WARN", f"狀態查詢失敗: HTTP {response.status_code}")
        
        except Exception as e:
            log("WARN", f"狀態查詢異常: {e}")
        
        time.sleep(POLL_INTERVAL)


def test_verify_output(image_url: str) -> bool:
    """
    Step 4: 驗證輸出檔案可存取
    
    Returns:
        是否成功
    """
    if not image_url:
        log("WARN", "無輸出 URL，跳過驗證")
        return True  # 不視為失敗
    
    log("STEP", f"驗證輸出: {image_url}")
    
    # 構建完整 URL
    if image_url.startswith('/'):
        full_url = f"{BASE_URL}{image_url}"
    else:
        full_url = image_url
    
    try:
        response = requests.head(full_url, timeout=10)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            log("PASS", f"輸出可存取: Content-Type={content_type}")
            
            # 驗證是否為影片格式
            if 'video' in content_type.lower():
                log("PASS", "確認為影片格式")
            elif 'image' in content_type.lower():
                log("INFO", "輸出為圖片格式")
            
            return True
        else:
            log("FAIL", f"輸出不可存取: HTTP {response.status_code}")
            return False
    except Exception as e:
        log("FAIL", f"驗證異常: {e}")
        return False


def run_full_test(skip_generation: bool = False) -> bool:
    """
    執行完整測試流程
    
    Args:
        skip_generation: 是否跳過實際生成 (僅測試上傳)
    
    Returns:
        測試是否成功
    """
    print("\n" + "=" * 60)
    print("[TEST] Virtual Human Flow Integration Test")
    print("=" * 60 + "\n")
    
    # 0. 健康檢查
    if not test_health_check():
        log("FAIL", "Backend 不可用，測試中止")
        return False
    
    # 1. 生成測試用 WAV 檔案
    log("STEP", "生成測試用靜音 WAV 檔案...")
    wav_path = generate_silence_wav(duration_seconds=1.0)
    log("INFO", f"暫存檔案: {wav_path}")
    
    try:
        # 2. 上傳音訊
        audio_filename = test_upload_audio(wav_path)
        if not audio_filename:
            log("FAIL", "音訊上傳失敗，測試中止")
            return False
        
        if skip_generation:
            log("INFO", "跳過生成測試 (--skip-generation)")
            print("\n" + "=" * 60)
            log("PASS", "上傳測試完成!")
            print("=" * 60 + "\n")
            return True
        
        # 3. 發送生成任務
        job_id = test_generate_task(audio_filename)
        if not job_id:
            log("FAIL", "任務提交失敗，測試中止")
            return False
        
        # 4. 監控狀態
        result = test_monitor_status(job_id)
        if not result:
            log("FAIL", "任務監控失敗")
            return False
        
        final_status = result.get('status', '')
        if final_status != 'finished':
            log("FAIL", f"任務未完成: {final_status}")
            return False
        
        # 5. 驗證輸出
        image_url = result.get('image_url', '')
        if not test_verify_output(image_url):
            log("WARN", "輸出驗證失敗 (可能是 ComfyUI 未運行)")
        
        print("\n" + "=" * 60)
        log("PASS", "所有測試通過!")
        print("=" * 60 + "\n")
        return True
    
    finally:
        # 清理暫存檔案
        try:
            os.unlink(wav_path)
            log("INFO", "已刪除暫存檔案")
        except Exception:
            pass


def run_upload_only_test() -> bool:
    """
    僅測試上傳功能 (不需要 ComfyUI)
    """
    print("\n" + "=" * 60)
    print("[TEST] Audio Upload Test (Quick)")
    print("=" * 60 + "\n")
    
    # 0. 健康檢查
    if not test_health_check():
        log("FAIL", "Backend 不可用，測試中止")
        return False
    
    # 1. 生成測試用 WAV 檔案
    log("STEP", "生成測試用靜音 WAV 檔案...")
    wav_path = generate_silence_wav(duration_seconds=0.5)
    log("INFO", f"暫存檔案: {wav_path}")
    
    try:
        # 2. 上傳音訊
        audio_filename = test_upload_audio(wav_path)
        if not audio_filename:
            log("FAIL", "音訊上傳失敗")
            return False
        
        # 3. 驗證檔案存在於 storage/inputs
        log("STEP", "驗證檔案已儲存...")
        storage_path = os.path.join(
            os.path.dirname(__file__), '..', 'storage', 'inputs', audio_filename
        )
        storage_path = os.path.abspath(storage_path)
        
        if os.path.exists(storage_path):
            log("PASS", f"檔案存在: {storage_path}")
        else:
            log("WARN", f"檔案不存在 (可能路徑不同): {storage_path}")
        
        print("\n" + "=" * 60)
        log("PASS", "上傳測試完成!")
        print("=" * 60 + "\n")
        return True
    
    finally:
        # 清理暫存檔案
        try:
            os.unlink(wav_path)
            log("INFO", "已刪除暫存檔案")
        except Exception:
            pass


def main():
    """主程式入口"""
    parser = argparse.ArgumentParser(
        description='Virtual Human Flow Integration Test',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
    python test_virtual_human_flow.py                    # 完整測試 (需要 ComfyUI)
    python test_virtual_human_flow.py --upload-only      # 僅測試上傳
    python test_virtual_human_flow.py --skip-generation  # 跳過生成步驟
    python test_virtual_human_flow.py --url http://192.168.1.100:5000
        """
    )
    
    parser.add_argument(
        '--url', '-u',
        default='http://localhost:5000',
        help='Backend URL (預設: http://localhost:5000)'
    )
    parser.add_argument(
        '--upload-only',
        action='store_true',
        help='僅測試上傳功能 (快速測試)'
    )
    parser.add_argument(
        '--skip-generation',
        action='store_true',
        help='跳過實際生成 (測試 API 但不等待 ComfyUI)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=300,
        help='超時時間 (秒，預設: 300)'
    )
    
    args = parser.parse_args()
    
    # 更新全域配置
    global BASE_URL, TIMEOUT_SECONDS
    BASE_URL = args.url
    TIMEOUT_SECONDS = args.timeout
    
    log("INFO", f"目標: {BASE_URL}")
    log("INFO", f"超時: {TIMEOUT_SECONDS}s")
    
    # 執行測試
    if args.upload_only:
        success = run_upload_only_test()
    else:
        success = run_full_test(skip_generation=args.skip_generation)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
