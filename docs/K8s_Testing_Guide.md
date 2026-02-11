# Kubernetes 完整測試指南

**版本**: 1.0  
**日期**: 2026-02-11  
**目標**: 提供 ComfyUI Studio K8s 環境的完整啟動、測試和除錯流程

---

## 📋 目錄

1. [前置準備](#前置準備)
2. [快速啟動](#快速啟動)
3. [手動啟動流程](#手動啟動流程)
4. [API 測試](#api-測試)
5. [端到端測試](#端到端測試)
6. [故障排除](#故障排除)
7. [監控與日誌](#監控與日誌)

---

## 前置準備

### 必須運行的服務

| 服務 | 描述 | 檢查命令 |
|------|------|---------|
| Docker Desktop | 容器運行環境 | `docker version` |
| Kubernetes | K8s 叢集 | `kubectl cluster-info` |
| ComfyUI | AI 生成引擎 | 瀏覽器訪問 `http://localhost:8188` |

### 啟動 ComfyUI（必須先啟動）

```powershell
# 進入 ComfyUI 目錄並啟動
D:\02_software\ComfyUI_windows_portable\run_nvidia_gpu.bat

# 等待看到類似輸出：
# To see the GUI go to: http://127.0.0.1:8188
```

**驗證 ComfyUI**:
```powershell
curl.exe http://localhost:8188/system_stats
# 應該回傳 JSON 系統資訊
```

---

## 快速啟動

### 方法 1：使用快速啟動腳本（推薦）

```powershell
# 進入專案目錄
cd D:\01_Project\2512_ComfyUISum

# 執行快速啟動腳本
.\scripts\k8s_quick_start.ps1

# 腳本會自動：
# 1. 檢查 K8s 連接
# 2. 啟動所有服務
# 3. 設置 Port Forwarding
# 4. 執行健康檢查
# 5. 提交測試任務
```

### 方法 2：僅測試模式（服務已運行）

```powershell
.\scripts\k8s_quick_start.ps1 -TestOnly
```

---

## 手動啟動流程

如果快速腳本失敗，可以按照以下步驟手動啟動：

### 步驟 1: 檢查 Kubernetes 狀態

```powershell
# 檢查節點狀態
kubectl get nodes

# 應該看到：
# NAME             STATUS   ROLES           AGE   VERSION
# docker-desktop   Ready    control-plane   XXd   vX.XX.X
```

### 步驟 2: 部署基礎設施

```powershell
# 進入專案目錄
cd D:\01_Project\2512_ComfyUISum

# 應用基礎配置（ConfigMap, Secrets, PVC）
kubectl apply -f k8s/base/

# 應用應用服務（MySQL, Redis, Backend, Worker, Frontend）
kubectl apply -f k8s/app/

# 驗證部署
kubectl get pods -o wide
```

**期望輸出**:
```
NAME                        READY   STATUS    RESTARTS   AGE
mysql-xxx                   1/1     Running   0          2m
redis-xxx                   1/1     Running   0          2m
backend-xxx                 1/1     Running   0          1m
worker-xxx                  1/1     Running   0          1m
frontend-xxx                1/1     Running   0          1m
```

### 步驟 3: 等待服務就緒

```powershell
# 等待所有 Pods 就緒（最多 2 分鐘）
kubectl wait --for=condition=ready pod --all --timeout=120s

# 如果某個服務卡住，單獨檢查
kubectl describe pod <pod-name>
```

### 步驟 4: 設置 Port Forwarding

```powershell
# Backend Port Forward（在新終端執行）
kubectl port-forward svc/backend-service 5000:5001

# Frontend Port Forward（可選，在另一個終端）
kubectl port-forward svc/frontend-service 8080:80

# 保持這些終端運行
```

---

## API 測試

### 測試 1: 健康檢查

```powershell
# 使用 curl.exe（避免 PowerShell 別名衝突）
curl.exe http://localhost:5000/health

# 期望輸出：
# {"status":"ok","redis":"healthy","mysql":"healthy"}
```

**注意**：健康檢查的正確端點是 `/health`，不是 `/api/health`

### 測試 2: 獲取系統指標

```powershell
curl.exe http://localhost:5000/api/metrics

# 期望輸出：
# {"redis":{"status":"connected","queue_length":0},"worker":{"status":"running"},...}
```

### 測試 3: 查詢歷史記錄

```powershell
curl.exe http://localhost:5000/api/history?page=1&limit=10

# 期望輸出：
# {"jobs":[],"total":0,"page":1,"total_pages":0}
```

---

## 端到端測試

### 測試場景 1: Text to Image 生成

#### 步驟 1: 提交任務

```powershell
# 創建 JSON 請求
$body = @{
    workflow = "text_to_image"
    prompt = "a beautiful sunset over mountains, digital art"
    negative_prompt = "blurry, low quality"
    model = "turbo_fp8"
    aspect_ratio = "16:9"
    batch_size = 1
    seed = -1
} | ConvertTo-Json

# 提交任務
$response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body

# 保存 Job ID
$jobId = $response.job_id
Write-Host "Job ID: $jobId"
```

#### 步驟 2: 輪詢任務狀態

```powershell
# 每 3 秒查詢一次狀態
while ($true) {
    $status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$jobId"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Status: $($status.status) | Progress: $($status.progress)%"
    
    if ($status.status -in @("completed", "failed")) {
        break
    }
    
    Start-Sleep -Seconds 3
}

# 查看最終結果
if ($status.status -eq "completed") {
    Write-Host "✅ 任務完成！"
    Write-Host "   圖片 URL: http://localhost:5000$($status.image_url)"
} else {
    Write-Host "❌ 任務失敗: $($status.error)"
}
```

#### 步驟 3: 下載生成圖片

```powershell
# 下載圖片到桌面
$imageUrl = "http://localhost:5000$($status.image_url)"
$outputPath = "$env:USERPROFILE\Desktop\comfyui_output.png"

Invoke-WebRequest -Uri $imageUrl -OutFile $outputPath
Write-Host "圖片已保存到: $outputPath"

# 開啟圖片
Start-Process $outputPath
```

### 測試場景 2: 完整 Web UI 測試

```powershell
# 在瀏覽器開啟前端
Start-Process "http://localhost:8080"

# 手動測試流程：
# 1. 進入 "Text to Image" 工作區
# 2. 輸入 Prompt: "a futuristic city at night"
# 3. 選擇 Aspect Ratio: 16:9
# 4. 點擊 "生成" 按鈕
# 5. 觀察進度條
# 6. 等待圖片顯示
# 7. 點擊下載按鈕
```

---

## 故障排除

### 問題 1: Backend 無法連接

**症狀 A - 端口佔用**:
```
Unable to listen on port 5000: bind: Only one usage of each socket address...
```

**解決方案**:

```powershell
# 檢查哪個進程佔用 5000 端口
Get-NetTCPConnection -LocalPort 5000 | Select-Object State, OwningProcess
Get-Process -Id (Get-NetTCPConnection -LocalPort 5000).OwningProcess

# 停止佔用端口的進程（請確認是什麼進程再停止）
Stop-Process -Id <ProcessID> -Force

# 重新啟動 port-forward
kubectl port-forward svc/backend-service 5000:5001
```

**症狀 B - API endpoint not found**:
```
curl : { "error": "API endpoint not found" }
```

**解決方案**:

```powershell
# 使用正確的端點路徑：
# 健康檢查：/health（不是 /api/health）
curl.exe http://localhost:5000/health

# 其他 API 端點都有 /api/ 前綴：
curl.exe http://localhost:5000/api/generate
curl.exe http://localhost:5000/api/history
curl.exe http://localhost:5000/api/metrics

# 檢查 Backend Pod 狀態
kubectl get pods -l app=backend

# 查看 Backend 日誌
kubectl logs -l app=backend --tail=50

# 確認 Port Forward 運行中
Get-Process | Where-Object {$_.ProcessName -eq "kubectl"}

# 如果沒有，重新啟動
Stop-Process -Name kubectl -Force -ErrorAction SilentlyContinue
Start-Process kubectl -ArgumentList "port-forward svc/backend-service 5000:5001" -WindowStyle Hidden
```

### 問題 2: Worker 無法連接 ComfyUI

**症狀**:
```
[ERROR] [worker] ❌ 處理錯誤: 無法連接 ComfyUI
```

**解決方案**:

```powershell
# 檢查 ComfyUI 是否運行
curl.exe http://localhost:8188/system_stats

# 測試 Worker 到 ComfyUI 的連接
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $workerPod -- python -c "
import requests
try:
    r = requests.get('http://comfyui-bridge:8188/system_stats', timeout=5)
    print('✅ ComfyUI 連接成功')
except Exception as e:
    print(f'❌ 連接失敗: {e}')
"

# 查看 Worker 環境變數
kubectl exec -it $workerPod -- env | Select-String "COMFYUI"
```

### 問題 3: 任務卡在 pending 狀態

**症狀**:
任務提交後長時間無進度

**解決方案**:

```powershell
# 檢查 Redis 隊列長度
$redisPod = kubectl get pods -l app=redis -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $redisPod -- redis-cli LLEN job_queue

# 查看 Worker 日誌
kubectl logs -l app=worker --tail=100 -f

# 檢查 Worker 心跳
kubectl exec -it $redisPod -- redis-cli GET worker:heartbeat

# 如果 Worker 無回應，重啟
kubectl rollout restart deployment/worker
```

### 問題 4: ComfyUIworkflow 檔案不存在

**症狀**:
```
[ERROR] [worker] Workflow 檔案不存在: /app/ComfyUIworkflow/xxx.json
```

**解決方案**:

```powershell
# 驗證 Worker 映像檔包含 workflow 檔案
$workerPod = kubectl get pods -l app=worker -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $workerPod -- ls -l /app/ComfyUIworkflow

# 如果檔案不存在，重新建立映像檔
cd D:\01_Project\2512_ComfyUISum
docker build -f worker/Dockerfile -t studiocore-worker:latest .

# 強制重啟 Pod
kubectl delete pod -l app=worker
```

---

## 監控與日誌

### 即時監控所有服務

```powershell
# 監控所有 Pods 狀態（實時更新）
kubectl get pods -w

# 監控 Backend 日誌
kubectl logs -l app=backend --tail=50 -f

# 監控 Worker 日誌
kubectl logs -l app=worker --tail=50 -f
```

### 查看資源使用情況

```powershell
# 查看 Pod 資源使用
kubectl top pods

# 查看節點資源
kubectl top nodes

# 查看 PVC 使用情況
kubectl get pvc
```

### 導出日誌到文件

```powershell
# 導出所有服務日誌
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
kubectl logs -l app=backend --tail=500 > "logs\k8s_backend_$timestamp.log"
kubectl logs -l app=worker --tail=500 > "logs\k8s_worker_$timestamp.log"
kubectl logs -l app=mysql --tail=500 > "logs\k8s_mysql_$timestamp.log"
kubectl logs -l app=redis --tail=500 > "logs\k8s_redis_$timestamp.log"

Write-Host "日誌已導出到 logs\ 目錄"
```

---

## 完整測試檢查清單

使用此清單確保系統完全正常運行：

### ✅ 基礎設施檢查

- [ ] Docker Desktop 正在運行
- [ ] Kubernetes 叢集可連接 (`kubectl cluster-info`)
- [ ] ComfyUI 正在運行 (`http://localhost:8188`)
- [ ] 所有 Pods 狀態為 Running (`kubectl get pods`)

### ✅ 服務連接檢查

- [ ] Backend 健康檢查通過 (`/api/health`)
- [ ] Redis 可連接（Backend 日誌無錯誤）
- [ ] MySQL 可連接（Backend 日誌無錯誤）
- [ ] Worker 連接到 ComfyUI（Worker 日誌顯示 "✅ ComfyUI 連接成功"）

### ✅ 功能測試

- [ ] 提交 Text to Image 任務成功
- [ ] 任務狀態從 pending → processing → completed
- [ ] 生成的圖片可以訪問和下載
- [ ] 歷史記錄可以查詢
- [ ] Web UI 可以正常使用

### ✅ 性能檢查

- [ ] API 響應時間 < 500ms
- [ ] 圖片生成時間合理（依 GPU 而定）
- [ ] 無異常錯誤日誌
- [ ] 資源使用率正常（CPU < 80%, Memory < 80%）

---

## 進階測試腳本

### 壓力測試：連續提交 10 個任務

```powershell
# 連續提交 10 個任務
$jobs = @()
for ($i = 1; $i -le 10; $i++) {
    $body = @{
        workflow = "text_to_image"
        prompt = "test image $i: a beautiful landscape"
        model = "turbo_fp8"
        aspect_ratio = "1:1"
        batch_size = 1
        seed = -1
    } | ConvertTo-Json
    
    $response = Invoke-RestMethod -Uri "http://localhost:5000/api/generate" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body
    
    $jobs += $response.job_id
    Write-Host "[$i/10] 提交成功: $($response.job_id)"
}

# 等待所有任務完成
Write-Host "`n等待任務完成..."
$completed = 0
while ($completed -lt 10) {
    $completed = 0
    foreach ($jobId in $jobs) {
        $status = Invoke-RestMethod -Uri "http://localhost:5000/api/status/$jobId"
        if ($status.status -in @("completed", "failed")) {
            $completed++
        }
    }
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 完成: $completed/10"
    Start-Sleep -Seconds 5
}

Write-Host "✅ 所有任務已完成！"
```

---

## 快速命令參考

```powershell
# 重啟所有服務
kubectl rollout restart deployment/backend deployment/worker deployment/frontend

# 清理所有資源
kubectl delete -f k8s/app/
kubectl delete -f k8s/base/

# 重新部署
kubectl apply -f k8s/base/
kubectl apply -f k8s/app/

# 進入 Pod 交互式終端
kubectl exec -it <pod-name> -- /bin/bash

# 查看 Service 端點
kubectl get endpoints

# 描述 Pod 詳細信息
kubectl describe pod <pod-name>
```

---

## 相關文件

- [README.md](../README.md) - 專案完整文檔
- [UpdateList.md](UpdateList.md) - 更新日誌
- [HYBRID_DEPLOYMENT_STRATEGY.md](../HYBRID_DEPLOYMENT_STRATEGY.md) - 混合部署策略

---

**最後更新**: 2026-02-11  
**維護者**: ComfyUI Studio Team
