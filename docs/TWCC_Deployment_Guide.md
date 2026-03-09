# TWCC 雙 VM 部署指南

> Studio Core (ComfyUI Middleware) — 從單機 Windows 遷移至 TWCC Linux 雙 VM 架構

---

## 目錄

1. [架構總覽](#1-架構總覽)
2. [前置需求](#2-前置需求)
3. [Base VM 部署](#3-base-vm-部署)
4. [GPU VM 部署](#4-gpu-vm-部署)
5. [TWCC Load Balancer 設定](#5-twcc-load-balancer-設定)
6. [TWCC COS (S3) 設定](#6-twcc-cos-s3-設定)
7. [Cron 排程管理](#7-cron-排程管理)
8. [Security Group 設定](#8-security-group-設定)
9. [健康檢查與監控](#9-健康檢查與監控)
10. [故障排除 FAQ](#10-故障排除-faq)

---

## 1. 架構總覽

```
┌─────────────────────────────────────────────────┐
│                  TWCC Load Balancer              │
│         (SSL 終端, HTTPS → HTTP:80)              │
└──────────────────────┬──────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │   Base VM (v2.super)       │
         │   ❖ 永遠開機               │
         │                            │
         │  ┌────────────────────┐    │
         │  │ Nginx (:80)        │    │
         │  │  → /api/ → Flask   │    │
         │  │  → /     → 靜態前端│    │
         │  └────────────────────┘    │
         │  ┌────────────────────┐    │
         │  │ Flask API (:5000)  │    │
         │  └────────────────────┘    │
         │  ┌────────────────────┐    │
         │  │ Redis (:6379)      │    │
         │  │  bind 0.0.0.0      │    │
         │  └────────────────────┘    │
         │  ┌────────────────────┐    │
         │  │ MySQL (:3306)      │    │
         │  └────────────────────┘    │
         └─────────────┬─────────────┘
                       │ TWCC 私有網路
                       │ (10.x.x.x)
         ┌─────────────▼─────────────┐
         │   GPU VM (A100)            │
         │   ❖ Cron 排程開關機         │
         │                            │
         │  ┌────────────────────┐    │
         │  │ ComfyUI (:8188)    │    │
         │  │  systemd service   │    │
         │  └────────────────────┘    │
         │  ┌────────────────────┐    │
         │  │ Worker              │    │
         │  │  systemd service   │    │
         │  └────────────────────┘    │
         └───────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │    TWCC COS (S3 相容)      │
         │    studio-outputs bucket   │
         └───────────────────────────┘
```

### 核心設計原則

| 原則 | 說明 |
|------|------|
| **成本最佳化** | GPU VM 僅在工作時間開機（平日 09:00-18:00），其餘時間關機 |
| **零停機前端** | Base VM 永遠在線，使用者隨時可存取前端與歷史作品 |
| **私有通訊** | Redis 透過 TWCC 私有網路暴露，GPU VM 跨 VM 連線 |
| **安全第一** | SSL 在 LB 層終端，內部全部走 HTTP；Security Group 限制存取 |

---

## 2. 前置需求

### 2.1 TWCC 資源

| 資源 | 規格 | 用途 |
|------|------|------|
| VCS 虛擬機 (Base) | v2.super (4 vCPU, 16GB RAM) | Nginx + Flask + Redis + MySQL |
| VCS 虛擬機 (GPU) | 含 A100 或同等 GPU | ComfyUI + Worker |
| COS 儲存體 | S3 相容物件儲存 | 生成圖片/影片持久化 |
| Load Balancer | L7 HTTP(S) | 前端流量分發 + SSL |
| 私有網路 | 10.x.x.x CIDR | VM 間安全通訊 |

### 2.2 本地工具

```bash
# 確保已安裝
docker --version          # >= 24.0
docker compose version    # >= 2.20 (compose v2)
git --version
ssh -V
```

### 2.3 DNS 設定

將你的域名（例如 `studio.example.com`）CNAME 指向 TWCC LB 的公開端點。

---

## 3. Base VM 部署

### 3.1 SSH 登入與基本設定

```bash
ssh ubuntu@<BASE_VM_IP>

# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 安裝 Docker Compose plugin
sudo apt install docker-compose-plugin -y
```

### 3.2 拉取程式碼

```bash
cd ~
git clone <your-repo-url> studio-core
cd studio-core
git checkout feature/twcc-linux-migration
```

### 3.3 設定環境變數

```bash
# 從範本建立環境檔
cp .env.twcc .env

# 編輯實際值
nano .env
```

**必填欄位：**

| 變數 | 範例值 | 說明 |
|------|--------|------|
| `MYSQL_ROOT_PASSWORD` | `<強密碼>` | MySQL root 密碼 |
| `MYSQL_PASSWORD` | `<強密碼>` | 應用程式 DB 密碼 |
| `SECRET_KEY` | `<隨機字串>` | Flask session 加密金鑰 |
| `S3_ENDPOINT` | `https://cos.twcc.ai` | TWCC COS 端點 |
| `S3_ACCESS_KEY` | `<COS Access Key>` | COS 存取金鑰 |
| `S3_SECRET_KEY` | `<COS Secret Key>` | COS 祕密金鑰 |
| `S3_BUCKET` | `studio-outputs` | COS Bucket 名稱 |
| `S3_REGION` | `ap-northeast-1` | COS 區域 |
| `GPU_VM_REDIS_HOST` | `10.x.x.x` | Base VM 在私有網路的 IP |
| `TWCC_API_KEY` | `<API Key>` | TWCC API 金鑰 |
| `TWCC_PROJECT_ID` | `<Project ID>` | TWCC 專案 ID |
| `TWCC_GPU_VM_ID` | `<VM ID>` | GPU VM 的資源 ID |
| `LB_DOMAIN` | `studio.example.com` | LB 對外域名 |

### 3.4 初始化資料庫

首次部署需要初始化 MySQL schema：

```bash
# 先單獨啟動 MySQL
docker compose -f docker-compose.base.yml up -d mysql

# 等待 MySQL 啟動完成（約 30 秒）
sleep 30

# 執行資料庫初始化（如有 schema 檔案）
docker compose -f docker-compose.base.yml exec mysql \
  mysql -u root -p${MYSQL_ROOT_PASSWORD} studio_db < backend/schema.sql

# 確認資料庫正常
docker compose -f docker-compose.base.yml exec mysql \
  mysql -u root -p${MYSQL_ROOT_PASSWORD} -e "SHOW DATABASES;"
```

### 3.5 啟動全部服務

```bash
docker compose -f docker-compose.base.yml up -d

# 檢查所有容器狀態
docker compose -f docker-compose.base.yml ps

# 查看 logs
docker compose -f docker-compose.base.yml logs -f
```

### 3.6 驗證 Base VM

```bash
# Nginx 回應
curl -I http://localhost

# Flask API
curl http://localhost/api/health

# Redis
docker compose -f docker-compose.base.yml exec redis redis-cli ping
# 預期回應：PONG

# MySQL
docker compose -f docker-compose.base.yml exec mysql \
  mysql -u root -p${MYSQL_ROOT_PASSWORD} -e "SELECT 1;"
```

---

## 4. GPU VM 部署

### 4.1 首次設定（自動腳本）

```bash
# 從 Base VM SSH 到 GPU VM
ssh ubuntu@<GPU_VM_PRIVATE_IP>

# 拉取程式碼
cd ~
git clone <your-repo-url> studio-core
cd studio-core
git checkout feature/twcc-linux-migration

# 複製環境設定
cp .env.twcc .env
nano .env  # 填入實際值，特別是 GPU_VM_REDIS_HOST

# 執行一鍵設定腳本
chmod +x scripts/twcc_gpu_setup.sh
sudo bash scripts/twcc_gpu_setup.sh
```

此腳本會自動完成：
- 安裝系統套件（git, python3.10-venv, ffmpeg, nvidia-driver 等）
- 建立 Python 虛擬環境
- 安裝 ComfyUI 與自訂節點
- 建立模型目錄軟連結
- 安裝並啟動 systemd 服務（comfyui + worker）
- 安裝 TWCC CLI

### 4.2 手動驗證服務

```bash
# 查看 ComfyUI 狀態
sudo systemctl status comfyui

# 查看 Worker 狀態
sudo systemctl status worker

# 查看 ComfyUI logs
journalctl -u comfyui -f

# 查看 Worker logs
journalctl -u worker -f

# 測試 ComfyUI API
curl http://127.0.0.1:8188/system_stats

# 測試 Redis 跨 VM 連線
python3 -c "
import redis
r = redis.Redis(host='${GPU_VM_REDIS_HOST}', port=6379)
print(r.ping())
"
```

### 4.3 Systemd 服務管理

```bash
# 重啟 ComfyUI
sudo systemctl restart comfyui

# 重啟 Worker
sudo systemctl restart worker

# 停止所有服務
sudo systemctl stop worker comfyui

# 啟用開機自動啟動
sudo systemctl enable comfyui worker
```

---

## 5. TWCC Load Balancer 設定

### 5.1 建立 LB

1. 登入 TWCC 控制台 → **負載平衡** → **建立**
2. 選擇：
   - 類型：**Application Load Balancer (L7)**
   - 網路：與 Base VM 相同的 VPC
   - Listener：
     - **HTTPS:443** → Target Group (Base VM:80)
     - **HTTP:80** → 自動重導至 HTTPS

### 5.2 SSL 憑證

1. 在 TWCC 控制台上傳 SSL 憑證（或使用 TWCC 託管憑證）
2. 綁定到 HTTPS:443 Listener

### 5.3 Target Group

| 設定 | 值 |
|------|-----|
| Protocol | HTTP |
| Port | 80 |
| 健康檢查路徑 | `/api/health` |
| 健康檢查間隔 | 30s |
| 不健康閾值 | 3 |
| 成員 | Base VM |

### 5.4 重要提醒

- LB 做 **SSL 終端**（SSL Termination），後方全部走 HTTP
- Nginx 已設定接收 `X-Forwarded-Proto` header 來判斷原始協定
- Flask 的 `ProxyFix` 會正確解析 LB 傳遞的真實 IP

---

## 6. TWCC COS (S3) 設定

### 6.1 建立 Bucket

```bash
# 使用 AWS CLI（相容 S3）
aws configure --profile twcc-cos
# Access Key: <COS Access Key>
# Secret Key: <COS Secret Key>
# Region: ap-northeast-1

aws s3 mb s3://studio-outputs \
  --endpoint-url https://cos.twcc.ai \
  --profile twcc-cos
```

### 6.2 CORS 設定

**⚠️ 這很重要！** 前端需要直接載入 COS 上的圖片/影片。

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": [
      "https://studio.example.com",
      "https://*.twcc.ai"
    ],
    "ExposeHeaders": ["Content-Length", "Content-Type", "ETag"],
    "MaxAgeSeconds": 86400
  }
]
```

```bash
# 套用 CORS 設定
aws s3api put-bucket-cors \
  --bucket studio-outputs \
  --cors-configuration file://cors.json \
  --endpoint-url https://cos.twcc.ai \
  --profile twcc-cos
```

### 6.3 驗證 COS 連線

```bash
# 上傳測試檔案
echo "test" | aws s3 cp - s3://studio-outputs/test.txt \
  --endpoint-url https://cos.twcc.ai \
  --profile twcc-cos

# 下載測試
aws s3 cp s3://studio-outputs/test.txt /tmp/test.txt \
  --endpoint-url https://cos.twcc.ai \
  --profile twcc-cos
cat /tmp/test.txt

# 清理
aws s3 rm s3://studio-outputs/test.txt \
  --endpoint-url https://cos.twcc.ai \
  --profile twcc-cos
```

---

## 7. Cron 排程管理

### 7.1 安裝排程

在 **Base VM** 上執行：

```bash
chmod +x scripts/twcc_setup_cron.sh
bash scripts/twcc_setup_cron.sh
```

預設排程：
- **平日 09:00** — 開啟 GPU VM
- **平日 18:00** — 安全關閉 GPU VM（檢查佇列）

### 7.2 調整排程

```bash
crontab -e
```

範例：改為 08:00 開機、22:00 關機：
```cron
0 8 * * 1-5 /home/ubuntu/studio-core/scripts/twcc_start_gpu.sh >> /home/ubuntu/studio-core/logs/cron_gpu.log 2>&1
0 22 * * 1-5 /home/ubuntu/studio-core/scripts/twcc_stop_gpu.sh >> /home/ubuntu/studio-core/logs/cron_gpu.log 2>&1
```

### 7.3 手動操作

```bash
# 手動開機
bash scripts/twcc_start_gpu.sh

# 手動關機（含安全檢查）
bash scripts/twcc_stop_gpu.sh

# 查看排程日誌
tail -f logs/cron_gpu.log
```

---

## 8. Security Group 設定

### 8.1 Base VM Security Group

| 方向 | 協定 | 埠號 | 來源 | 說明 |
|------|------|------|------|------|
| Inbound | TCP | 80 | TWCC LB CIDR | Nginx (僅 LB 可存取) |
| Inbound | TCP | 6379 | GPU VM 私有 IP | Redis (僅 GPU VM 可存取) |
| Inbound | TCP | 22 | 管理員 IP | SSH |
| Outbound | ALL | ALL | 0.0.0.0/0 | 全部放行 |

### 8.2 GPU VM Security Group

| 方向 | 協定 | 埠號 | 來源 | 說明 |
|------|------|------|------|------|
| Inbound | TCP | 22 | Base VM IP / 管理員 IP | SSH |
| Outbound | ALL | ALL | 0.0.0.0/0 | 全部放行 |

### 8.3 重要安全原則

- **不要** 把 Redis 6379 暴露到公網
- **不要** 把 MySQL 3306 暴露到任何外部來源
- **不要** 把 ComfyUI 8188 暴露到公網（只在 GPU VM localhost 監聽）
- Base VM 的 port 80 **只允許** 來自 TWCC LB 的流量

---

## 9. 健康檢查與監控

### 9.1 健康檢查腳本

```bash
chmod +x scripts/twcc_healthcheck.sh
bash scripts/twcc_healthcheck.sh
```

此腳本會檢查：
- Redis 連線
- MySQL 連線
- COS (S3) 連線
- Worker 心跳
- Nginx 回應
- 任務佇列狀態

### 9.2 關鍵監控指標

| 指標 | 檢查方式 | 警戒值 |
|------|----------|--------|
| Redis 連線 | `redis-cli ping` | 無回應 = 嚴重 |
| Worker 心跳 | `GET worker:heartbeat` | 超過 120s 無更新 |
| 任務佇列長度 | `LLEN job_queue` | > 10 需注意 |
| GPU 記憶體 | `nvidia-smi` | > 90% 需注意 |
| 磁碟空間 | `df -h` | > 85% 需清理 |
| COS 可存取 | S3 HEAD bucket | 失敗 = 嚴重 |

### 9.3 日誌位置

| 服務 | 日誌位置 |
|------|----------|
| Nginx | Docker logs: `docker logs nginx` |
| Flask API | Docker logs: `docker logs api` |
| Redis | Docker logs: `docker logs redis` |
| MySQL | Docker logs: `docker logs mysql` |
| ComfyUI | `journalctl -u comfyui` |
| Worker | `journalctl -u worker` |
| Cron 排程 | `logs/cron_gpu.log` |

---

## 10. 故障排除 FAQ

### Q1: Worker 連不上 Redis

**症狀：** Worker 日誌顯示 `Redis connection failed, retrying...`

**檢查步驟：**
```bash
# 在 GPU VM 上測試
redis-cli -h <BASE_VM_PRIVATE_IP> -p 6379 ping

# 如果不通，檢查：
# 1. Base VM 的 Security Group 是否允許 6379
# 2. Redis 是否 bind 0.0.0.0（docker-compose.base.yml 已設定）
# 3. 防火牆：sudo ufw status
```

### Q2: COS 上傳失敗

**症狀：** Worker 日誌顯示 `S3 upload failed`

**檢查步驟：**
```bash
# 測試 COS 連線
aws s3 ls --endpoint-url https://cos.twcc.ai --profile twcc-cos

# 常見問題：
# 1. endpoint_url 必須指定（不能用 AWS 預設端點）
# 2. Access Key / Secret Key 是否正確
# 3. Bucket 是否存在
# 4. 網路是否能存取 cos.twcc.ai
```

### Q3: 前端圖片載入失敗 (CORS)

**症狀：** 瀏覽器 Console 顯示 CORS 錯誤

**解決：**
```bash
# 確認 CORS 設定
aws s3api get-bucket-cors \
  --bucket studio-outputs \
  --endpoint-url https://cos.twcc.ai \
  --profile twcc-cos

# AllowedOrigins 必須包含你的域名
```

### Q4: ComfyUI 啟動很慢

**預期行為：** ComfyUI 冷啟動需要 20-60 秒載入模型。

Worker 有 **VRAM 暖機** 機制，啟動後會自動發送一個極小的 256x256 測試任務來預熱 GPU。

如果暖機失敗不影響正常使用，只是第一個真實任務可能稍慢。

```bash
# 可用環境變數跳過暖機
# .env 中設定：
SKIP_WARMUP=true
```

### Q5: GPU VM 沒有自動開機

**檢查步驟：**
```bash
# 在 Base VM 上
crontab -l | grep -i studio

# 確認環境變數
cat .env | grep TWCC

# 手動測試
bash scripts/twcc_start_gpu.sh
# 查看輸出是否有錯誤
```

### Q6: 關機腳本不執行關機

**可能原因：** 安全檢查偵測到佇列中還有任務。

```bash
# 查看佇列
docker compose -f docker-compose.base.yml exec redis redis-cli LLEN job_queue

# 強制關機（慎用）
# 手動呼叫 TWCC API
twccli ch vcs -sts stop -s <GPU_VM_ID>
```

### Q7: Nginx 502 Bad Gateway

**原因：** Flask 容器未啟動或尚在啟動中。

```bash
docker compose -f docker-compose.base.yml ps
docker compose -f docker-compose.base.yml logs api
```

---

## 附錄 A：本地 MinIO S3 測試

在本地 Windows 開發環境中，可以用 MinIO 模擬 S3：

```bash
# 啟動 MinIO + Flask + Redis + MySQL
docker compose -f docker-compose.dev-s3.yml --env-file .env.dev-s3 up -d

# MinIO Console
# http://localhost:9001
# 帳號：minioadmin / 密碼：minioadmin

# 測試結束後
docker compose -f docker-compose.dev-s3.yml down
```

---

## 附錄 B：更新部署

```bash
# Base VM
cd ~/studio-core
git pull origin feature/twcc-linux-migration
docker compose -f docker-compose.base.yml up -d --build

# GPU VM
cd ~/studio-core
git pull origin feature/twcc-linux-migration
pip install -r requirements.txt
sudo systemctl restart worker
# 如果 ComfyUI 有更新：
sudo systemctl restart comfyui
```

---

## 附錄 C：災難復原

### 資料庫備份

```bash
# 在 Base VM 上
docker compose -f docker-compose.base.yml exec mysql \
  mysqldump -u root -p${MYSQL_ROOT_PASSWORD} studio_db > backup_$(date +%Y%m%d).sql
```

### Redis 快照

Redis 預設啟用 RDB 快照，資料存放在 `redis_data/dump.rdb`。

### COS 資料

COS 上的圖片/影片具有持久性，無需額外備份。但建議定期透過 `aws s3 sync` 做本地備份。
