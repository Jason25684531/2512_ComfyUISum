"""
Locust 壓力測試腳本 - Phase 7
=================================

模擬真實用戶行為，對 ComfyUI Studio Backend API 進行壓力測試。

測試場景：
1. T2I 生成：POST /api/generate
2. 狀態輪詢：GET /api/status/<job_id>
3. 圖片上傳生成 (可選)：POST /api/upload

使用方式：
locust -f tests/locustfile.py --host=http://localhost:5000
"""

import json
import random
import time
from pathlib import Path
from locust import HttpUser, task, between, events
from locust.exception import StopUser

# ============================================
# 載入測試數據
# ============================================
TEST_PROMPTS_PATH = Path(__file__).parent / "test_prompts.json"

try:
    with open(TEST_PROMPTS_PATH, "r", encoding="utf-8") as f:
        TEST_PROMPTS = json.load(f)
except FileNotFoundError:
    print(f"⚠️ 警告：找不到 {TEST_PROMPTS_PATH}，使用預設 Prompt")
    TEST_PROMPTS = [
        "A beautiful landscape",
        "A futuristic city",
        "A portrait of a person"
    ]

# ============================================
# 配置參數
# ============================================
POLLING_INTERVAL = 1.0  # 狀態輪詢間隔 (秒)
POLLING_TIMEOUT = 60    # 輪詢超時時間 (秒)

# ============================================
# Locust User 類
# ============================================
class ComfyUIUser(HttpUser):
    """
    ComfyUI Studio 用戶模擬
    
    模擬真實用戶行為：
    1. 提交生成任務
    2. 輪詢任務狀態
    3. 等待一段時間後重複
    """
    
    # 模擬人類思考時間 (1-5 秒之間)
    wait_time = between(1, 5)
    
    def on_start(self):
        """用戶會話開始時執行"""
        self.job_id = None
        print(f"👤 用戶 {id(self)} 開始測試")
    
    @task(3)
    def generate_t2i(self):
        """
        Task 1: 文字生成圖片 (Text-to-Image)
        
        權重：3 (最常執行的任務)
        """
        # 隨機選擇測試參數
        prompt = random.choice(TEST_PROMPTS)
        seed = random.randint(0, 999999)
        model = "flux1-dev-fp8.safetensors"  # 預設模型
        aspect_ratio = random.choice(["1:1", "16:9", "9:16", "4:3", "3:4"])
        batch_size = random.choice([1, 2, 4])
        
        payload = {
            "prompt": prompt,
            "seed": seed,
            "workflow": "text_to_image",
            "model": model,
            "aspect_ratio": aspect_ratio,
            "batch_size": batch_size
        }
        
        # 發送 POST 請求
        with self.client.post(
            "/api/generate",
            json=payload,
            catch_response=True,
            name="/api/generate [T2I]"
        ) as response:
            try:
                if response.status_code == 200:
                    data = response.json()
                    if "job_id" in data:
                        self.job_id = data["job_id"]
                        response.success()
                        print(f"✅ 任務提交成功: {self.job_id[:8]}... (Prompt: {prompt[:30]}...)")
                    else:
                        response.failure("Response missing job_id")
                elif response.status_code == 429:
                    # Rate Limit 達到上限，記錄但不視為失敗
                    response.success()
                    print(f"⏱️ Rate Limit: {response.text}")
                    time.sleep(5)  # 等待 5 秒後重試
                else:
                    response.failure(f"Status {response.status_code}: {response.text}")
            except json.JSONDecodeError:
                response.failure("Invalid JSON response")
            except Exception as e:
                response.failure(f"Exception: {str(e)}")
    
    @task(2)
    def poll_status(self):
        """
        Task 2: 輪詢任務狀態
        
        權重：2
        """
        if not self.job_id:
            # 如果沒有 job_id，先提交一個任務
            return
        
        start_time = time.time()
        poll_count = 0
        
        while True:
            poll_count += 1
            elapsed = time.time() - start_time
            
            # 超時檢查
            if elapsed > POLLING_TIMEOUT:
                print(f"❌ 任務 {self.job_id[:8]}... 輪詢超時 ({POLLING_TIMEOUT}s)")
                break
            
            # 發送 GET 請求
            with self.client.get(
                f"/api/status/{self.job_id}",
                catch_response=True,
                name="/api/status/<job_id>"
            ) as response:
                try:
                    if response.status_code == 200:
                        data = response.json()
                        status = data.get("status", "unknown")
                        
                        if status == "finished":
                            response.success()
                            print(f"✅ 任務完成: {self.job_id[:8]}... (耗時: {elapsed:.1f}s, 輪詢: {poll_count}次)")
                            self.job_id = None  # 清空 job_id
                            break
                        elif status == "failed":
                            response.failure(f"Job failed: {data.get('error', 'Unknown error')}")
                            print(f"❌ 任務失敗: {self.job_id[:8]}...")
                            self.job_id = None
                            break
                        elif status in ["queued", "processing"]:
                            response.success()
                            # 繼續輪詢
                        else:
                            response.failure(f"Unknown status: {status}")
                            break
                    elif response.status_code == 404:
                        response.failure("Job not found")
                        print(f"❌ 任務不存在: {self.job_id[:8]}...")
                        self.job_id = None
                        break
                    else:
                        response.failure(f"Status {response.status_code}")
                        break
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
                    break
                except Exception as e:
                    response.failure(f"Exception: {str(e)}")
                    break
            
            # 等待一段時間後再輪詢
            time.sleep(POLLING_INTERVAL)
    
    @task(1)
    def get_history(self):
        """
        Task 3: 獲取歷史記錄
        
        權重：1 (較少執行)
        """
        with self.client.get(
            "/api/history?limit=10",
            catch_response=True,
            name="/api/history"
        ) as response:
            try:
                if response.status_code == 200:
                    data = response.json()
                    if "jobs" in data:
                        response.success()
                        print(f"📜 獲取歷史: {len(data['jobs'])} 筆記錄")
                    else:
                        response.failure("Response missing jobs field")
                else:
                    response.failure(f"Status {response.status_code}")
            except json.JSONDecodeError:
                response.failure("Invalid JSON response")
            except Exception as e:
                response.failure(f"Exception: {str(e)}")

# ============================================
# Locust 事件監聽器
# ============================================
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """測試開始時輸出資訊"""
    print("=" * 60)
    print("🚀 Phase 7 壓力測試開始")
    print("=" * 60)
    print(f"📊 載入 {len(TEST_PROMPTS)} 組測試 Prompt")
    print(f"⏱️ 輪詢間隔: {POLLING_INTERVAL}s")
    print(f"⏰ 輪詢超時: {POLLING_TIMEOUT}s")
    print("=" * 60)

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """測試結束時輸出資訊"""
    print("=" * 60)
    print("🏁 Phase 7 壓力測試結束")
    print("=" * 60)
    
    # 輸出統計資訊
    stats = environment.stats
    print(f"📈 總請求數: {stats.total.num_requests}")
    print(f"❌ 失敗數: {stats.total.num_failures}")
    print(f"📊 失敗率: {stats.total.fail_ratio * 100:.2f}%")
    print(f"⚡ 平均響應時間: {stats.total.avg_response_time:.2f}ms")
    print("=" * 60)

# ============================================
# 執行說明
# ============================================
if __name__ == "__main__":
    print(__doc__)
    print("\n請使用以下命令執行測試：")
    print("locust -f tests/locustfile.py --host=http://localhost:5000")
