"""
ComfyUI Client
==============
處理與 ComfyUI API 的通訊：
- HTTP POST 提交 workflow
- WebSocket 監聯執行狀態
- 輸出檔案處理
"""

import json
import uuid
import time
import shutil
import requests
import websocket
import sys
from pathlib import Path
from typing import Optional, Callable

from config import (
    COMFY_HOST, COMFY_PORT, COMFY_HTTP_URL, COMFY_WS_URL,
    COMFYUI_OUTPUT_DIR, STORAGE_OUTPUT_DIR
)

# K8s Phase 2: S3 儲存整合
try:
    from shared.config_base import STORAGE_TYPE
    from shared.storage import get_storage_client
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from shared.config_base import STORAGE_TYPE
    from shared.storage import get_storage_client

# 為了向後相容，保留模組級別的別名
COMFY_OUTPUT_DIR = COMFYUI_OUTPUT_DIR


class ComfyClient:
    """
    ComfyUI API 客戶端
    """
    
    def __init__(self, host: str = COMFY_HOST, port: int = COMFY_PORT):
        self.host = host
        self.port = port
        self.http_url = f"http://{host}:{port}"
        self.ws_url = f"ws://{host}:{port}/ws"
        self.client_id = str(uuid.uuid4())
        
        # 確保輸出目錄存在
        STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # K8s Phase 2: 初始化 S3 客戶端（如果啟用）
        self.s3_client = get_storage_client() if STORAGE_TYPE == "s3" else None
        if self.s3_client:
            print(f"[ComfyClient] ✓ S3 儲存模式已啟用")
    
    def check_connection(self, retry: int = 1) -> bool:
        """
        檢查 ComfyUI 是否可連接
        
        Args:
            retry: 失敗時重試次數（預設 1 次）
        
        Returns:
            是否連接成功
        """
        for attempt in range(retry + 1):
            try:
                response = requests.get(f"{self.http_url}/system_stats", timeout=5)
                if response.status_code == 200:
                    return True
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < retry:
                    print(f"[ComfyClient] 連接失敗 ({attempt + 1}/{retry + 1})，5 秒後重試: {e}")
                    time.sleep(5)
                else:
                    print(f"[ComfyClient] 連接失敗（已重試 {retry} 次）: {e}")
            except Exception as e:
                print(f"[ComfyClient] 連接異常: {e}")
                break
        
        return False
    
    def queue_prompt(self, workflow: dict) -> Optional[str]:
        """
        提交 workflow 到 ComfyUI 佇列
        
        Returns:
            prompt_id: 執行 ID，失敗時返回 None
        """
        payload = {
            "prompt": workflow,
            "client_id": self.client_id
        }
        
        try:
            response = requests.post(
                f"{self.http_url}/prompt",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                prompt_id = result.get("prompt_id")
                print(f"[ComfyClient] 任務已提交，prompt_id: {prompt_id}")
                return prompt_id
            else:
                print(f"[ComfyClient] 提交失敗: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[ComfyClient] 提交錯誤: {e}")
            return None
    
    def wait_for_completion(
        self, 
        prompt_id: str, 
        timeout: int = None,  # Phase 9: 改為 None，使用 config 預設值
        on_progress: Optional[Callable] = None
    ) -> dict:
        """
        使用 WebSocket 等待任務完成
        
        Args:
            prompt_id: 執行 ID
            timeout: 超時時間 (秒)，None 則使用配置預設值
            on_progress: 進度回調函數
        
        Returns:
            {
                "success": bool,
                "images": [{"filename": str, "subfolder": str, "type": str}],
                "videos": [{"filename": str, "subfolder": str, "type": str}],
                "gifs": [{"filename": str, "subfolder": str, "type": str}],
                "error": str or None
            }
        """
        # Phase 9: 使用配置的 WORKER_TIMEOUT
        from config import WORKER_TIMEOUT, COMFY_POLLING_INTERVAL
        if timeout is None:
            timeout = WORKER_TIMEOUT
        
        ws_url = f"{self.ws_url}?clientId={self.client_id}"
        result = {
            "success": False,
            "images": [],
            "videos": [],
            "gifs": [],
            "error": None
        }
        all_images = []  # 收集所有輸出圖片
        all_videos = []  # 收集所有輸出影片
        all_gifs = []    # 收集所有輸出 GIF
        
        try:
            ws = websocket.create_connection(ws_url, timeout=timeout)
            print(f"[ComfyClient] WebSocket 已連接，等待任務完成（超時: {timeout}s）...")
            
            start_time = time.time()
            last_heartbeat = start_time  # Phase 9: 記錄上次心跳時間
            
            while True:
                # 檢查超時
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    result["error"] = f"執行超時（已等待 {int(elapsed)}s）"
                    print(f"[ComfyClient] ❌ 任務超時: {prompt_id} ({int(elapsed)}s)")
                    break
                
                # Phase 9: 每 60 秒輸出一次心跳日誌（保持連接存活，證明沒有卡死）
                if elapsed - last_heartbeat >= 60:
                    print(f"[ComfyClient] 💓 任務 {prompt_id} 仍在處理中... （已等待: {int(elapsed)}s / {timeout}s）")
                    last_heartbeat = elapsed
                
                try:
                    message = ws.recv()
                    
                    # 跳過二進制消息 (圖片預覽等)
                    if isinstance(message, bytes):
                        continue
                    
                    # 嘗試解析 JSON
                    try:
                        data = json.loads(message)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # 無法解析的消息，跳過
                        continue
                    
                    # 確保 data 是字典類型
                    if not isinstance(data, dict):
                        continue
                    
                    msg_type = data.get("type")
                    msg_data = data.get("data") or {}  # 確保 msg_data 不為 None
                    
                    # 確保 msg_data 是字典類型
                    if not isinstance(msg_data, dict):
                        msg_data = {}
                    
                    # 進度更新
                    if msg_type == "progress":
                        value = msg_data.get("value", 0)
                        max_value = msg_data.get("max", 100)
                        progress = int((value / max_value) * 100)
                        print(f"[ComfyClient] 進度: {progress}%")
                        
                        # 透過回調函數通知進度更新
                        if on_progress:
                            on_progress(progress)
                    
                    # 執行中
                    elif msg_type == "executing":
                        node = msg_data.get("node")
                        if node:
                            print(f"[ComfyClient] 執行節點: {node}")
                        elif msg_data.get("prompt_id") == prompt_id:
                            # node 為 None 表示執行完成
                            print(f"[ComfyClient] 任務執行完成")
                            result["success"] = True
                            # 使用收集到的所有輸出
                            result["images"] = all_images
                            result["videos"] = all_videos
                            result["gifs"] = all_gifs
                            
                            # 如果 WebSocket 沒有收到輸出，從 History API 獲取
                            if not all_images and not all_videos and not all_gifs:
                                print(f"[ComfyClient] WebSocket 未收到輸出，嘗試從 History API 獲取...")
                                history_outputs = self.get_outputs_from_history(prompt_id)
                                result["images"] = history_outputs.get("images", [])
                                result["videos"] = history_outputs.get("videos", [])
                                result["gifs"] = history_outputs.get("gifs", [])
                                
                                if result["images"] or result["videos"] or result["gifs"]:
                                    print(f"[ComfyClient] ✅ 從 History API 獲取到輸出")
                            break
                    
                    # 執行完成 (獲取輸出)
                    elif msg_type == "executed":
                        if msg_data.get("prompt_id") == prompt_id:
                            output = msg_data.get("output", {})
                            # 確保 output 是字典類型（防止 ComfyUI 返回 None）
                            if output is None or not isinstance(output, dict):
                                output = {}
                            
                            # 處理圖片
                            images = output.get("images", [])
                            if images:
                                all_images.extend(images)
                                print(f"[ComfyClient] 輸出圖片: {images}")
                                
                            # 處理影片 (有些節點可能用 videos)
                            videos = output.get("videos", [])
                            if videos:
                                all_videos.extend(videos)
                                print(f"[ComfyClient] 輸出影片: {videos}")
                                
                            # 處理 GIF (有些節點可能用 gifs)
                            gifs = output.get("gifs", [])
                            if gifs:
                                all_gifs.extend(gifs)
                                print(f"[ComfyClient] 輸出 GIF: {gifs}")

                    
                    # 執行錯誤
                    elif msg_type == "execution_error":
                        if msg_data.get("prompt_id") == prompt_id:
                            error_msg = msg_data.get("exception_message", "未知錯誤")
                            result["error"] = error_msg
                            print(f"[ComfyClient] 執行錯誤: {error_msg}")
                            break
                            
                except websocket.WebSocketTimeoutException:
                    continue
            
            ws.close()
            
        except Exception as e:
            result["error"] = str(e)
            print(f"[ComfyClient] WebSocket 錯誤: {e}")
        
        return result
    
    def get_outputs_from_history(self, prompt_id: str) -> dict:
        """
        從 ComfyUI History API 獲取任務輸出
        
        這是 WebSocket 的備用方案，用於處理 WebSocket 可能漏掉輸出訊息的情況。
        VHS_VideoCombine 節點的輸出可能不會通過 WebSocket 正確發送。
        
        Args:
            prompt_id: 執行 ID
        
        Returns:
            {
                "images": [...],
                "videos": [...],
                "gifs": [...]
            }
        """
        result = {"images": [], "videos": [], "gifs": []}
        
        try:
            response = requests.get(
                f"{self.http_url}/history/{prompt_id}",
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"[ComfyClient] History API 返回錯誤: {response.status_code}")
                return result
            
            history = response.json()
            
            if prompt_id not in history:
                print(f"[ComfyClient] History 中找不到 prompt_id: {prompt_id}")
                return result
            
            outputs = history[prompt_id].get("outputs", {})
            
            # 遍歷所有節點的輸出
            for node_id, node_output in outputs.items():
                # 處理圖片
                images = node_output.get("images", [])
                if images:
                    result["images"].extend(images)
                    print(f"[ComfyClient] History - 節點 {node_id} 輸出圖片: {len(images)} 張")
                
                # 處理影片 (VHS_VideoCombine 使用 gifs 欄位存放影片)
                videos = node_output.get("videos", [])
                if videos:
                    result["videos"].extend(videos)
                    print(f"[ComfyClient] History - 節點 {node_id} 輸出影片: {len(videos)} 個")
                
                # 處理 GIF (VHS_VideoCombine 輸出)
                gifs = node_output.get("gifs", [])
                if gifs:
                    result["gifs"].extend(gifs)
                    print(f"[ComfyClient] History - 節點 {node_id} 輸出 GIF/影片: {len(gifs)} 個")
            
            total = len(result["images"]) + len(result["videos"]) + len(result["gifs"])
            print(f"[ComfyClient] History API 總共找到 {total} 個輸出檔案")
            
        except Exception as e:
            print(f"[ComfyClient] History API 錯誤: {e}")
        
        return result
    
    def copy_output_file(
        self, 
        filename: str, 
        subfolder: str = "",
        file_type: str = "output",  # 新增：'output' 或 'temp'
        job_id: str = None
    ) -> Optional[str]:
        """
        將 ComfyUI 輸出的檔案（圖片/影片）複製到 storage/outputs
        
        Args:
            filename: 原始檔名
            subfolder: 子資料夾
            file_type: 檔案類型，'output' 或 'temp' (預設 'output')
            job_id: 任務 ID (用於重命名)
        
        Returns:
            新的檔名，失敗時返回 None
        """
        # 根據 file_type 決定來源根目錄
        if file_type == "temp":
            base_dir = COMFY_OUTPUT_DIR.parent / "temp"
        else:
            base_dir = COMFY_OUTPUT_DIR
        
        # 來源路徑
        if subfolder:
            source_path = base_dir / subfolder / filename
        else:
            source_path = base_dir / filename
        
        print(f"[ComfyClient] 檢查檔案路徑: {source_path}")
        
        if not source_path.exists():
            print(f"[ComfyClient] 找不到輸出檔案: {source_path}")
            
            # 嘗試備用路徑（有時 ComfyUI 的輸出可能在不同位置）
            alternative_paths = []
            
            # 1. 嘗試直接在 output 根目錄
            if subfolder:
                alternative_paths.append(COMFY_OUTPUT_DIR / filename)
            
            # 2. 如果是 temp 類型，嘗試 output 目錄
            if file_type == "temp":
                if subfolder:
                    alternative_paths.append(COMFY_OUTPUT_DIR / subfolder / filename)
                else:
                    alternative_paths.append(COMFY_OUTPUT_DIR / filename)
            
            # 3. 嘗試 temp 目錄（即使 file_type 不是 temp）
            if file_type != "temp":
                temp_dir = COMFY_OUTPUT_DIR.parent / "temp"
                if subfolder:
                    alternative_paths.append(temp_dir / subfolder / filename)
                else:
                    alternative_paths.append(temp_dir / filename)
            
            # 檢查所有備用路徑
            for alt_path in alternative_paths:
                print(f"[ComfyClient] 嘗試備用路徑: {alt_path}")
                if alt_path.exists():
                    print(f"[ComfyClient] ✓ 在備用路徑找到檔案！")
                    source_path = alt_path
                    break
            else:
                # 所有路徑都找不到
                print(f"[ComfyClient] ✗ 所有可能路徑都找不到檔案")
                return None
        
        # 目標檔名
        ext = source_path.suffix
        if job_id:
            new_filename = f"{job_id}{ext}"
        else:
            new_filename = f"{int(time.time())}_{filename}"
        
        dest_path = STORAGE_OUTPUT_DIR / new_filename
        
        try:
            shutil.copy2(source_path, dest_path)
            print(f"[ComfyClient] ✓ 已複製檔案: {source_path} -> {dest_path}")
            
            # K8s Phase 2: 上傳到 S3（如果啟用）
            if self.s3_client and STORAGE_TYPE == "s3":
                object_key = f"outputs/{new_filename}"
                success = self.s3_client.upload_file(dest_path, object_key)
                if success:
                    print(f"[ComfyClient] ✓ 已上傳至 S3: {object_key}")
                else:
                    print(f"[ComfyClient] ⚠️ S3 上傳失敗，但本地檔案已保存")
            
            return new_filename
        except Exception as e:
            print(f"[ComfyClient] ✗ 複製檔案失敗: {e}")
            return None
            
    # 向後相容別名
    copy_output_image = copy_output_file
    
    def interrupt(self) -> bool:
        """
        中斷 ComfyUI 當前執行的任務
        
        Returns:
            bool: 是否成功發送中斷指令
        """
        try:
            response = requests.post(
                f"{self.http_url}/interrupt",
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"[ComfyClient] ✓ 中斷指令已發送")
                return True
            else:
                print(f"[ComfyClient] ✗ 中斷失敗: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[ComfyClient] ✗ 中斷錯誤: {e}")
            return False
    
    def process_task(self, workflow: dict, job_id: str = None) -> dict:
        """
        完整處理一個任務
        
        Args:
            workflow: 已解析的 workflow dict
            job_id: 任務 ID
        
        Returns:
            {
                "success": bool,
                "image_url": str or None,
                "error": str or None
            }
        """
        result = {
            "success": False,
            "image_url": None,
            "error": None
        }
        
        # 1. 檢查連接
        if not self.check_connection():
            result["error"] = "無法連接 ComfyUI，請確認是否已啟動"
            return result
        
        # 2. 提交任務
        prompt_id = self.queue_prompt(workflow)
        if not prompt_id:
            result["error"] = "任務提交失敗"
            return result
        
        # 3. 等待完成
        ws_result = self.wait_for_completion(prompt_id)
        
        if not ws_result["success"]:
            result["error"] = ws_result.get("error", "執行失敗")
            return result
        
        # 4. 複製輸出
        output_file = None
        
        # 優先檢查影片/GIF
        if ws_result["videos"]:
            output_file = ws_result["videos"][0]
        elif ws_result["gifs"]:
            output_file = ws_result["gifs"][0]
        elif ws_result["images"]:
            output_file = ws_result["images"][0]
            
        if output_file:
            new_filename = self.copy_output_file(
                filename=output_file.get("filename"),
                subfolder=output_file.get("subfolder", ""),
                job_id=job_id
            )
            
            if new_filename:
                result["success"] = True
                result["image_url"] = f"/outputs/{new_filename}"
        else:
            result["error"] = "沒有輸出檔案"
        
        return result


# ==========================================
# 測試用
# ==========================================
if __name__ == "__main__":
    client = ComfyClient()
    
    if client.check_connection():
        print("[Test] ComfyUI 連接成功！")
    else:
        print("[Test] ComfyUI 連接失敗，請確認是否已啟動")
