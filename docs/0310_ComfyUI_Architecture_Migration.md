# ComfyUI 架構遷移：Windows 本地 → Linux 雲端

> **文檔日期**: 2026-03-10  
> **分支**: `feature/twcc-linux-migration`  
> **目的**: 說明 ComfyUI 從 Windows 本地遷移到 TWCC Linux 雲端的架構改動

---

## 當前狀況 vs 新架構的差異

### 當前架構（Windows 本地）

```
你的 Windows 電腦
├── ComfyUI（本地安裝，GPU 在你的 Windows）
│   └── 監聽 127.0.0.1:8188
│
├── Flask Backend（Python venv）
│   └── Worker 向 ComfyUI:8188 發請求
│
└── Ngrok 穿透
    └── 將 localhost:5000 暴露到公網
    └── https://[id].ngrok-free.app → localhost:5000
```

**數據流**：
```
Web 用戶 → Ngrok → Flask (localhost:5000) 
         → Worker 讀任務佇列 
         → ComfyUI (127.0.0.1:8188) 
         → Windows GPU 算圖
         → 結果存到 storage/
```

### 新架構（TWCC 雲端）

```
TWCC 雲端
├── Base VM (v2.super, 常駐)
│   ├── Nginx
│   ├── Flask Backend ← 邏輯與 Windows 完全相同
│   ├── Redis / MySQL
│   └── 監聽 docker network
│
└── GPU VM (A100, Cron 排程)
    ├── ComfyUI（Linux 版本！） ← 這是新的
    │   └── 監聽 127.0.0.1:8188
    │
    └── Worker（Python） ← 邏輯與 Windows 版本相同
        └── 向 ComfyUI:8188 發請求
```

**數據流**：
```
Web 用戶 → TWCC LB (HTTPS) 
         → Base VM Nginx 
         → Flask (backend:5000)
         → 任務存 Redis
         → GPU VM Worker 讀任務
         → Linux ComfyUI (127.0.0.1:8188) ← A100 GPU 算圖
         → 結果上傳 TWCC COS
```

---

## 改動部分：只有「ComfyUI 部署位置」

### ✅ 改了什麼

| 面向 | Windows 本地 | TWCC 雲端 |
|------|------------|---------|
| **ComfyUI 版本** | 你裝的那個（Python） | Linux 版本（同個項目，移到 Linux） |
| **ComfyUI 運行方式** | 你手動點開 UI 或用 bat 啟動 | `systemd comfyui.service` 自啟 |
| **ComfyUI 監聽位置** | 127.0.0.1:8188（Windows） | 127.0.0.1:8188（Linux） |
| **ComfyUI 存放路徑** | `C:\ComfyUI\` | `/opt/comfyui/`（Linux 慣例） |
| **ComfyUI GPU** | Windows GPU（你的顯卡） | TWCC A100（雲端 GPU） |
| **ComfyUI 模型存放** | `C:\ComfyUI\models\` | `/opt/comfyui/models/`（TWCC COS 同步） |

### ❌ 沒改的東西

```python
# Worker 連 ComfyUI 的邏輯完全相同
comfy_client = ComfyUIClient(host='127.0.0.1', port=8188)
queue_result = comfy_client.queue_prompt(api_format_prompt)
```

**沒有改動**：
- ComfyUI API 呼叫方式（同一套）
- Worker 內部邏輯（同一份程式碼）
- 任務佇列格式（Redis 中的資料結構相同）
- Flask API 端點（/api/generate 邏輯相同）

---

## 具體改動細節

### 1️⃣ ComfyUI 啟動方式改變

**Windows（現在）**：
```batch
# start_unified_windows.bat 會啟動
python -m comfy.main --listen 127.0.0.1 --port 8188 --gpu-device 0
```

**Linux（新）**：
```bash
# systemd 服務自動啟動
[Service]
ExecStart=/usr/bin/python main.py --listen 127.0.0.1 --port 8188 --gpu-device 0
WorkingDirectory=/opt/comfyui
Environment=NVIDIA_VISIBLE_DEVICES=all
```

### 2️⃣ ComfyUI 模型存放改變

**Windows（現在）**：
```
C:\ComfyUI\models\
├── checkpoints\
│   └── sd-v1.5.safetensors
├── vae\
└── loras\
```

**Linux（新）**：
```
/opt/comfyui/models/         ← 本地快取
├── checkpoints/
├── vae/
└── loras/
    ↓（可選）
    定期同步到 TWCC COS
    以便跨 GPU VM 共享模型
```

### 3️⃣ ComfyUI 依賴安裝改變

**Windows（現在）**：
```powershell
pip install -r requirements.txt
# 直接在你的 Windows 環境安裝
```

**Linux（新）**：
```bash
# twcc_gpu_setup.sh 自動執行
cd /opt/comfyui
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 你的 Worker 程式碼改動量

### ❓ Worker 需要改嗎？

**答案：基本不用改！** ✅

```python
# worker/src/comfy_client.py
# 這份程式碼對 Windows 和 Linux ComfyUI 都適用

class ComfyUIClient:
    def __init__(self, host='127.0.0.1', port=8188):
        self.server_address = f"{host}:{port}"
        
    def queue_prompt(self, prompt_dict):
        # API 調用邏輯完全相同
        response = requests.post(
            f"http://{self.server_address}/prompt",
            json=prompt_dict
        )
        return response.json()
    
    def get_history(self, prompt_id):
        # 同樣邏輯，無論 Windows 還是 Linux
        return requests.get(
            f"http://{self.server_address}/history/{prompt_id}"
        ).json()
```

**為什麼不用改？**

因為 ComfyUI 的 API 是標準化的，無論在 Windows 還是 Linux 都一樣。

---

## 唯一需要調整的：網路連線

### Windows 本地（現在）

```python
# worker/src/main.py
comfy_client = ComfyUIClient(
    host='127.0.0.1',  # 本機
    port=8188
)
```

### TWCC Linux（新）

```python
# worker/src/main.py（改動最少化）
comfy_client = ComfyUIClient(
    host=os.getenv('COMFYUI_HOST', '127.0.0.1'),
    port=8188
)
```

**環境變數來源（`.env.twcc`）**：
```bash
COMFYUI_HOST=127.0.0.1
# GPU VM 內部 Worker 和 ComfyUI 都在 localhost，所以還是 127.0.0.1
```

**為什麼還是 127.0.0.1？**

```
GPU VM 內部：
├── ComfyUI listening on 127.0.0.1:8188
└── Worker 也在同一台 VM 內部
    └── 透過 localhost 連線最快

不需要透過 Base VM Redis 或任何網路
```

---

## 儲存層的改動（這個改了！）

### ✅ 儲存部分有改動

**Windows（現在）**：
```python
# worker/src/main.py
# 結果直接存到 storage/ 目錄
output_path = os.path.join('storage/outputs', f'{task_id}.png')
shutil.copy2(comfy_output, output_path)
```

**Linux（新）**：
```python
# worker/src/main.py
output_path = os.path.join('storage/outputs', f'{task_id}.png')
shutil.copy2(comfy_output, output_path)  # 本地暫存

# 新增：上傳到 TWCC COS
if os.getenv('STORAGE_BACKEND') == 's3':
    storage_service.upload_file(
        output_path,
        f"outputs/{task_id}.png"
    )
```

**為什麼要上傳？**

```
Linux GPU VM 和 Base VM 是不同機器
├── GPU VM 產出的圖片存在 /opt/studio-worker/storage/outputs/
│   └── Base VM 讀不到（不同機器的檔案系統）
│
└── 解決方案：上傳到 TWCC COS
    └── Base VM 和 GPU VM 都能透過 S3 API 讀取
```

---

## 完整改動清單

### ComfyUI 相關改動

| 項目 | Windows | Linux TWCC | 改動 |
|------|---------|-----------|------|
| **部署位置** | 本地 Windows | Linux GPU VM | 位置改變 |
| **啟動方式** | 手動或 bat | systemd 服務 | 啟動方式改變 |
| **監聽地址** | 127.0.0.1:8188 | 127.0.0.1:8188 | **無改變** ✅ |
| **API 調用** | HTTP localhost | HTTP localhost | **無改變** ✅ |
| **依賴安裝** | pip install | venv + pip | 過程改變，結果相同 |
| **GPU 支援** | CUDA / ROCm | CUDA (A100) | 環境改變 |

### Worker / Backend 相關改動

| 項目 | Windows | Linux TWCC | 改動 |
|------|---------|-----------|------|
| **連 ComfyUI 邏輯** | 127.0.0.1:8188 | 127.0.0.1:8188 | **無改變** ✅ |
| **讀 Redis** | localhost:6379 | Base VM:6379 (私網) | 連線位置改，邏輯無改 |
| **存圖片** | 本地 storage/ | 本地 + S3 上傳 | **新增 S3 層** |
| **讀圖片** | send_from_directory | 生成 presigned URL | **改動（Frontend 用）** |
| **任務佇列** | Redis 相同 | Redis 相同 | **無改變** ✅ |

---

## 你需要關心的改動只有這些

### ✅ 必須改的

1. **ComfyUI 部署從 Windows → Linux**
   - 但這不是你的程式碼改，是運維改
   - 你的程式碼對 ComfyUI 在哪都適用

2. **儲存層新增 S3 上傳**
   - `shared/storage_service.py`（已新增）
   - `worker/src/main.py` 呼叫上傳（已改）
   - 邏輯透析：完成後上傳，完成前不上傳

3. **Flask 新增 presigned URL**
   - `backend/src/app.py` 改動（已改）
   - 邏輯透析：/api/download 回傳簽署 URL 給前端下載

### ❌ 不用改的

```python
# ComfyUI 連線邏輯
comfy_client = ComfyUIClient(host='127.0.0.1', port=8188)

# 任務處理邏輯
prompt = self.parser.parse(workflow)
result = comfy_client.queue_prompt(prompt)
outputs = comfy_client.get_history(result['prompt_id'])

# 這些都是一模一樣
```

---

## 為什麼不用大改？

```
ComfyUI API 設計原則：
「REST API 是標準化的，無論部署在哪都相同」

就像：
├── 你在本地用 http://127.0.0.1:8188/api
└── ComfyUI Docker 也用 http://comfyui:8188/api
└── TWCC Linux 也用 http://127.0.0.1:8188/api

API 端點相同 → 調用程式碼相同
```

---

## 視覺化：改動涉及範圍

```
架構圖
┌─────────────────────────────────────────────┐
│ ComfyUI 部署改動（位置/運行方式改）         │
│ ↓                                           │
│ worker/src/main.py（儲存層改）              │
│ ├─ 新增：s3 上傳邏輯                       │
│ ├─ 不改：ComfyUI 連線邏輯                  │
│ └─ 不改：任務處理邏輯                      │
│                                             │
│ backend/src/app.py（下載層改）             │
│ ├─ 新增：presigned URL 生成                │
│ └─ 不改：其他 API 邏輯                     │
│                                             │
│ shared/storage_service.py（新增抽象層）    │
│ └─ 統一 local / s3 切換                    │
│                                             │
│ ComfyUI API 調用（完全不改）                │
│ └─ 無論 Windows / Linux 都是                │
│    comfy_client.queue_prompt(prompt)       │
└─────────────────────────────────────────────┘

改動面積占比：
├─ ComfyUI 部署方式：10%（運維）
├─ 儲存層新增：30%（新功能）
├─ API 層適配：20%（新功能）
└─ ComfyUI 調用邏輯：0%（完全不改）
```

---

## 實務驗證方案

### 如果你想驗證改動無虞

1. **本地 Windows 跑現有測試**
   ```powershell
   # 驗證 ComfyUI + Worker + Flask 互動正常
   .\start_unified_windows.bat
   ```

2. **本地 MinIO 模式驗證儲存層**
   ```powershell
   docker compose -f docker-compose.dev-s3.yml up -d
   # 驗證新增的 S3 上傳 / presigned URL 邏輯
   ```

3. **TWCC 部署驗證完整流程**
   ```bash
   # GPU VM 跑 Linux ComfyUI + Worker
   # 驗證雲端完整流程
   bash scripts/twcc_gpu_setup.sh
   ```

**結果**：ComfyUI 能在 Windows 和 Linux 上透明使用 ✅

---

## ComfyUI 版本相容性

### 重要提醒

```
Windows 版 ComfyUI: https://github.com/comfyanonymous/ComfyUI
Linux 版 ComfyUI: 同一個專案，git clone 到 Linux

版本必須相同！
├─ Windows: 某個 commit hash (e.g., abc123)
└─ Linux: 必須是同個 hash
    └─ 原因：workflow 格式可能不同，API 端點相同但行為可能有差

建議：
├─ requirements.txt 記錄 ComfyUI 版本
└─ docker-compose.base.yml 中的 Python 版本也寫死
    └─ 確保可重現構建
```

---

## 相關檔案

- [docs/TWCC_Deployment_Guide.md](docs/TWCC_Deployment_Guide.md) - TWCC 雲端部署指南
- [docs/MinIO_S3_Strategy.md](docs/MinIO_S3_Strategy.md) - MinIO S3 策略
- `worker/comfyui.service.template` - ComfyUI systemd 服務
- `worker/worker.service.template` - Worker systemd 服務
- `scripts/twcc_gpu_setup.sh` - GPU VM 首次建置腳本
- `shared/storage_service.py` - 儲存抽象層

---

## 總結

### 你的問題

> ComfyUI 是做穿透至本地 Windows，目前架構下有改動是與 ComfyUI Linux 作連動嗎?

### 答案

✅ **有改動，但影響很小**

```
改動點：
├─ ComfyUI 物理位置：Windows → Linux GPU VM
│   └─ 但 API 仍是 127.0.0.1:8188（相同）
│
├─ ComfyUI 啟動方式：手動 → systemd 自動啟動
│   └─ 邏輯相同，只是過程改
│
└─ 儲存方式：本地檔案 → 本地 + Cloud S3
    └─ Worker 額外做上傳，但邏輯透析清晰

不改的：
└─ ComfyUI API 呼叫方式 ✅ 完全相同
└─ Worker 內部邏輯 ✅ 邏輯不變
└─ 任務佇列 ✅ Redis 相同
└─ Flask 基礎邏輯 ✅ 不變
```

---

**關鍵insight**: ComfyUI 只是從 Windows 機器移到 Linux 機器，但 API 契約完全相同，所以你的 Worker 程式碼可以無縫跨平台運行。
