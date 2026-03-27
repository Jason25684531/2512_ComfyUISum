# TWCC 實機部署前逐步檢查清單

> 用途：在真正登入 TWCC 開始部署之前，逐步確認所有必要條件、配置、檔案與指令都已就緒。

---

## 使用方式

每一項都應在進入下一步前完成。不要跳步，因為 TWCC 雙 VM 部署的錯誤通常來自「前一層沒準備好」。

---

## Phase 0：本地檔案與 OpenSpec 狀態

- [ ] 確認目前 change 已完成並可追溯
  指令：`openspec list`
  預期：`harden-twcc-mvp` 顯示為 `Complete`

- [ ] 確認 OpenSpec 驗證通過
  指令：`openspec validate harden-twcc-mvp --strict`
  預期：strict validate 成功

- [ ] 確認核心配置檔存在
  檔案：`docker-compose.base.yml`、`docker-compose.unified.yml`、`nginx/nginx.twcc.conf`、`.env.twcc`

---

## Phase 1：本地靜態驗證

- [ ] 驗證 Base VM compose 語法
  指令：`docker compose -f docker-compose.base.yml config`

- [ ] 驗證 unified compose 語法
  指令：`docker compose -f docker-compose.unified.yml config`

- [ ] 驗證 Python 受影響檔案語法
  指令：`python -m py_compile worker/src/config.py worker/src/comfy_client.py backend/src/app.py`

- [ ] 確認 Nginx 設定具備必要補強
  檢查：`50M`、`300s`、`/ws/`、`server_tokens off`

---

## Phase 2：TWCC 資源前置條件

- [ ] 已建立 Base VM
  需要：對外 IP、私網 IP、SSH 金鑰

- [ ] 已建立 GPU VM
  需要：GPU 規格、私網 IP、SSH 金鑰

- [ ] 已建立 Load Balancer
  需要：對外域名或公開入口

- [ ] 已建立 COS Bucket
  需要：Bucket 名稱、Access Key、Secret Key、Endpoint

- [ ] 已建立 Security Group / ACL
  檢查：
  1. Base VM 可被 LB 存取 80
  2. GPU VM 可連 Base VM 的 Redis / MySQL
  3. GPU VM 僅對管理者開放 SSH

---

## Phase 3：環境變數與敏感資訊

- [ ] `.env.twcc` 已填入真實值
  必填：`REDIS_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`DB_PASSWORD`、`SECRET_KEY`

- [ ] `.env.twcc` 已設定 COS 參數
  必填：`S3_ENDPOINT`、`S3_BUCKET`、`S3_ACCESS_KEY`、`S3_SECRET_KEY`

- [ ] `.env.twcc` 已設定 TWCC 參數
  必填：`TWCC_API_KEY`、`TWCC_PROJECT_ID`、`TWCC_GPU_VM_ID`

- [ ] `.env.twcc` 已設定 timeout 參數
  建議：`COMFY_HTTP_TIMEOUT=300`、`WORKER_TIMEOUT=3600`

- [ ] `.env.twcc` 已確認服務名與路徑
  檢查：`TWCCLI_PATH`、`COMFY_HOST=127.0.0.1`、`COMFYUI_HOST=127.0.0.1`

---

## Phase 4：Base VM 上線前檢查

- [ ] Base VM 已安裝 Docker 與 Compose plugin

- [ ] 已把專案同步到 Base VM

- [ ] Base VM 使用的執行主檔是 `docker-compose.base.yml`

- [ ] 前端與 Nginx 檔案都在正確路徑
  檢查：`frontend/`、`nginx/nginx.twcc.conf`

- [ ] 初次部署前已確認資料庫初始化策略
  有 schema 就先只起 mysql，再匯入 schema

---

## Phase 5：GPU Node 上線前檢查

- [ ] GPU VM 已安裝 Python 3.10+ 與 NVIDIA 驅動

- [ ] GPU VM 上的 ComfyUI 路徑準備完成
  預期：`/opt/comfyui`

- [ ] GPU VM 上的 Worker 路徑準備完成
  預期：`/opt/studio-worker`

- [ ] 模型路徑已存在或已規劃
  預期：`/data/models`

- [ ] 已確認 `studio-worker.service` 才是 Worker 的正式 service 名稱

- [ ] 若 Base VM 私網 IP 有變更，已重新生成或更新 worker unit 中的 REDIS/DB host

---

## Phase 6：首次啟動前測試清單

- [ ] Base VM 能從本機 SSH 登入
- [ ] GPU VM 能從本機 SSH 登入
- [ ] GPU VM 能 ping 到 Base VM 私網 IP
- [ ] Base VM 能回應 `curl http://localhost/health`
- [ ] GPU VM 的 `curl http://127.0.0.1:8188/system_stats` 有預期回應
- [ ] 若要用 Cron，自動化腳本已存在並有執行權限
  檔案：`scripts/twcc_start_gpu.sh`、`scripts/twcc_stop_gpu.sh`、`scripts/twcc_setup_cron.sh`

---

## Phase 7：正式啟動前最後確認

- [ ] 服務名稱確認完畢
  1. `comfyui`
  2. `studio-worker`

- [ ] 健康檢查命令確認完畢
  1. Base VM：`bash scripts/twcc_healthcheck.sh`
  2. OpenSpec：`openspec validate harden-twcc-mvp --strict`

- [ ] 已準備正式上線 SOP
  文件：`docs/TWCC_PRODUCTION_LAUNCH_SOP.md`

---

## 完成判定

當且僅當以下三條都成立，才進入正式部署：

1. OpenSpec 與本地靜態驗證全通過
2. TWCC 雙 VM、COS、LB、Security Group 都已就緒
3. `.env.twcc`、Base VM、GPU VM、systemd 與檢查腳本都已對齊