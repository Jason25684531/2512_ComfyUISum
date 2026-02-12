# Worker 檔案複製失敗問題修復指南

## 問題描述

### 症狀
Worker 日誌顯示任務完成，但所有輸出檔案無法複製：

```log
[07:30:45] [INFO] [worker] [Job: 4dd431f0-ba2b-443c-85f7-959bc45ab7cb] 📷 收到 2 張輸出圖片
[07:30:45] [INFO] [worker] [Job: 4dd431f0-ba2b-443c-85f7-959bc45ab7cb] 選擇有子目錄的檔案: 文生圖_00265_.png (subfolder: 集成應用1222)
[07:30:45] [WARNING] [worker] [Job: 4dd431f0-ba2b-443c-85f7-959bc45ab7cb] ⚠️ 第一選擇失敗，嘗試其他檔案...
[07:30:45] [WARNING] [worker] [Job: 4dd431f0-ba2b-443c-85f7-959bc45ab7cb] ⚠️ 任務完成，但所有輸出檔案都無法複製
```

### 根本原因

**K8s 環境中缺少 Volume 掛載配置！**

Worker Pod 無法存取：1. **ComfyUI 輸出目錄**（`C:\ComfyUI_windows_portable\ComfyUI\output`）- 無法讀取 ComfyUI 生成的圖片
2. **storage/outputs 目錄**（`D:\01_Project\2512_ComfyUISum\storage\outputs`）- 無法儲存複製後的圖片

導致 Worker 找不到檔案，前端最終無法顯示圖片。

---

## 修復方案

### 1. 修改 Worker 部署配置

**檔案**：`k8s/app/20-worker.yaml`

#### 1.1 添加 volumeMounts

```yaml
        volumeMounts:
        # 1. ComfyUI 輸出目錄 (讀取生成的圖片)
        - name: comfyui-output
          mountPath: /comfyui/output
          readOnly: true  # Worker 只需讀取權限
        # 2. storage/outputs 目錄 (儲存複製後的圖片)
        - name: storage-outputs
          mountPath: /app/storage/outputs
        # 3. ComfyUI workflow 配置目錄 (讀取 workflow JSON)
        - name: workflows
          mountPath: /app/ComfyUIworkflow
          readOnly: true
```

#### 1.2 添加 volumes 定義

```yaml
      volumes:
      # ComfyUI 輸出目錄 (主機路徑)
      - name: comfyui-output
        hostPath:
          path: C:\ComfyUI_windows_portable\ComfyUI\output
          type: Directory
      # storage/outputs 目錄 (專案路徑)
      - name: storage-outputs
        hostPath:
          path: D:\01_Project\2512_ComfyUISum\storage\outputs
          type: DirectoryOrCreate
      # Workflow 配置目錄
      - name: workflows
        hostPath:
          path: D:\01_Project\2512_ComfyUISum\ComfyUIworkflow
          type: Directory
```

### 2. 修改 Backend 部署配置

**檔案**：`k8s/app/10-backend.yaml`

Backend 也需要掛載 storage 目錄以提供輸出檔案給前端：

```yaml
        volumeMounts:
        # storage 目錄 (讀取/提供輸出檔案給前端)
        - name: storage-outputs
          mountPath: /app/storage/outputs
        - name: storage-inputs
          mountPath: /app/storage/inputs
      volumes:
      # storage/outputs 目錄 (專案路徑)
      - name: storage-outputs
        hostPath:
          path: D:\01_Project\2512_ComfyUISum\storage\outputs
          type: DirectoryOrCreate
      # storage/inputs 目錄 (專案路徑)
      - name: storage-inputs
        hostPath:
          path: D:\01_Project\2512_ComfyUISum\storage\inputs
          type: DirectoryOrCreate
```

### 3. 更新 Worker 配置邏輯

**檔案**：`worker/src/config.py`

修改 COMFYUI_OUTPUT_DIR 自動偵測 K8s 環境：

```python
COMFYUI_OUTPUT_DIR = Path(os.getenv(
    "COMFYUI_OUTPUT_DIR",
    "/comfyui/output" if os.path.exists("/comfyui/output") else str(COMFYUI_ROOT / "output")
))
```

這樣在 K8s 環境中會使用 `/comfyui/output`，本地開發時使用 `COMFYUI_ROOT / "output"`。

---

## 完整重啟與測試流程

### 階段 1：停止所有服務

```powershell
# 1. 停止 K8s 部署
kubectl delete deployment backend worker

# 2. 等待 Pod 終止 (約 10-30 秒)
kubectl get pods -w

# 3. 驗證所有 Pod 已停止
kubectl get pods
# 應該只看到 redis、mysql 等基礎服務
```

### 階段 2：重建 Docker 映像檔 (非必要，但建議)

如果修改了 Worker 或 Backend 程式碼，需要重建映像檔：

```powershell
# 重建 Backend 映像
docker build -t studiocore-backend:latest -f backend/Dockerfile .

# 重建 Worker 映像
docker build -t studiocore-worker:latest -f worker/Dockerfile .

# 驗證映像已建立
docker images | findstr studiocore
```

### 階段 3：重新部署服務

```powershell
# 1. 按順序部署
kubectl apply -f k8s/base/01-redis.yaml
kubectl apply -f k8s/base/04-comfyui-bridge.yaml
kubectl apply -f k8s/base/05-mysql.yaml
kubectl apply -f k8s/app/00-configmap.yaml

# 2. 部署應用服務 (包含新的 Volume 配置)
kubectl apply -f k8s/app/10-backend.yaml
kubectl apply -f k8s/app/20-worker.yaml

# 3. 驗證部署狀態
kubectl get deployments
kubectl get pods

# 4. 等待所有 Pod 進入 Running 狀態 (約 30-60 秒)
kubectl get pods -w
```

### 階段 4：驗證 Volume 掛載

```powershell
# 1. 進入 Worker Pod 檢查掛載點
kubectl exec -it deployment/worker -- /bin/sh

# 在 Pod 內執行：
ls -la /comfyui/output
ls -la /app/storage/outputs
ls -la /app/ComfyUIworkflow
exit

# 預期結果：
# - /comfyui/output 應該顯示 ComfyUI 生成的圖片檔案
# - /app/storage/outputs 應該是空的或有之前的輸出
# - /app/ComfyUIworkflow 應該顯示 workflow JSON 檔案
```

### 階段 5：檢查服務日誌

```powershell
# 查看 Worker 日誌 (即時監控)
kubectl logs -l app=worker -f

# 查看 Backend 日誌
kubectl logs -l app=backend -f

# 預期結果：
# - Worker 應該顯示「已啟動」訊息
# - Backend 應該顯示「已連接 Redis」、「已連接資料庫」
```

### 階段 6：測試任務提交

#### 6.1 設置 Port Forward

```powershell
# 在新的 PowerShell 視窗中執行
kubectl port-forward service/backend-service 5001:5001

# 在另一個視窗中設置 Frontend Port Forward
kubectl port-forward service/frontend-service 8080:80
```

#### 6.2 開啟前端測試

1. 開啟瀏覽器訪問：`http://localhost:8080`
2. 選擇任一工具（例如：Text to Image）
3. 輸入提示詞並提交任務
4. 觀察 Worker 日誌變化

#### 6.3 觀察 Worker 日誌

在 `kubectl logs -l app=worker -f` 視窗中，應該看到類似：

```log
[INFO] [worker] [Job: abc123] 📊 輸出統計: videos=0, gifs=0, images=1
[INFO] [worker] [Job: abc123] 📷 收到 1 張輸出圖片
[INFO] [worker] [Job: abc123] ✓ 過濾後剩餘 1 個真實輸出
[ComfyClient] 檢查檔案路徑: /comfyui/output/文生圖_00266_.png
[ComfyClient] ✓ 已複製檔案: /comfyui/output/文生圖_00266_.png -> /app/storage/outputs/abc123.png
[INFO] [worker] ✓ Redis 狀態更新: abc123 -> finished
[INFO] [worker] ✓ MySQL 狀態同步: abc123 -> finished
[INFO] [worker] [Job: abc123] ✅ 任務完成，輸出 (image): /outputs/abc123.png
```

**關鍵指標**：
- ✅ `檢查檔案路徑: /comfyui/output/...` - 找到檔案
- ✅ `已複製檔案: ... -> /app/storage/outputs/...` - 複製成功
- ✅ `✅ 任務完成，輸出 (image): /outputs/...` - 有輸出路徑

如果看到：
- ❌ `找不到輸出檔案: ...` - Volume 掛載失敗
- ❌ `⚠️ 任務完成，但所有輸出檔案都無法複製` - 所有路徑都失敗

#### 6.4 驗證前端顯示

1. 前端應該顯示生成的圖片
2. Gallery 頁面應該顯示歷史記錄
3. 圖片可以正常下載

---

## MinIO 配置 (可選)

目前系統配置為使用 MinIO (S3 兼容儲存)，但可能尚未啟用或測試。

### 檢查 MinIO 狀態

```powershell
# 檢查 MinIO 是否運行
kubectl get pods -l app=minio
kubectl logs -l app=minio

# 如果沒有運行，部署 MinIO
kubectl apply -f k8s/base/03-minio.yaml
```

### MinIO 相關問題

**目前配置**（`k8s/app/00-configmap.yaml`）：
```yaml
STORAGE_TYPE: "s3"
S3_ENDPOINT_URL: "http://minio-service:9000"
```

**問題**：
1. MinIO 可能未正常運行
2. MinIO 的 Bucket 可能未創建
3. Worker 上傳到 MinIO 可能失敗（但本地檔案仍然保存）

### 臨時解決方案：改用本地儲存

如果 MinIO 有問題，可以暫時改用本地儲存：

```powershell
# 修改 ConfigMap
kubectl edit configmap app-config

# 將 STORAGE_TYPE 改為 "local"
# 儲存後需要重啟 Pod
kubectl rollout restart deployment/backend
kubectl rollout restart deployment/worker
```

### MinIO 完整測試

```powershell
# 1. 部署 MinIO
kubectl apply -f k8s/base/03-minio.yaml

# 2. 等待 MinIO 啟動
kubectl wait --for=condition=ready pod -l app=minio --timeout=60s

# 3. Port Forward MinIO Console
kubectl port-forward service/minio-console-service 9001:9001

# 4. 訪問 MinIO Console
# 瀏覽器開啟：http://localhost:9001
# 帳號：minioadmin
# 密碼：minioadmin

# 5. 檢查 Bucket 是否存在
# 在 MinIO Console 中應該看到 "comfyui-outputs" bucket
```

---

## 故障排查

### 問題 1：Worker 仍然找不到檔案

**症狀**：
```log
[ComfyClient] 找不到輸出檔案: /comfyui/output/xxx.png
```

**檢查步驟**：

1. **驗證 ComfyUI 是否生成檔案**
   ```powershell
   # 在主機上檢查
   dir C:\ComfyUI_windows_portable\ComfyUI\output
   ```

2. **驗證 Volume 掛載**
   ```powershell
   kubectl exec -it deployment/worker -- ls -la /comfyui/output
   ```
   
   如果看到 `No such file or directory`，表示掛載失敗。

3. **檢查路徑分隔符**
   - Windows 路徑使用 `\`，但 K8s YAML 需要 `\\` 或 `/`
   - 確認 `20-worker.yaml` 中的 `path: C:\ComfyUI_windows_portable\ComfyUI\output`

4. **檢查 Docker Desktop 設置**
   - 開啟 Docker Desktop
   - Settings → Resources → File sharing
   - 確認 `C:\` 和 `D:\` 都已添加到共享列表中

### 問題 2：權限錯誤

**症狀**：
```log
[ComfyClient] ✗ 複製檔案失敗: Permission denied
```

**解決方案**：

```powershell
# 修改目錄權限（在主機上執行）
icacls "D:\01_Project\2512_ComfyUISum\storage\outputs" /grant Everyone:F /T
```

### 問題 3：Pod 無法啟動

**症狀**：
```powershell
kubectl get pods
# worker-xxx   0/1   CrashLoopBackOff
```

**檢查步驟**：

```powershell
# 查看 Pod 詳細狀態
kubectl describe pod -l app=worker

# 查看 Pod 日誌
kubectl logs -l app=worker --tail=50

# 常見原因：
# - Volume 掛載路徑不存在
# - Docker Desktop File Sharing 未啟用
# - YAML 配置語法錯誤
```

### 問題 4：檔名包含中文字符

**症狀**：
```log
選擇有子目錄的檔案: 文生圖_00265_.png (subfolder: 集成應用1222)
⚠️ 第一選擇失敗
```

**原因**：中文路徑編碼問題

**解決方案**：
1. 確保 Python 環境使用 UTF-8 編碼
2. Worker Dockerfile 中添加：
   ```dockerfile
   ENV PYTHONIOENCODING=utf-8
   ENV LANG=C.UTF-8
   ```

3. 重建 Worker 映像檔

---

## 驗證清單

完成修復後，逐項驗證：

- [ ] Worker Pod 成功啟動
- [ ] Worker 可以存取 `/comfyui/output` 目錄
- [ ] Worker 可以寫入 `/app/storage/outputs` 目錄
- [ ] Backend Pod 成功啟動
- [ ] Backend 可以讀取 `/app/storage/outputs` 目錄
- [ ] 提交測試任務成功
- [ ] Worker 日誌顯示「✓ 已複製檔案」
- [ ] Worker 日誌顯示「✅ 任務完成，輸出 (image): /outputs/xxx.png」
- [ ] Redis 狀態包含 `image_url`
- [ ] 資料庫 `jobs.output_path` 有值
- [ ] 前端顯示生成的圖片
- [ ] Gallery 頁面顯示歷史記錄

---

## 修改的檔案清單

1. ✅ `k8s/app/20-worker.yaml` - Worker 部署配置（添加 Volume 掛載）
2. ✅ `k8s/app/10-backend.yaml` - Backend 部署配置（添加 Volume 掛載）
3. ✅ `worker/src/config.py` - Worker 配置邏輯（K8s 路徑適配）
4. ✅ `docs/Fix_Worker_File_Copy_Issue.md` - 完整修復文件（本文件）

---

## 後續建議

1. **MinIO 完整整合**
   - 創建自動初始化 Bucket 的 Job
   - 驗證 S3 上傳/下載功能
   - 前端改為從 MinIO 讀取圖片（而非本地檔案）

2. **監控告警**
   - 添加 Worker 檔案複製失敗的告警
   - 監控 storage/outputs 目錄大小
   - 定期清理過期檔案

3. **效能優化**
   - 考慮使用 PersistentVolumeClaim 代替 hostPath
   - 實施 Storage Class 自動管理
   - 添加備份機制

4. **測試覆蓋**
   - 添加 E2E 測試驗證完整流程
   - 測試不同檔案格式（PNG、MP4、GIF）
   - 測試中文路徑處理

---

**狀態**：✅ 配置修復完成，等待測試驗證  
**優先級**：高（阻斷核心功能）  
**影響範圍**：所有算圖任務的輸出檔案處理

