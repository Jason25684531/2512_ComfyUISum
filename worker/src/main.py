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
import logging
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timedelta

# ============================================
# 添加 shared 模組路徑
# ============================================
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 配置日誌系統 (優先設置)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 確保 logs 目錄存在
log_dir = Path(__file__).parent.parent.parent / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / 'worker.log'

# 配置 RotatingFileHandler (5MB, 保留 3 份)
file_handler = RotatingFileHandler(
    str(log_file),
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# 配置控制台輸出
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

# 配置 root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("Worker 日誌系統已啟動")
logger.info(f"日誌檔案位置: {log_file}")
logger.info("=" * 60)

# 使用共用的 load_env
from shared.utils import load_env
load_env()

from json_parser import parse_workflow
from comfy_client import ComfyClient
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,
    COMFYUI_INPUT_DIR, JOB_QUEUE, TEMP_FILE_MAX_AGE_HOURS,
    JOB_STATUS_EXPIRE_SECONDS, STORAGE_INPUT_DIR, print_config,
    WORKER_TIMEOUT
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
        保存的檔名 (不含路徑，用於 ComfyUI 相對路徑參考)
    """
    import io
    from PIL import Image
    
    # 移除 data:image/xxx;base64, 前綴（更嚴格的處理）
    if isinstance(base64_data, str) and "," in base64_data:
        base64_data = base64_data.split(",", 1)[1].strip()
    
    # 解碼 base64
    try:
        image_bytes = base64.b64decode(base64_data)
    except Exception as e:
        raise ValueError(f"Base64 解碼失敗: {e}")
    
    # 始終轉換為真正的 PNG 格式（解決格式不匹配問題）
    # 原因：用戶上傳的圖片可能是 JPEG, AVIF, WebP 等格式，
    #       如果直接保存為 .png 副檔名但內容是其他格式，
    #       ComfyUI 的 LoadImage 節點可能無法正確識別
    try:
        img = Image.open(io.BytesIO(image_bytes))
        original_format = img.format
        logger.info(f"📷 原始圖片格式: {original_format}, 尺寸: {img.size}")
        
        # 轉換為 RGB（處理 RGBA 或其他色彩模式）
        if img.mode in ('RGBA', 'LA', 'P'):
            # 創建白色背景
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 保存為真正的 PNG 格式
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG', optimize=True)
        image_bytes = img_buffer.getvalue()
        logger.info(f"✅ 已轉換為 PNG 格式，大小: {len(image_bytes)} bytes")
        
    except Exception as e:
        raise ValueError(f"圖片格式轉換失敗: {e}")

    
    # 生成唯一檔名（只用檔名，不用絕對路徑）
    filename = f"upload_{job_id}_{field_name}.png"
    filepath = Path(COMFYUI_INPUT_DIR) / filename
    
    # 確保目錄存在
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # 寫入檔案
    try:
        with open(filepath, "wb") as f:
            f.write(image_bytes)
            f.flush()  # 確保寫入磁碟
            os.fsync(f.fileno())  # 強制同步到磁碟
        
        logger.info(f"💾 已保存圖片: {filename} ({len(image_bytes)} bytes) 至 {filepath}")
        
        # 驗證檔案是否可讀（確保 ComfyUI 能讀取）
        if not filepath.exists():
            raise FileNotFoundError(f"檔案寫入後無法找到: {filepath}")
        
        file_size = filepath.stat().st_size
        if file_size != len(image_bytes):
            raise IOError(f"檔案大小不符，預期 {len(image_bytes)} bytes，實際 {file_size} bytes")
        
        # 嘗試重新開啟檔案驗證可讀性
        try:
            from PIL import Image
            with Image.open(filepath) as test_img:
                test_img.verify()
            logger.info(f"✅ 檔案驗證成功: {filename}")
        except Exception as verify_err:
            logger.warning(f"⚠️ 檔案驗證警告: {verify_err}")
        
        # 添加短暫延遲，確保檔案系統完成所有 I/O 操作
        time.sleep(0.1)
        
    except Exception as e:
        logger.error(f"❌ 檔案寫入失敗: {e}")
        raise
    
    # 返回只有檔名（相對路徑），不返回絕對路徑
    return filename


def copy_audio_to_comfyui(audio_filename: str, job_id: str) -> str:
    """
    將音訊檔案從 storage/inputs 複製到 ComfyUI input 目錄
    
    Args:
        audio_filename: 上傳的音訊檔名 (如 audio_1ba6e2ba-e8a.mp3)
        job_id: 任務 ID (用於生成唯一檔名)
    
    Returns:
        複製後的檔名 (不含路徑)
    """
    import shutil
    
    # 來源檔案路徑
    source_path = Path(STORAGE_INPUT_DIR) / audio_filename
    
    if not source_path.exists():
        raise FileNotFoundError(f"找不到音訊檔案: {source_path}")
    
    # 保留原副檔名，生成新檔名
    file_ext = source_path.suffix.lower()
    new_filename = f"audio_{job_id}{file_ext}"
    dest_path = Path(COMFYUI_INPUT_DIR) / new_filename
    
    # 確保目錄存在
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 複製檔案
    shutil.copy2(source_path, dest_path)
    
    logger.info(f"🎵 已複製音訊: {audio_filename} -> {new_filename} ({source_path.stat().st_size} bytes)")
    return new_filename


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
            logger.warning(f"⚠️ 無法刪除 {filepath}: {e}")
    
    if deleted_count > 0:
        logger.info(f"🗑️ 已清理 {deleted_count} 個過期暫存檔案")


def cleanup_old_output_files(db_client=None):
    """
    清理 storage/outputs 中超過 30 天的圖片檔案
    並同步軟刪除資料庫記錄
    
    Args:
        db_client: Database 客戶端實例（用於同步軟刪除）
    """
    from config import STORAGE_OUTPUT_DIR
    
    if not STORAGE_OUTPUT_DIR.exists():
        return
    
    cutoff_time = datetime.now() - timedelta(days=30)
    deleted_count = 0
    total_size = 0
    db_synced = 0
    
    for filepath in STORAGE_OUTPUT_DIR.glob("*"):
        if not filepath.is_file():
            continue
        
        try:
            file_mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            if file_mtime < cutoff_time:
                file_size = filepath.stat().st_size
                filename = filepath.name
                
                # 刪除檔案
                filepath.unlink()
                deleted_count += 1
                total_size += file_size
                
                # 同步軟刪除資料庫記錄 (如果有資料庫連接)
                if db_client:
                    try:
                        if db_client.soft_delete_by_output_path(filename):
                            db_synced += 1
                    except Exception as db_err:
                        logger.warning(f"⚠️ 資料庫軟刪除失敗: {db_err}")
                
        except Exception as e:
            logger.warning(f"⚠️ 無法刪除 {filepath}: {e}")
    
    if deleted_count > 0:
        size_mb = total_size / (1024 * 1024)
        logger.info(f"🗑️ 已清理 {deleted_count} 個超過 30 天的輸出圖片 (釋放 {size_mb:.2f} MB)")
        if db_client and db_synced > 0:
            logger.info(f"📊 已同步軟刪除資料庫記錄: {db_synced} 筆")


def worker_heartbeat(redis_client):
    """
    Worker 心跳線程 - 每 10 秒向 Redis 發送心跳信號
    Backend 可通過檢查 'worker:heartbeat' 鍵來判斷 Worker 是否在線
    
    Args:
        redis_client: Redis 客戶端實例
    """
    while True:
        try:
            # 設置心跳鍵，30 秒過期
            redis_client.setex('worker:heartbeat', 30, 'alive')
            logger.debug("💓 Worker 心跳發送成功")
            time.sleep(10)  # 每 10 秒發送一次
        except Exception as e:
            logger.error(f"❌ Worker 心跳發送失敗: {e}")
            time.sleep(10)


def update_job_status(
    r: redis.Redis,
    job_id: str,
    status: str,
    progress: int = 0,
    image_url: str = None,
    error: str = None,
    db_client=None
):
    """
    更新任務狀態到 Redis 和 MySQL
    
    Args:
        r: Redis 客戶端
        job_id: 任務 ID
        status: 狀態 (processing, finished, failed)
        progress: 進度 (0-100)
        image_url: 輸出圖片 URL
        error: 錯誤訊息
        db_client: Database 客戶端 (可選，用於同步到 MySQL)
    """
    # 1. 更新 Redis
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
    logger.info(f"✓ Redis 狀態更新: {job_id} -> {status}")
    
    # 2. 同步到 MySQL (如果可用且狀態為 finished 或 failed)
    if db_client and status in ['finished', 'failed']:
        try:
            # 轉換 image_url 為 output_path (去除 /outputs/ 前綴)
            output_path = None
            if image_url:
                output_path = image_url.replace('/outputs/', '')
            
            success = db_client.update_job_status(
                job_id=job_id,
                status=status,
                output_path=output_path
            )
            if success:
                logger.info(f"✓ MySQL 狀態同步: {job_id} -> {status}")
            else:
                logger.warning(f"⚠️ MySQL 狀態同步失敗: {job_id}")
        except Exception as e:
            logger.error(f"❌ MySQL 同步錯誤: {e}")



def process_job(r: redis.Redis, client: ComfyClient, job_data: dict, db_client=None):
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
    
    logger.info("="*50)
    logger.info(f"🚀 開始處理任務: {job_id}")
    logger.info("="*50)
    
    try:
        # 1. 更新狀態為處理中
        update_job_status(r, job_id, "processing", progress=10, db_client=db_client)
        
        # 2. 提取參數
        workflow_name = job_data.get("workflow", "text_to_image")
        prompt = job_data.get("prompt", "")
        prompts = job_data.get("prompts", [])  # Veo3 Long Video: 多段 prompts
        seed = job_data.get("seed", -1)
        aspect_ratio = job_data.get("aspect_ratio", "1:1")
        model = job_data.get("model", "turbo_fp8")
        batch_size = job_data.get("batch_size", 1)
        images = job_data.get("images", {})  # base64 圖片字典
        
        logger.info(f"Workflow: {workflow_name}")
        logger.info(f"Prompt: {prompt[:50] if prompt else '(empty)'}...")
        if prompts:
            logger.info(f"Prompts: {len(prompts)} segments")
        logger.info(f"Aspect Ratio: {aspect_ratio}")
        logger.info(f"Model: {model}")
        logger.info(f"Batch Size: {batch_size}")
        logger.info(f"Images: {list(images.keys()) if images else 'None'}")
        
        # 3. 處理上傳的圖片 (base64 -> 檔案)
        update_job_status(r, job_id, "processing", progress=15, db_client=db_client)
        
        image_files = {}  # 儲存檔名映射 {"source": "upload_xxx_source.png"}
        if images:
            logger.info(f"📷 開始處理 {len(images)} 張圖片...")
            for field_name, base64_data in images.items():
                if base64_data:
                    try:
                        filename = save_base64_image(base64_data, job_id, field_name)
                        image_files[field_name] = filename
                    except Exception as e:
                        logger.warning(f"⚠️ 處理圖片 {field_name} 失敗: {e}")
        
        # 3.5 處理音訊參數 (Phase 7 新增)
        # 需要將音訊從 storage/inputs 複製到 ComfyUI/input
        audio_file = job_data.get("audio", "")
        comfyui_audio_file = ""
        if audio_file:
            logger.info(f"🎵 Audio file specified: {audio_file}")
            try:
                comfyui_audio_file = copy_audio_to_comfyui(audio_file, job_id)
            except Exception as e:
                logger.warning(f"⚠️ 複製音訊檔案失敗: {e}")
                comfyui_audio_file = ""
        
        # 4. 解析 workflow (包含圖片與音訊注入)
        update_job_status(r, job_id, "processing", progress=20, db_client=db_client)
        
        workflow = parse_workflow(
            workflow_name=workflow_name,
            prompt=prompt,
            seed=seed,
            aspect_ratio=aspect_ratio,
            model=model,
            batch_size=batch_size,
            image_files=image_files,      # 傳入圖片檔名映射
            audio_file=comfyui_audio_file, # 傳入複製後的音訊檔名 (Phase 7)
            prompts=prompts               # Veo3 Long Video: 傳入多段 prompts
        )
        
        logger.info("Workflow 解析完成")
        
        # 5. 檢查 ComfyUI 連接
        if not client.check_connection():
            raise Exception("無法連接 ComfyUI，請確認是否已啟動")
        
        # 6. 提交任務到 ComfyUI
        update_job_status(r, job_id, "processing", progress=30, db_client=db_client)
        
        prompt_id = client.queue_prompt(workflow)
        if not prompt_id:
            raise Exception("任務提交失敗")
        
        logger.info(f"任務已提交，prompt_id: {prompt_id}")
        
        # 7. 定義進度更新回調函數
        def on_progress(progress):
            # 檢查任務是否被取消
            status_key = f"job:status:{job_id}"
            current_status = r.hget(status_key, "status")
            if current_status == "cancelled":
                logger.warning("🛑 任務已被取消，發送中斷指令...")
                client.interrupt()
                raise Exception("Task cancelled by user")
            
            # 將進度從 30% 開始映射到 30-95%
            mapped_progress = 30 + int(progress * 0.65)
            update_job_status(r, job_id, "processing", progress=mapped_progress, db_client=db_client)

        # 8. 等待 ComfyUI 執行完成
        result = client.wait_for_completion(
            prompt_id=prompt_id,
            timeout=WORKER_TIMEOUT,  # 使用配置值 (預設 2400 秒 = 40 分鐘)
            on_progress=on_progress
        )

        # 9. 根據執行結果處理輸出
        if result.get("success"):
            videos = result.get("videos", [])
            gifs = result.get("gifs", [])  # VHS_VideoCombine 輸出影片也在這裡
            images = result.get("images", [])
            
            # 合併所有視訊類輸出 (videos + gifs)，統一處理
            all_video_outputs = []
            for v in videos:
                v["_source"] = "videos"
                all_video_outputs.append(v)
            for g in gifs:
                g["_source"] = "gifs"
                all_video_outputs.append(g)
            
            logger.info(f"📊 輸出統計: videos={len(videos)}, gifs={len(gifs)}, images={len(images)}")
            
            output_list = []
            output_type = "unknown"
            
            # 優先順序: 視訊類 (videos + gifs) > 圖片
            if all_video_outputs:
                output_list = all_video_outputs
                output_type = "video"
                logger.info(f"🎥 收到 {len(all_video_outputs)} 個視訊輸出")
            elif images:
                output_list = images
                output_type = "image"
                logger.info(f"📷 收到 {len(images)} 張輸出圖片")
            
            if output_list:
                # 過濾掉臨時預覽圖（type: 'temp'），只保留真實輸出
                real_outputs = [item for item in output_list if item.get("type") != "temp"]
                
                if not real_outputs:
                    logger.warning("⚠️ 只有臨時預覽圖，沒有真實輸出")
                    logger.info("📋 臨時預覽圖列表:")
                    for item in output_list:
                        logger.info(f"   - {item.get('filename')} (type: {item.get('type')})")
                    # 如果完全沒有輸出，使用臨時預覽圖作為後備
                    real_outputs = output_list
                else:
                    logger.info(f"✓ 過濾後剩餘 {len(real_outputs)} 個真實輸出")
                
                # 優先選擇完整合併的影片 (filename 包含 Combined 或 Full)
                selected_file = None
                
                # 1. 第一輪篩選：找 "Combined" 或 "Full" (Veo3 Long Video 最終輸出)
                for item in real_outputs:
                    filename = item.get("filename", "")
                    if "Combined" in filename or "Full" in filename:
                        selected_file = item
                        logger.info(f"✨ 優先選擇合併影片: {filename}")
                        break
                
                # 2. 第二輪篩選：如果有 subfolder (備選)
                if not selected_file:
                    for item in real_outputs:
                        if item.get("subfolder"):
                            selected_file = item
                            logger.info(f"選擇有子目錄的檔案: {item.get('filename')} (subfolder: {item.get('subfolder')})")
                            break
                
                # 3. 最後手段：使用最後一個（通常最終輸出在最後）
                if not selected_file:
                    selected_file = real_outputs[-1]
                    logger.info(f"使用最後一個檔案: {selected_file.get('filename')}")
                
                # 嘗試複製選中的檔案（傳遞 file_type）
                file_type = selected_file.get("type", "output")
                new_filename = client.copy_output_file(
                    filename=selected_file.get("filename"),
                    subfolder=selected_file.get("subfolder", ""),
                    file_type=file_type,
                    job_id=job_id
                )
                
                # 如果選中的檔案複製失敗，嘗試其他檔案
                if not new_filename and len(real_outputs) > 1:
                    logger.warning("⚠️ 第一選擇失敗，嘗試其他檔案...")
                    for item in real_outputs:
                        if item == selected_file:
                            continue
                        file_type = item.get("type", "output")
                        new_filename = client.copy_output_file(
                            filename=item.get("filename"),
                            subfolder=item.get("subfolder", ""),
                            file_type=file_type,
                            job_id=job_id
                        )
                        if new_filename:
                            logger.info(f"✓ 成功複製備選檔案: {item.get('filename')}")
                            break
                
                if new_filename:
                    # 無論是圖片還是影片，都通過 image_url 欄位回傳 (前端會根據副檔名判斷)
                    file_url = f"/outputs/{new_filename}"
                    update_job_status(r, job_id, "finished", progress=100, image_url=file_url, db_client=db_client)
                    logger.info(f"✅ 任務完成，輸出 ({output_type}): {file_url}")
                else:
                    update_job_status(r, job_id, "finished", progress=100, db_client=db_client)
                    logger.warning("⚠️ 任務完成，但所有輸出檔案都無法複製")
            else:
                update_job_status(r, job_id, "finished", progress=100, db_client=db_client)
                logger.info("✅ 任務完成，但沒有輸出檔案")
        else:
            error = result.get("error", "未知錯誤")
            
            # 超時情況特殊處理：嘗試從 History API 獲取部分結果
            if "超時" in error or "timeout" in error.lower():
                logger.warning("⚠️ 任務超時，嘗試獲取已完成的輸出...")
                try:
                    partial_outputs = client.get_outputs_from_history(prompt_id)
                    all_partial = partial_outputs.get("videos", []) + partial_outputs.get("gifs", []) + partial_outputs.get("images", [])
                    if all_partial:
                        # 有部分輸出，也複製到 Gallery
                        new_filename = client.copy_output_file(
                            filename=all_partial[-1].get("filename"),
                            subfolder=all_partial[-1].get("subfolder", ""),
                            job_id=job_id
                        )
                        if new_filename:
                            file_url = f"/outputs/{new_filename}"
                            update_job_status(r, job_id, "failed", error=f"{error} (partial output saved)", image_url=file_url, db_client=db_client)
                            logger.info(f"⚠️ 任務超時但已保存部分輸出: {file_url}")
                            return
                except Exception as partial_err:
                    logger.warning(f"⚠️ 獲取部分輸出失敗: {partial_err}")
            
            update_job_status(r, job_id, "failed", error=error, db_client=db_client)
            logger.error(f"❌ 任務失敗: {error}")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ 處理錯誤: {error_msg}")
        update_job_status(r, job_id, "failed", progress=0, error=error_msg, db_client=db_client)


def main():
    """
    Worker 主迴圈
    """
    logger.info("="*50)
    logger.info("🚀 Worker 啟動中...")
    logger.info("="*50)
    
    # 1. 連接 Redis
    try:
        r = get_redis_client()
        r.ping()
        logger.info(f"✅ Redis 連接成功 ({REDIS_HOST}:{REDIS_PORT})")
    except Exception as e:
        logger.error(f"❌ Redis 連接失敗: {e}")
        sys.exit(1)
    
    # 2. 連接資料庫 (可選)
    db_client = None
    try:
        # 嘗試從環境變數載入資料庫配置
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = int(os.getenv("DB_PORT", 3306))
        db_user = os.getenv("DB_USER", "studio_user")
        db_password = os.getenv("DB_PASSWORD", "studio_password")
        db_name = os.getenv("DB_NAME", "studio_db")
        
        # 從 shared 模組導入 Database 類
        from shared.database import Database
        
        db_client = Database(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        logger.info(f"✅ 資料庫連接成功 ({db_host}:{db_port}/{db_name})")
    except Exception as e:
        logger.warning(f"⚠️ 資料庫連接失敗 (功能降級): {e}")
    
    # 3. 初始化 ComfyUI 客戶端
    client = ComfyClient()
    
    # 4. 檢查 ComfyUI 連接
    if client.check_connection():
        logger.info("✅ ComfyUI 連接成功")
    else:
        logger.warning("⚠️ ComfyUI 尚未啟動，將持續等待...")
    
    # 5. 清理舊的暫存檔案
    logger.info("🗑️ 清理過期暫存檔案...")
    cleanup_old_temp_files()
    
    # 6. 清理超過 30 天的輸出圖片 (並同步資料庫)
    logger.info("🗑️ 清理超過 30 天的輸出圖片...")
    cleanup_old_output_files(db_client)
    
    # 7. 啟動 Worker 心跳線程
    logger.info("💓 啟動 Worker 心跳線程...")
    heartbeat_thread = threading.Thread(target=worker_heartbeat, args=(r,), daemon=True)
    heartbeat_thread.start()
    
    # 8. 開始處理佇列
    logger.info(f"\n監聽佇列: {JOB_QUEUE}")
    logger.info(f"ComfyUI Input 目錄: {COMFYUI_INPUT_DIR}")
    logger.info("等待任務中...\n")
    
    last_cleanup_time = time.time()
    CLEANUP_INTERVAL = 3600  # 每小時清理一次
    
    while True:
        try:
            # 定期清理暫存檔案和輸出圖片
            if time.time() - last_cleanup_time > CLEANUP_INTERVAL:
                cleanup_old_temp_files()
                cleanup_old_output_files(db_client)
                last_cleanup_time = time.time()
            
            # BLPOP: 阻塞式取出任務 (超時 5 秒)
            result = r.blpop(JOB_QUEUE, timeout=5)
            
            if result:
                queue_name, job_json = result
                
                try:
                    job_data = json.loads(job_json)
                    process_job(r, client, job_data, db_client)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON 解析錯誤: {e}")
            
        except redis.ConnectionError as e:
            logger.error(f"Redis 連接中斷，5 秒後重試: {e}")
            time.sleep(5)
            try:
                r = get_redis_client()
            except:
                pass
                
        except KeyboardInterrupt:
            logger.info("\n收到中斷信號，正在關閉...")
            break
            
        except Exception as e:
            logger.error(f"未預期錯誤: {e}")
            time.sleep(1)
    
    logger.info("已關閉")


if __name__ == '__main__':
    main()
