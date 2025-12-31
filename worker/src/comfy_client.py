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
from pathlib import Path
from typing import Optional, Callable

from config import (
    COMFY_HOST, COMFY_PORT, COMFY_HTTP_URL, COMFY_WS_URL,
    COMFYUI_OUTPUT_DIR, STORAGE_OUTPUT_DIR
)

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
    
    def check_connection(self) -> bool:
        """
        檢查 ComfyUI 是否可連接
        """
        try:
            response = requests.get(f"{self.http_url}/system_stats", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"[ComfyClient] 連接失敗: {e}")
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
        timeout: int = 300,
        on_progress: Optional[Callable] = None
    ) -> dict:
        """
        使用 WebSocket 等待任務完成
        
        Args:
            prompt_id: 執行 ID
            timeout: 超時時間 (秒)
            on_progress: 進度回調函數
        
        Returns:
            {
                "success": bool,
                "images": [{"filename": str, "subfolder": str, "type": str}],
                "error": str or None
            }
        """
        ws_url = f"{self.ws_url}?clientId={self.client_id}"
        result = {
            "success": False,
            "images": [],
            "error": None
        }
        all_images = []  # 收集所有輸出圖片
        
        try:
            ws = websocket.create_connection(ws_url, timeout=timeout)
            print(f"[ComfyClient] WebSocket 已連接，等待任務完成...")
            
            start_time = time.time()
            
            while True:
                # 檢查超時
                if time.time() - start_time > timeout:
                    result["error"] = "執行超時"
                    break
                
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
                            # 使用收集到的所有圖片
                            result["images"] = all_images
                            break
                    
                    # 執行完成 (獲取輸出)
                    elif msg_type == "executed":
                        if msg_data.get("prompt_id") == prompt_id:
                            output = msg_data.get("output", {})
                            images = output.get("images", [])
                            if images:
                                # 收集所有圖片，不覆蓋之前的
                                all_images.extend(images)
                                print(f"[ComfyClient] 輸出圖片: {images}")
                    
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
    
    def copy_output_image(
        self, 
        filename: str, 
        subfolder: str = "",
        job_id: str = None
    ) -> Optional[str]:
        """
        將 ComfyUI 輸出的圖片複製到 storage/outputs
        
        Args:
            filename: 原始檔名
            subfolder: 子資料夾
            job_id: 任務 ID (用於重命名)
        
        Returns:
            新的檔名，失敗時返回 None
        """
        # 來源路徑
        if subfolder:
            source_path = COMFY_OUTPUT_DIR / subfolder / filename
        else:
            source_path = COMFY_OUTPUT_DIR / filename
        
        if not source_path.exists():
            print(f"[ComfyClient] 找不到輸出檔案: {source_path}")
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
            print(f"[ComfyClient] 已複製圖片: {dest_path}")
            return new_filename
        except Exception as e:
            print(f"[ComfyClient] 複製失敗: {e}")
            return None
    
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
        
        # 4. 複製輸出圖片
        if ws_result["images"]:
            first_image = ws_result["images"][0]
            new_filename = self.copy_output_image(
                filename=first_image.get("filename"),
                subfolder=first_image.get("subfolder", ""),
                job_id=job_id
            )
            
            if new_filename:
                result["success"] = True
                result["image_url"] = f"/outputs/{new_filename}"
        else:
            result["error"] = "沒有輸出圖片"
        
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
