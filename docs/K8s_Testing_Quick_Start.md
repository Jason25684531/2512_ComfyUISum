# K8s 快速啟動指南 (5分鐘版)

**如需完整詳細指南，請查看**: [K8s_Comprehensive_Testing_Guide.md](K8s_Comprehensive_Testing_Guide.md)

---

## 一鍵啟動（推薦）

```powershell
cd D:\01_Project\2512_ComfyUISum
.\scripts\k8s_quick_start.ps1
```

💡 腳本會自動：
- ✓ 驗證 K8s 集群
- ✓ 部署所有服務
- ✓ 設置端口轉發
- ✓ 執行健康檢查

**所需時間**: 15-20 分鐘

---

## 手動 5 步啟動

### 步驟 1：驗證前置條件

```powershell
# 檢查 Docker & K8s
docker ps
kubectl cluster-info

# 檢查 ComfyUI 運行
curl.exe http://localhost:8188/system_stats
```

### 步驟 2：部署基礎設施

```powershell
cd D:\01_Project\2512_ComfyUISum
kubectl apply -f k8s/base/
```

### 步驟 3：部署應用層

```powershell
kubectl apply -f k8s/app/
```

### 步驟 4：等待服務就緒

```powershell
kubectl wait --for=condition=ready pod --all --timeout=120s
kubectl get pods
```

### 步驟 5：設置端口轉發（新終端）

```powershell
# 終端 1
kubectl port-forward svc/backend-service 5000:5001

# 終端 2
kubectl port-forward svc/frontend-service 8080:80
```

---

## 驗證系統

```powershell
# 檢查服務
curl.exe http://localhost:5000/health
# 應返回: {"status":"ok",...}

# 打開 Web UI
Start-Process "http://localhost:8080"
```

✅ **完成！系統已就緒**

---

## 常用命令

```powershell
# 查看 Pods 狀態
kubectl get pods -w

# 查看日誌
kubectl logs -l app=backend -f
kubectl logs -l app=worker -f

# 重啟服務
kubectl rollout restart deployment/backend

# 關閉系統
kubectl delete -f k8s/app/
kubectl delete -f k8s/base/

# 進入 Pod 調試
$pod = kubectl get pods -l app=backend -o jsonpath="{.items[0].metadata.name}"
kubectl exec -it $pod -- /bin/bash
```

---

## 故障排除

| 問題 | 快速解決 |
|------|---------|
| Port 被佔用 | Stop-Process -Port 5000 |
| Pod 無法啟動 | `kubectl describe pod <name>` |
| ComfyUI 連接失敗 | 檢查 `http://localhost:8188` |
| Backend 無響應 | 重啟 Port Forward |

---

## 詳細文檔

所有完整說明、高級測試、除錯技巧請參考：
### 📘 [K8s 完整架構、測試與部署指南](K8s_Comprehensive_Testing_Guide.md)

包含：
- ✅ 完整架構設計圖
- ✅ 詳細啟動流程
- ✅ 端到端測試場景
- ✅ Web UI 測試指南
- ✅ 性能基準測試
- ✅ 完整故障排查
- ✅ 前後端整合測試

---

**快速導航**: [首頁](README.md) | [架構文檔](HYBRID_DEPLOYMENT_STRATEGY.md) | [更新日誌](UpdateList.md)
