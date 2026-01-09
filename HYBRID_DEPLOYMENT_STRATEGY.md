# ComfyUI Studio - Windows/Linux 混合部署開發策略

> **統一配置架構** - 一套配置，多環境部署 | Windows 開發 + Linux 生產無縫切換

---

## 📋 目錄

- [架構概覽](#架構概覽)
- [快速開始](#快速開始)
  - [Windows 開發環境 (5分鐘)](#windows-開發環境-5分鐘)
  - [Linux 開發環境 (5分鐘)](#linux-開發環境-5分鐘)
  - [Linux 生產環境 (10分鐘)](#linux-生產環境-10分鐘)
- [核心概念](#核心概念)
- [配置詳解](#配置詳解)
- [部署模式對比](#部署模式對比)
- [常用指令](#常用指令)
- [故障排除](#故障排除)
- [最佳實踐](#最佳實踐)

---

## 架構概覽

### 設計理念

ComfyUI Studio 採用 **統一配置架構**，透過 Docker Compose Profiles 和環境變數實現跨平台部署：

```
單一配置檔案 (docker-compose.unified.yml)
    ↓
Docker Compose Profiles 自動選擇服務
    ↓
.env 環境變數動態調整參數
    ↓
Windows / Linux 無縫切換
```

### 三種部署模式

| 模式 | Profile | 適用場景 | 服務組合 |
|------|---------|---------|---------|
| **Windows 開發** | `windows-dev` | 本地開發測試 | MySQL + Redis + Backend |
| **Linux 開發** | `linux-dev` | 完整開發環境 | MySQL + Redis + ComfyUI + Backend + Worker |
| **Linux 生產** | `linux-prod` | 生產部署 | 同上 + 自動重啟 + 持久化路徑 |

### 架構優勢

✅ **單一真實來源** - 所有服務定義集中在一個檔案  
✅ **環境變數驅動** - 只需調整 `.env` 即可切換環境  
✅ **Profile 自動切換** - 根據需求啟動正確的服務組合  
✅ **向後兼容** - 保留舊配置，平滑遷移  
✅ **易於維護** - 減少配置不一致的問題  

---

## 快速開始

### Windows 開發環境 (5分鐘)

適用於在 Windows 本機運行 ComfyUI，使用 Docker 提供數據庫服務。

#### 步驟 1: 準備環境

```batch
# 確保已安裝
- Docker Desktop for Windows
- Python 3.10+
- Git
```

#### 步驟 2: 配置環境變數

```batch
cd d:\01_Project\2512_ComfyUISum
copy .env.unified.example .env
```

編輯 `.env` 檔案：

```env
# 平台設定
PLATFORM=windows

# ComfyUI 設定 (本機運行)
COMFYUI_HOST=localhost
COMFYUI_PORT=8188
COMFY_HOST=localhost

# 模型路徑 (改成你的實際路徑)
MODEL_PATH=/mnt/d/02_software/ComfyUI_windows_portable/ComfyUI/models

# 資料庫設定
MYSQL_PORT=3307
REDIS_PORT=6379
RESTART_POLICY=unless-stopped
```

#### 步驟 3: 啟動服務

```batch
cd scripts
start_unified_windows.bat
```

選擇 **[1] Infrastructure only** (僅啟動 MySQL + Redis)

#### 步驟 4: 手動啟動其他服務

**ComfyUI (本機)**
```batch
# 在你的 ComfyUI 安裝目錄
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat
```

**Backend (可選)**
```batch
cd backend
python src/app.py
```

#### 步驟 5: 驗證

```batch
# 瀏覽器訪問
http://localhost:5000      # Backend API
http://localhost:8188      # ComfyUI Web UI
```

---

### Linux 開發環境 (5分鐘)

所有服務運行在 Docker，支援 NVIDIA GPU。

#### 步驟 1: 系統準備

```bash
# 確保已安裝
sudo apt update
sudo apt install docker.io docker-compose nvidia-docker2
```

#### 步驟 2: 配置環境變數

```bash
cd /opt/ComfyUIStudio  # 或你的專案路徑
cp .env.unified.example .env
nano .env
```

設定內容：

```env
# 平台設定
PLATFORM=linux

# ComfyUI 設定 (Docker 容器)
COMFYUI_HOST=studio-engine
COMFYUI_PORT=8188
COMFY_HOST=studio-engine

# 模型路徑
MODEL_PATH=/data/models

# 資料庫設定
MYSQL_PORT=3307
REDIS_PORT=6379
RESTART_POLICY=unless-stopped
```

#### 步驟 3: 啟動服務

```bash
chmod +x scripts/start_unified_linux.sh
cd scripts
./start_unified_linux.sh
```

選擇 **[1] Development** (開發模式)

#### 步驟 4: 驗證

```bash
# 檢查服務狀態
docker-compose -f docker-compose.unified.yml ps

# 測試 API
curl http://localhost:8188/system_stats  # ComfyUI
curl http://localhost:5000/health        # Backend
```

---

### Linux 生產環境 (10分鐘)

生產級部署，包含持久化、自動重啟、安全加固。

#### 步驟 1: 系統準備

```bash
# 創建數據目錄
sudo mkdir -p /var/lib/studio/{redis_data,mysql_data,storage}
sudo chown -R $USER:$USER /var/lib/studio

# 創建模型目錄
sudo mkdir -p /mnt/storage/models
sudo chown -R $USER:$USER /mnt/storage
```

#### 步驟 2: 生產環境配置

```bash
cd /opt/ComfyUIStudio
cp .env.unified.example .env
nano .env
```

**生產環境設定：**

```env
# 平台設定
PLATFORM=linux

# ComfyUI 設定
COMFYUI_HOST=studio-engine
COMFYUI_PORT=8188
COMFY_HOST=studio-engine

# 生產環境路徑
MODEL_PATH=/mnt/storage/models
REDIS_DATA_PATH=/var/lib/studio/redis_data
MYSQL_DATA_PATH=/var/lib/studio/mysql_data
STORAGE_DIR=/var/lib/studio/storage

# 重啟策略
RESTART_POLICY=always

# 安全設定 (務必修改!)
MYSQL_ROOT_PASSWORD=<your_strong_password>
DB_PASSWORD=<your_db_password>
REDIS_PASSWORD=<your_redis_password>
```

#### 步驟 3: 啟動服務

```bash
cd scripts
./start_unified_linux.sh
```

選擇 **[2] Production** (生產模式)

#### 步驟 4: 設定開機自動啟動

創建 systemd 服務：

```bash
sudo nano /etc/systemd/system/comfyui-studio.service
```

內容：

```ini
[Unit]
Description=ComfyUI Studio
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/ComfyUIStudio
ExecStart=/usr/local/bin/docker-compose -f docker-compose.unified.yml --profile linux-prod up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.unified.yml --profile linux-prod down
User=your_username

[Install]
WantedBy=multi-user.target
```

啟用服務：

```bash
sudo systemctl daemon-reload
sudo systemctl enable comfyui-studio.service
sudo systemctl start comfyui-studio.service
```

---

## 核心概念

### Docker Compose Profiles

Profiles 讓單一配置檔案支援多種部署模式：

```yaml
services:
  mysql:
    # 無 profile - 所有模式都啟動
    
  backend:
    profiles:
      - windows-dev
      - linux-dev
      - linux-prod
    # 三種模式都啟動
    
  comfyui:
    profiles:
      - linux-dev
      - linux-prod
    # 僅 Linux 模式啟動（Windows 使用本機 ComfyUI）
```

### 環境變數驅動

所有平台差異透過 `.env` 控制：

| 變數 | Windows | Linux 開發 | Linux 生產 |
|------|---------|-----------|-----------|
| `COMFYUI_HOST` | `localhost` | `studio-engine` | `studio-engine` |
| `MODEL_PATH` | `/mnt/d/...` | `/data/models` | `/mnt/storage/models` |
| `REDIS_DATA_PATH` | `./redis_data` | `./redis_data` | `/var/lib/studio/redis_data` |
| `RESTART_POLICY` | `unless-stopped` | `unless-stopped` | `always` |

### 服務組織

```
核心服務 (無 profile - 永遠啟動)
├── Redis (Port 6379)
└── MySQL (Port 3307)

Windows 開發 (windows-dev)
├── 核心服務
└── Backend (Port 5000)
    註: ComfyUI 在本機運行

Linux 開發 (linux-dev)
├── 核心服務
├── ComfyUI (Port 8188 + GPU)
├── Backend (Port 5000)
└── Worker

Linux 生產 (linux-prod)
├── 同 linux-dev
└── + 生產級配置 (持久化路徑 + always 重啟)
```

---

## 配置詳解

### 環境變數完整說明

#### 平台配置

```env
# PLATFORM: 運行平台
# 值: windows | linux
# 說明: 用於腳本判斷和日誌記錄
PLATFORM=windows

# RESTART_POLICY: Docker 容器重啟策略
# 值: no | always | unless-stopped | on-failure
# 建議: 開發環境 unless-stopped | 生產環境 always
RESTART_POLICY=unless-stopped
```

#### Redis 配置

```env
# REDIS_HOST: Redis 主機位址
# 開發: redis (Docker service name)
# 本機測試: localhost
REDIS_HOST=redis

# REDIS_PORT: 外部訪問端口
REDIS_PORT=6379

# REDIS_INTERNAL_PORT: 容器內部端口
REDIS_INTERNAL_PORT=6379

# REDIS_PASSWORD: Redis 密碼
REDIS_PASSWORD=mysecret

# REDIS_DATA_PATH: 數據持久化路徑
# Windows 開發: ./redis_data
# Linux 生產: /var/lib/studio/redis_data
REDIS_DATA_PATH=./redis_data
```

#### MySQL 配置

```env
# DB_HOST: MySQL 主機位址
DB_HOST=mysql

# MYSQL_PORT: 外部訪問端口 (避免與本機 MySQL 衝突)
MYSQL_PORT=3307

# DB_INTERNAL_PORT: 容器內部端口
DB_INTERNAL_PORT=3306

# 數據庫認證
MYSQL_ROOT_PASSWORD=rootpassword
DB_NAME=studio_db
DB_USER=studio_user
DB_PASSWORD=studio_password

# MYSQL_DATA_PATH: 數據持久化路徑
MYSQL_DATA_PATH=./mysql_data
```

#### ComfyUI 配置

```env
# COMFYUI_HOST: ComfyUI 主機位址
# Windows: localhost (本機運行)
# Linux: studio-engine (Docker 容器名稱)
COMFYUI_HOST=localhost

# COMFYUI_PORT: ComfyUI Web UI 端口
COMFYUI_PORT=8188

# COMFY_HOST: Worker 連接的 ComfyUI 主機
# 必須與服務實際位置一致
COMFY_HOST=localhost

# COMFYUI_PATH: ComfyUI 程式碼路徑
COMFYUI_PATH=./ComfyUI

# MODEL_PATH: 模型檔案路徑
# Windows: /mnt/d/... (WSL 路徑)
# Linux: /data/models 或 /mnt/storage/models
MODEL_PATH=/mnt/d/02_software/ComfyUI_windows_portable/ComfyUI/models
```

#### 儲存路徑配置

```env
# STORAGE_DIR: 儲存根目錄
STORAGE_DIR=./storage

# STORAGE_INPUT_DIR: 輸入檔案 (用戶上傳)
STORAGE_INPUT_DIR=./storage/inputs

# STORAGE_OUTPUT_DIR: 輸出檔案 (生成結果)
STORAGE_OUTPUT_DIR=./storage/outputs

# WORKFLOW_DIR: 工作流模板目錄
WORKFLOW_DIR=./ComfyUIworkflow

# LOG_DIR: 日誌目錄
LOG_DIR=./logs
```

---

## 部署模式對比

### 功能對比表

| 功能 | Windows 開發 | Linux 開發 | Linux 生產 |
|------|-------------|-----------|-----------|
| **ComfyUI 運行位置** | 本機 | Docker (GPU) | Docker (GPU) |
| **Backend** | 可選 (Docker/本機) | Docker | Docker |
| **Worker** | 不啟動 | Docker | Docker |
| **MySQL** | Docker | Docker | Docker |
| **Redis** | Docker | Docker | Docker |
| **持久化路徑** | 專案目錄 | 專案目錄 | 系統目錄 |
| **重啟策略** | unless-stopped | unless-stopped | always |
| **適用場景** | 快速開發測試 | 完整功能開發 | 生產部署 |

### 啟動指令對比

```bash
# Windows 開發
cd scripts && start_unified_windows.bat
選擇 [1] Infrastructure only
手動啟動 ComfyUI 和 Backend

# Linux 開發
cd scripts && ./start_unified_linux.sh
選擇 [1] Development
自動啟動所有服務

# Linux 生產
cd scripts && ./start_unified_linux.sh
選擇 [2] Production
自動啟動 + 生產級配置
```

### 手動啟動 (進階)

```bash
# Windows 開發環境
docker-compose -f docker-compose.unified.yml --profile windows-dev up -d

# Linux 開發環境
docker-compose -f docker-compose.unified.yml --profile linux-dev up -d

# Linux 生產環境
docker-compose -f docker-compose.unified.yml --profile linux-prod up -d

# 僅基礎設施 (任何環境)
docker-compose -f docker-compose.unified.yml up -d redis mysql
```

---

## 常用指令

### 查看服務狀態

```bash
# 查看運行中的服務
docker-compose -f docker-compose.unified.yml ps

# 查看特定服務
docker-compose -f docker-compose.unified.yml ps backend
```

### 查看日誌

```bash
# 所有服務日誌 (實時)
docker-compose -f docker-compose.unified.yml logs -f

# 特定服務日誌
docker-compose -f docker-compose.unified.yml logs -f backend
docker-compose -f docker-compose.unified.yml logs -f worker

# 最近 100 行
docker-compose -f docker-compose.unified.yml logs --tail=100 backend
```

### 重啟服務

```bash
# 重啟所有服務
docker-compose -f docker-compose.unified.yml restart

# 重啟特定服務
docker-compose -f docker-compose.unified.yml restart backend
docker-compose -f docker-compose.unified.yml restart worker
```

### 停止服務

```bash
# Windows 開發環境
docker-compose -f docker-compose.unified.yml --profile windows-dev down

# Linux 開發環境
docker-compose -f docker-compose.unified.yml --profile linux-dev down

# Linux 生產環境
docker-compose -f docker-compose.unified.yml --profile linux-prod down

# 停止並刪除資料卷 (注意: 會清除數據!)
docker-compose -f docker-compose.unified.yml down -v
```

### 重建容器

```bash
# Windows 開發
docker-compose -f docker-compose.unified.yml --profile windows-dev build --no-cache
docker-compose -f docker-compose.unified.yml --profile windows-dev up -d

# Linux 開發
docker-compose -f docker-compose.unified.yml --profile linux-dev build --no-cache
docker-compose -f docker-compose.unified.yml --profile linux-dev up -d
```

### 進入容器

```bash
# 進入 Backend 容器
docker exec -it studio-backend /bin/bash

# 進入 Worker 容器
docker exec -it studio-worker /bin/bash

# 進入 MySQL 容器
docker exec -it studio-mysql mysql -u root -p
```

---

## 故障排除

### 問題 1: 端口已被占用

**錯誤訊息:**
```
Error: bind: address already in use
```

**解決方法:**

```bash
# Windows
netstat -ano | findstr :3307
netstat -ano | findstr :5000

# Linux
netstat -tuln | grep 3307
netstat -tuln | grep 5000

# 修改 .env 中的端口
MYSQL_PORT=3308
BACKEND_PORT=5001
```

### 問題 2: Docker 服務無法啟動

**檢查步驟:**

```bash
# 1. 檢查 Docker 狀態
docker ps

# 2. 驗證配置檔案
docker-compose -f docker-compose.unified.yml config

# 3. 查看詳細錯誤
docker-compose -f docker-compose.unified.yml --profile windows-dev up

# 4. 重建容器
docker-compose -f docker-compose.unified.yml down
docker-compose -f docker-compose.unified.yml --profile windows-dev build --no-cache
docker-compose -f docker-compose.unified.yml --profile windows-dev up -d
```

### 問題 3: MySQL 無法連接

**診斷:**

```bash
# 檢查 MySQL 容器狀態
docker-compose -f docker-compose.unified.yml ps mysql

# 查看 MySQL 日誌
docker-compose -f docker-compose.unified.yml logs mysql

# 測試連接
docker exec -it studio-mysql mysql -u root -p

# 檢查健康狀態
docker inspect studio-mysql | grep -i health
```

**解決:**

```bash
# 重新初始化 MySQL (會清除數據!)
docker-compose -f docker-compose.unified.yml down
rm -rf mysql_data/*  # Windows: rmdir /s mysql_data
docker-compose -f docker-compose.unified.yml up -d mysql
```

### 問題 4: ComfyUI 無法訪問 (Linux)

**檢查:**

```bash
# 查看 ComfyUI 日誌
docker-compose -f docker-compose.unified.yml logs comfyui

# 檢查 GPU
nvidia-smi

# 測試 ComfyUI API
curl http://localhost:8188/system_stats
```

### 問題 5: Backend 無法連接服務

**診斷網路:**

```bash
# 查看網路配置
docker network inspect 2512_comfyuisum_studio-net

# 進入 Backend 容器測試
docker exec -it studio-backend /bin/bash
ping redis
ping mysql
ping studio-engine  # Linux only
```

### 問題 6: 配置不生效

```bash
# 檢查環境變數
docker-compose -f docker-compose.unified.yml config

# 驗證 .env 檔案
cat .env | grep -v '^#' | grep -v '^$'

# 重啟服務
docker-compose -f docker-compose.unified.yml restart
```

---

## 最佳實踐

### 開發流程建議

#### Windows 開發環境

1. **首次設定**
   ```batch
   copy .env.unified.example .env
   # 編輯 .env 設定為 Windows 環境
   cd scripts && start_unified_windows.bat
   選擇 [1] Infrastructure only
   ```

2. **日常開發**
   ```batch
   # 啟動 Docker 服務
   cd scripts && start_unified_windows.bat

   # 啟動 ComfyUI (本機)
   D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

   # 啟動 Backend (本機或 Docker)
   cd backend && python src/app.py
   ```

3. **測試完成後**
   ```batch
   # 停止 Docker 服務
   docker-compose -f docker-compose.unified.yml --profile windows-dev down
   ```

#### Linux 開發環境

1. **首次設定**
   ```bash
   cp .env.unified.example .env
   # 編輯 .env 設定為 Linux 環境
   chmod +x scripts/start_unified_linux.sh
   cd scripts && ./start_unified_linux.sh
   選擇 [1] Development
   ```

2. **日常開發**
   ```bash
   # 一鍵啟動所有服務
   cd scripts && ./start_unified_linux.sh

   # 查看日誌
   docker-compose -f docker-compose.unified.yml logs -f
   ```

### 資料備份

```bash
# 備份 MySQL 數據
docker exec studio-mysql mysqldump -u root -p studio_db > backup.sql

# 備份 Redis 數據
docker exec studio-redis redis-cli SAVE
cp redis_data/dump.rdb backup/dump.rdb

# 備份生成的圖片
tar -czf storage_backup.tar.gz storage/outputs/
```

### 安全建議

1. **更改預設密碼**
   ```env
   MYSQL_ROOT_PASSWORD=<strong_password>
   DB_PASSWORD=<strong_password>
   REDIS_PASSWORD=<strong_password>
   ```

2. **限制網路訪問**
   - 生產環境使用防火牆
   - 只開放必要端口
   - 考慮使用 VPN

3. **定期更新**
   ```bash
   # 更新 Docker 映像
   docker-compose -f docker-compose.unified.yml pull
   docker-compose -f docker-compose.unified.yml up -d
   ```

### 效能優化

1. **Redis 連接池** - 在 Backend 配置連接池
2. **圖片壓縮** - 自動壓縮上傳和輸出圖片
3. **CDN 整合** - 大量圖片使用 CDN 服務
4. **負載均衡** - 多 Worker 實例處理高併發

---

## 附錄

### 專案結構

```
ComfyUIStudio/
├── docker-compose.unified.yml      # 統一配置檔案
├── .env                            # 環境變數 (從 .env.unified.example 複製)
├── .env.unified.example            # 環境變數範本
├── scripts/
│   ├── start_unified_windows.bat   # Windows 啟動腳本
│   └── start_unified_linux.sh      # Linux 啟動腳本
├── backend/                        # Backend API 服務
├── worker/                         # Worker 任務處理
├── frontend/                       # Web UI
├── ComfyUIworkflow/               # Workflow 模板
├── storage/                        # 儲存目錄
└── logs/                           # 日誌目錄
```

### 端口映射

| 服務 | 內部端口 | 外部端口 | 說明 |
|------|----------|----------|------|
| MySQL | 3306 | 3307 | 避免與本機 MySQL 衝突 |
| Redis | 6379 | 6379 | 快取和訊息佇列 |
| Backend | 5000 | 5000 | API 服務 |
| ComfyUI | 8188 | 8188 | ComfyUI Web UI |

### 相關文檔

- [專案 README](../README.md) - 專案整體說明
- [UpdateList](../Update_MD/UpdateList.md) - 變更歷史
- [API 測試指南](../backend/Readmd/API_TESTING.md) - API 使用說明

---

**最後更新:** 2026-01-09  
**版本:** 1.0.0
