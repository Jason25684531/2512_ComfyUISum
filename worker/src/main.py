"""
Worker Main Loop
=================
從 Redis 佇列取得任務，解析 workflow，送交 ComfyUI 執行。
"""

import os
import sys
import json
import time
import redis
import base64
import uuid
from pathlib import Path
from datetime import datetime, timedelta

# 自動載入 .env 檔案
def load_env():
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"[Worker] 已載入 .env 檔案")

load_env()

from json_parser import parse_workflow
from comfy_client import ComfyClient
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
    COMFYUI_INPUT_DIR, JOB_QUEUE, TEMP_FILE_MAX_AGE_HOURS,
    JOB_STATUS_EXPIRE_SECONDS, print_config
)


def get_redis_client() -> redis.Redis:
    """
    建立 Redis 連接
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True
    )


def save_base64_image(base64_data: str, job_id: str, field_name: str) -> str:
    """
    將 base64 圖片保存到 ComfyUI input 目錄
    
    Args:
        base64_data: base64 編碼的圖片數據 (可能包含 data:image/xxx;base64, 前綴)
        job_id: 任務 ID
        field_name: 欄位名稱 (source, target, input 等)
    
    Returns:
        保存的檔名 (不含路徑)
    """
    # 移除 data:image/xxx;base64, 前綴
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]
    
    # 解碼 base64
    try:
        image_bytes = base64.b64decode(base64_data)
    except Exception as e:
        raise ValueError(f"Base64 解碼失敗: {e}")
    
    # 生成唯一檔名
    filename = f"upload_{job_id}_{field_name}.png"
    filepath = Path(COMFYUI_INPUT_DIR) / filename
    
    # 確保目錄存在
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # 寫入檔案
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    
    print(f"[Worker] 💾 已保存圖片: {filename} ({len(image_bytes)} bytes)")
    return filename


def cleanup_old_temp_files():
    """
    清理超過指定時間的暫存圖片檔案
    """
    input_dir = Path(COMFYUI_INPUT_DIR)
    if not input_dir.exists():
        return
    
    cutoff_time = datetime.now() - timedelta(hours=TEMP_FILE_MAX_AGE_HOURS)
    deleted_count = 0
    
    for filepath in input_dir.glob("upload_*.png"):
        try:
            file_mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if file_mtime < cutoff_time:
                filepath.unlink()
                deleted_count += 1
        except Exception as e:
            print(f"[Worker] ⚠️ 無法刪除 {filepath}: {e}")
    
    if deleted_count > 0:
        print(f"[Worker] 🗑️ 已清理 {deleted_count} 個過期暫存檔案")


def cleanup_old_output_files():
    """
    清理 storage/outputs 中超過 30 天的圖片檔案
    """
    from config import STORAGE_OUTPUT_DIR
    
    if not STORAGE_OUTPUT_DIR.exists():
        return
    
    cutoff_time = datetime.now() - timedelta(days=30)
    deleted_count = 0
    total_size = 0
    
    for filepath in STORAGE_OUTPUT_DIR.glob("*"):
        if not filepath.is_file():
            continue
        
        try:
            file_mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if file_mtime < cutoff_time:
                file_size = filepath.stat().st_size
                filepath.unlink()
                deleted_count += 1
                total_size += file_size
        except Exception as e:
            print(f"[Worker] ⚠️ 無法刪除 {filepath}: {e}")
    
    if deleted_count > 0:
        size_mb = total_size / (1024 * 1024)
        print(f"[Worker] 🗑️ 已清理 {deleted_count} 個超過 30 天的輸出圖片 (釋放 {size_mb:.2f} MB)")


def update_job_status(
    r: redis.Redis,
    job_id: str,
    status: str,
    progress: int = 0,
    image_url: str = None,
    error: str = None
):
    """
    更新任務狀態到 Redis
    """
    status_key = f"job:status:{job_id}"
    data = {
        "status": status,
        "progress": progress
    }
    
    if image_url:
        data["image_url"] = image_url
    if error:
        data["error"] = error
    
    r.hset(status_key, mapping=data)
    r.expire(status_key, JOB_STATUS_EXPIRE_SECONDS)
    print(f"[Worker] 更新狀態: {job_id} -> {status}")


def process_job(r: redis.Redis, client: ComfyClient, job_data: dict):
    """
    處理單個任務
    
    job_data 格式:
    {
        "job_id": "uuid",
        "prompt": "描述文字",
        "seed": -1,
        "workflow": "text_to_image",
        "model": "turbo_fp8",
        "aspect_ratio": "1:1",
        "batch_size": 1,
        "images": {
            "source": "base64...",
            "target": "base64..."
        }
    }
    """
    job_id = job_data.get("job_id", "unknown")
    
    print(f"\n{'='*50}")
    print(f"[Worker] 開始處理任務: {job_id}")
    print(f"{'='*50}")
    
    try:
        # 1. 更新狀態為處理中
        update_job_status(r, job_id, "processing", progress=10)
        
        # 2. 提取參數
        workflow_name = job_data.get("workflow", "text_to_image")
        prompt = job_data.get("prompt", "")
        seed = job_data.get("seed", -1)
        aspect_ratio = job_data.get("aspect_ratio", "1:1")
        model = job_data.get("model", "turbo_fp8")
        batch_size = job_data.get("batch_size", 1)
        images = job_data.get("images", {})  # base64 圖片字典
        
        print(f"[Worker] Workflow: {workflow_name}")
        print(f"[Worker] Prompt: {prompt[:50] if prompt else '(empty)'}...")
        print(f"[Worker] Aspect Ratio: {aspect_ratio}")
        print(f"[Worker] Model: {model}")
        print(f"[Worker] Batch Size: {batch_size}")
        print(f"[Worker] Images: {list(images.keys()) if images else 'None'}")
        
        # 3. 處理上傳的圖片 (base64 -> 檔案)
        update_job_status(r, job_id, "processing", progress=15)
        
        image_files = {}  # 儲存檔名映射 {"source": "upload_xxx_source.png"}
        if images:
            print(f"[Worker] 📷 開始處理 {len(images)} 張圖片...")
            for field_name, base64_data in images.items():
                if base64_data:
                    try:
                        filename = save_base64_image(base64_data, job_id, field_name)
                        image_files[field_name] = filename
                    except Exception as e:
                        print(f"[Worker] ⚠️ 處理圖片 {field_name} 失敗: {e}")
        
        # 4. 解析 workflow (包含圖片注入)
        update_job_status(r, job_id, "processing", progress=20)
        
        workflow = parse_workflow(
            workflow_name=workflow_name,
            prompt=prompt,
            seed=seed,
            aspect_ratio=aspect_ratio,
            model=model,
            batch_size=batch_size,
            image_files=image_files  # 傳入圖片檔名映射
        )
        
        print(f"[Worker] Workflow 解析完成")
        
        # 5. 檢查 ComfyUI 連接
        if not client.check_connection():
            raise Exception("無法連接 ComfyUI，請確認是否已啟動")
        
        # 6. 提交任務到 ComfyUI
        update_job_status(r, job_id, "processing", progress=30)
        
        prompt_id = client.queue_prompt(workflow)
        if not prompt_id:
            raise Exception("任務提交失敗")
        
        print(f"[Worker] 任務已提交，prompt_id: {prompt_id}")
        
        # 7. 定義進度更新回調函數
        def on_progress(progress):
            # 檢查任務是否被取消
            status_key = f"job:status:{job_id}"
            current_status = r.hget(status_key, "status")
            if current_status == "cancelled":
                print(f"[Worker] 🛑 任務已被取消，發送中斷指令...")
                client.interrupt()
                raise Exception("Task cancelled by user")
            
            # 將進度從 30% 開始映射到 30-95%
            mapped_progress = 30 + int(progress * 0.65)
            update_job_status(r, job_id, "processing", progress=mapped_progress)

        # 8. 等待 ComfyUI 執行完成
        result = client.wait_for_completion(
            prompt_id=prompt_id,
            timeout=600,
            on_progress=on_progress
        )

        # 9. 根據執行結果處理輸出
        if result.get("success"):
            images = result.get("images", [])
            if images:
                print(f"[Worker] 📷 收到 {len(images)} 張輸出圖片")
                
                # 優先選擇有 subfolder 的圖片（正式輸出），否則使用第一張
                selected_image = None
                for img in images:
                    if img.get("subfolder"):
                        selected_image = img
                        print(f"[Worker] 選擇有子目錄的圖片: {img.get('filename')} (subfolder: {img.get('subfolder')})")
                        break
                
                if not selected_image:
                    selected_image = images[0]
                    print(f"[Worker] 使用第一張圖片: {selected_image.get('filename')}")
                
                # 嘗試複製選中的圖片
                new_filename = client.copy_output_image(
                    filename=selected_image.get("filename"),
                    subfolder=selected_image.get("subfolder", ""),
                    job_id=job_id
                )
                
                # 如果選中的圖片複製失敗，嘗試其他圖片
                if not new_filename and len(images) > 1:
                    print(f"[Worker] ⚠️ 第一選擇失敗，嘗試其他圖片...")
                    for img in images:
                        if img == selected_image:
                            continue
                        new_filename = client.copy_output_image(
                            filename=img.get("filename"),
                            subfolder=img.get("subfolder", ""),
                            job_id=job_id
                        )
                        if new_filename:
                            print(f"[Worker] ✓ 成功複製備選圖片: {img.get('filename')}")
                            break
                
                if new_filename:
                    image_url = f"/outputs/{new_filename}"
                    update_job_status(r, job_id, "finished", progress=100, image_url=image_url)
                    print(f"[Worker] ✅ 任務完成，輸出: {image_url}")
                else:
                    update_job_status(r, job_id, "finished", progress=100)
                    print(f"[Worker] ⚠️ 任務完成，但所有輸出圖片都無法複製")
            else:
                update_job_status(r, job_id, "finished", progress=100)
                print(f"[Worker] ✅ 任務完成，但沒有輸出圖片")
        else:
            error = result.get("error", "未知錯誤")
            update_job_status(r, job_id, "failed", error=error)
            print(f"[Worker] ❌ 任務失敗: {error}")
            
    except Exception as e:
        error_msg = str(e)
        print(f"[Worker] ❌ 處理錯誤: {error_msg}")
        update_job_status(r, job_id, "failed", progress=0, error=error_msg)


def main():
    """
    Worker 主迴圈
    """
    print("="*50)
    print("🚀 Worker 啟動中...")
    print("="*50)
    
    # 1. 連接 Redis
    try:
        r = get_redis_client()
        r.ping()
        print(f"[Worker] ✅ Redis 連接成功 ({REDIS_HOST}:{REDIS_PORT})")
    except Exception as e:
        print(f"[Worker] ❌ Redis 連接失敗: {e}")
        sys.exit(1)
    
    # 2. 初始化 ComfyUI 客戶端
    client = ComfyClient()
    
    # 3. 檢查 ComfyUI 連接
    if client.check_connection():
        print("[Worker] ✅ ComfyUI 連接成功")
    else:
        print("[Worker] ⚠️ ComfyUI 尚未啟動，將持續等待...")
    
    # 4. 清理舊的暫存檔案
    print("[Worker] 🗑️ 清理過期暫存檔案...")
    cleanup_old_temp_files()
    
    # 5. 清理超過 30 天的輸出圖片
    print("[Worker] 🗑️ 清理超過 30 天的輸出圖片...")
    cleanup_old_output_files()
    
    # 6. 開始處理佇列
    print(f"\n[Worker] 監聽佇列: {JOB_QUEUE}")
    print(f"[Worker] ComfyUI Input 目錄: {COMFYUI_INPUT_DIR}")
    print("[Worker] 等待任務中...\n")
    
    last_cleanup_time = time.time()
    CLEANUP_INTERVAL = 3600  # 每小時清理一次
    
    while True:
        try:
            # 定期清理暫存檔案和輸出圖片
            if time.time() - last_cleanup_time > CLEANUP_INTERVAL:
                cleanup_old_temp_files()
                cleanup_old_output_files()
                last_cleanup_time = time.time()
            
            # BLPOP: 阻塞式取出任務 (超時 5 秒)
            result = r.blpop(JOB_QUEUE, timeout=5)
            
            if result:
                queue_name, job_json = result
                
                try:
                    job_data = json.loads(job_json)
                    process_job(r, client, job_data)
                except json.JSONDecodeError as e:
                    print(f"[Worker] JSON 解析錯誤: {e}")
            
        except redis.ConnectionError as e:
            print(f"[Worker] Redis 連接中斷，5 秒後重試: {e}")
            time.sleep(5)
            try:
                r = get_redis_client()
            except:
                pass
                
        except KeyboardInterrupt:
            print("\n[Worker] 收到中斷信號，正在關閉...")
            break
            
        except Exception as e:
            print(f"[Worker] 未預期錯誤: {e}")
            time.sleep(1)
    
    print("[Worker] 已關閉")


if __name__ == '__main__':
    main()
