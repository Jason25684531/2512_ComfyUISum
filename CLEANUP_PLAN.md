# 專案清理建議報告

> **生成時間**: 2026-01-09  
> **目的**: 清理重複配置、廢棄腳本，維持專案結構整潔

---

## 📋 清理概覽

### 清理統計

- **待刪除/歸檔檔案**: 9 個
- **已整合檔案**: 2 個
- **新增統一檔案**: 6 個
- **預計減少檔案數**: 3 個 (9 - 2 - 6 + 2整合 = 3淨減少)

---

## 🗑️ 待刪除/歸檔檔案清單

### 1. 舊 Docker Compose 配置 (2 個)

#### `docker-compose.yml`
- **原因**: 已被 `docker-compose.unified.yml` 取代
- **功能**: Linux 完整堆疊配置 (ComfyUI + Backend + Worker + DB)
- **狀態**: 功能已完全整合到統一配置的 `linux-dev` 和 `linux-prod` profiles
- **建議**: 
  - [ ] 備份為 `docker-compose.yml.backup`
  - [ ] 刪除原檔案
- **風險**: 低 (新配置已測試可用)

#### `docker-compose.dev.yml`
- **原因**: 已被 `docker-compose.unified.yml` 取代
- **功能**: 開發環境配置 (MySQL + Redis)
- **狀態**: 功能已整合到統一配置 (無 profile 時的預設行為)
- **影響**: `scripts/start_all_with_docker.bat` 和 `scripts/monitor_status.bat` 仍引用此檔案
- **建議**:
  - [ ] 先更新引用此檔案的腳本
  - [ ] 備份為 `docker-compose.dev.yml.backup`
  - [ ] 刪除原檔案
- **風險**: 中 (需先更新引用腳本)

---

### 2. 舊環境變數範本 (1 個)

#### `.env.example`
- **原因**: 已被 `.env.unified.example` 取代
- **功能**: 舊環境變數範本
- **狀態**: 新範本更完整，包含三種環境的配置
- **建議**:
  - [ ] 確認無其他文檔引用
  - [ ] 刪除檔案
- **風險**: 低 (新範本更完整)

---

### 3. 已整合文檔 (2 個)

#### `QUICKSTART.md`
- **原因**: 內容已完整整合到 `HYBRID_DEPLOYMENT_STRATEGY.md`
- **功能**: 快速開始指南
- **狀態**: 完全整合，無遺漏
- **建議**:
  - [ ] 刪除檔案
- **風險**: 無

#### `UNIFIED_DEPLOYMENT_GUIDE.md`
- **原因**: 內容已完整整合到 `HYBRID_DEPLOYMENT_STRATEGY.md`
- **功能**: 統一部署指南
- **狀態**: 完全整合，無遺漏
- **建議**:
  - [ ] 刪除檔案
- **風險**: 無

---

### 4. 待更新/淘汰腳本 (4 個)

#### `scripts/start_all_with_docker.bat`
- **原因**: 已被 `scripts/start_unified_windows.bat` 取代
- **功能**: Windows 開發環境啟動 (使用 docker-compose.dev.yml)
- **狀態**: 新腳本功能更完整
- **引用**: 可能被用戶習慣使用
- **建議**:
  - [ ] 保留短期內向後兼容
  - [ ] 在腳本開頭添加棄用警告
  - [ ] 建議用戶遷移到新腳本
  - [ ] 3 個月後刪除
- **風險**: 低 (保留過渡期)

**棄用警告範例**:
```batch
@echo off
echo ========================================
echo   WARNING: This script is DEPRECATED
echo ========================================
echo.
echo This script will be removed in future versions.
echo Please use the new unified deployment:
echo   scripts\start_unified_windows.bat
echo.
echo Press Ctrl+C to cancel, or any key to continue...
pause >nul
echo.
```

#### `scripts/startweb.bat`
- **原因**: Web 服務器功能已由 Backend 提供
- **功能**: 啟動 Python HTTP Server (Port 8000)
- **狀態**: 不再需要 (Backend 在 Port 5000 提供靜態文件)
- **建議**:
  - [ ] 確認無處使用
  - [ ] 刪除檔案
- **風險**: 無

#### `scripts/monitor_status.bat`
- **狀態**: 仍然有用 (監控腳本)
- **問題**: 引用 `docker-compose.dev.yml`
- **建議**:
  - [ ] 保留檔案
  - [ ] 更新為使用 `docker-compose.unified.yml`
- **風險**: 低 (只需更新引用)

#### `scripts/update_ngrok_config.ps1`
- **狀態**: 仍然有用 (Ngrok 配置自動更新)
- **建議**:
  - [ ] 保留檔案 (功能獨立)
- **風險**: 無

---

## ✅ 需要更新的檔案

### 1. `scripts/start_all_with_docker.bat`

**需要更新的行**:
```batch
# 第 24 行
docker-compose -f docker-compose.dev.yml up -d 2>nul
↓ 改為
docker-compose -f docker-compose.unified.yml up -d redis mysql 2>nul

# 或者添加棄用警告（如上述範例）
```

### 2. `scripts/monitor_status.bat`

**需要更新的行**:
```batch
# 第 61 行
docker-compose -f docker-compose.dev.yml ps 2>nul
↓ 改為
docker-compose -f docker-compose.unified.yml ps 2>nul
```

---

## 📊 清理執行計劃

### Phase 1: 立即執行 (低風險)

```batch
# 1. 刪除已整合文檔
del QUICKSTART.md
del UNIFIED_DEPLOYMENT_GUIDE.md

# 2. 刪除不再需要的腳本
del scripts\startweb.bat

# 3. 備份舊環境範本
move .env.example .env.example.backup
```

### Phase 2: 更新引用 (需測試)

```batch
# 1. 更新 monitor_status.bat
# 手動編輯檔案，更新 docker-compose 引用

# 2. 添加棄用警告到 start_all_with_docker.bat
# 手動編輯檔案，在開頭添加警告訊息
```

### Phase 3: 備份舊配置 (需確認新配置穩定)

```batch
# 確認新配置運行 1-2 週後執行

# 1. 備份舊 Docker Compose 配置
move docker-compose.yml docker-compose.yml.backup
move docker-compose.dev.yml docker-compose.dev.yml.backup

# 2. 可選：歸檔到 backup/ 目錄
mkdir backup
move *.backup backup\
```

### Phase 4: 最終清理 (3 個月後)

```batch
# 1. 刪除棄用的啟動腳本
del scripts\start_all_with_docker.bat

# 2. 刪除備份檔案
rmdir /s /q backup
```

---

## 🎯 清理後的專案結構

```
ComfyUIStudio/
├── docker-compose.unified.yml      # ✓ 統一配置
├── .env                            # ✓ 環境變數 (使用中)
├── .env.unified.example            # ✓ 環境變數範本
│
├── scripts/
│   ├── start_unified_windows.bat   # ✓ Windows 統一啟動
│   ├── start_unified_linux.sh      # ✓ Linux 統一啟動
│   ├── start_ngrok.bat             # ✓ Ngrok 啟動
│   ├── update_ngrok_config.ps1     # ✓ Ngrok 配置
│   ├── monitor_status.bat          # ✓ 監控 (已更新)
│   ├── run_stack_test.bat          # ✓ 測試
│   └── test_rate_limit.bat         # ✓ Rate Limit 測試
│
├── README.md                       # ✓ 專案說明 (已更新)
├── HYBRID_DEPLOYMENT_STRATEGY.md   # ✓ 部署策略指南
├── DEPLOYMENT_COMPARISON.md        # ✓ 方案對比
│
└── Update_MD/
    ├── UpdateList.md               # ✓ 更新日誌 (已更新)
    ├── NGROK_SETUP.md              # ✓ Ngrok 指南
    ├── MONITORING_GUIDE.md         # ✓ 監控指南
    └── ...
```

---

## ⚠️ 注意事項

### 執行清理前

1. **確認新配置穩定**
   - 測試 Windows 開發環境
   - 測試 Linux 開發環境
   - 確認所有功能正常

2. **通知團隊成員**
   - 如果是團隊專案，需通知所有成員
   - 提供遷移指南

3. **Git 提交**
   - 在清理前提交當前狀態
   - 建立 tag 標記清理前的版本

### 回滾計劃

如果新配置有問題，可以快速回滾：

```bash
# 恢復舊配置
mv docker-compose.yml.backup docker-compose.yml
mv docker-compose.dev.yml.backup docker-compose.dev.yml
mv .env.example.backup .env.example

# 使用舊腳本
cd scripts
start_all_with_docker.bat
```

---

## 📝 清理執行檢查清單

```
Phase 1: 立即執行
- [ ] 刪除 QUICKSTART.md
- [ ] 刪除 UNIFIED_DEPLOYMENT_GUIDE.md
- [ ] 刪除 scripts/startweb.bat
- [ ] 備份 .env.example

Phase 2: 更新引用
- [ ] 更新 scripts/monitor_status.bat
- [ ] 添加棄用警告到 scripts/start_all_with_docker.bat

Phase 3: 備份舊配置 (1-2週後)
- [ ] 測試新配置穩定性
- [ ] 備份 docker-compose.yml
- [ ] 備份 docker-compose.dev.yml
- [ ] 歸檔到 backup/ 目錄

Phase 4: 最終清理 (3個月後)
- [ ] 刪除 scripts/start_all_with_docker.bat
- [ ] 刪除 backup/ 目錄

文檔更新
- [x] 更新 README.md
- [x] 更新 UpdateList.md
- [ ] 更新其他引用舊檔案的文檔
```

---

**建議**: 按照 Phase 1 → Phase 2 → Phase 3 → Phase 4 的順序執行，每個 Phase 之間留有充足的測試時間。

**最後更新**: 2026-01-09
