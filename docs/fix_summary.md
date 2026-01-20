# Worker 輸出問題修復總結

## 執行時間
2026-01-19 16:36

## 問題背景

Worker 日誌顯示三個主要問題：
1. ❌ 輸出檔案路徑不匹配 - Worker 找不到 ComfyUI 的輸出文件
2. ❌ LoadImage 節點無法讀取上傳的圖片 - "Invalid image file" 錯誤
3. ❌ 只返回臨時預覽圖，沒有最終輸出 - type: 'temp' 文件處理錯誤

---

## 已實施的修復

### 1. ✅ 更新環境配置（避免硬編碼路徑）

**文件**: `.env`

**變更**:
- 將 ComfyUI 路徑從 `D:/02_software/ComfyUI_windows_portable` 更新為 `C:/ComfyUI_windows_portable`
- 移除硬編碼的 `COMFYUI_INPUT_DIR` 和 `COMFYUI_OUTPUT_DIR`（由程式自動拼接）
- 只保留 `COMFYUI_ROOT` 環境變數，遵循 DRY 原則

**配置示例**:
```env
COMFYUI_ROOT=C:/ComfyUI_windows_portable/ComfyUI
COMFY_HOST=127.0.0.1
COMFY_PORT=8188
```

**優點**:
- ✅ 不再硬編碼絕對路徑
- ✅ 支持跨環境部署（Windows/Linux/Docker）
- ✅ 單一真實來源（SSOT）

---

### 2. ✅ 增強圖片保存可靠性

**文件**: `worker/src/main.py` - `save_base64_image()` 函數

**變更**:
1. 添加 `f.flush()` 和 `os.fsync()` 確保寫入磁碟
2. 驗證檔案是否存在和大小是否正確
3. 使用 PIL 重新開啟圖片驗證可讀性
4. 添加 100ms 延遲確保檔案系統完成 I/O 操作

**代碼片段**:
```python
with open(filepath, "wb") as f:
    f.write(image_bytes)
    f.flush()  # 確保寫入磁碟
    os.fsync(f.fileno())  # 強制同步到磁碟

# 驗證檔案可讀性
if not filepath.exists():
    raise FileNotFoundError(f"檔案寫入後無法找到: {filepath}")

# PIL 驗證
with Image.open(filepath) as test_img:
    test_img.verify()

# 短暫延遲
time.sleep(0.1)
```

**解決的問題**:
- ✅ LoadImage 節點能正確讀取上傳的圖片
- ✅ 避免緩衝區未刷新導致的讀取失敗
- ✅ 提前發現檔案寫入錯誤

---

### 3. ✅ 改進輸出檔案處理邏輯

**文件**: `worker/src/comfy_client.py` - `copy_output_file()` 函數

**變更**:
1. 新增 `file_type` 參數支持 `'output'` 和 `'temp'` 兩種類型
2. 根據 `file_type` 自動選擇來源目錄（`ComfyUI/output/` 或 `ComfyUI/temp/`）
3. 添加備用路徑檢查機制（多重容錯）
4. 詳細的路徑檢查日誌

**函數簽名**:
```python
def copy_output_file(
    self, 
    filename: str, 
    subfolder: str = "",
    file_type: str = "output",  # 新增參數
    job_id: str = None
) -> Optional[str]:
```

**備用路徑檢查順序**:
1. 主路徑（根據 file_type 決定）
2. Output 根目錄（如果有 subfolder）
3. Temp 目錄（如果 file_type 不是 temp）
4. 交叉檢查（temp ↔ output）

**解決的問題**:
- ✅ 能正確處理 type: 'temp' 的文件
- ✅ 找不到文件時自動嘗試備用路徑
- ✅ 提供詳細的路徑檢查日誌方便除錯

---

### 4. ✅ 過濾臨時預覽圖

**文件**: `worker/src/main.py` - `process_job()` 函數

**變更**:
1. 過濾掉 `type: 'temp'` 的臨時預覽圖
2. 只處理真實輸出（type: 'output' 或無 type 屬性）
3. 如果沒有真實輸出，記錄警告並使用臨時圖作為後備
4. 在調用 `copy_output_file` 時傳遞正確的 `file_type`

**代碼片段**:
```python
# 過濾掉臨時預覽圖
real_outputs = [item for item in output_list if item.get("type") != "temp"]

if not real_outputs:
    logger.warning("⚠️ 只有臨時預覽圖，沒有真實輸出")
    # 使用臨時預覽圖作為後備
    real_outputs = output_list

# 複製時傳遞 file_type
file_type = selected_file.get("type", "output")
new_filename = client.copy_output_file(
    filename=selected_file.get("filename"),
    subfolder=selected_file.get("subfolder", ""),
    file_type=file_type,  # 傳遞類型
    job_id=job_id
)
```

**解決的問題**:
- ✅ 不再返回 SigmasPreview 等臨時預覽圖
- ✅ 自動識別並返回最終輸出圖片
- ✅ 提供詳細的過濾日誌

---

## 測試建議

### 1. 重啟 Worker

為了使配置生效，需要重啟 Worker：

```powershell
# 按 Ctrl+C 停止當前 Worker，然後重新啟動
.\venv\Scripts\python.exe worker\src\main.py
```

### 2. 測試各個 Workflow

建議按以下順序測試：

#### Test 1: text_to_image
- 目的：驗證基礎文生圖功能
- 檢查：是否能正確返回輸出圖片

#### Test 2: face_swap
- 目的：驗證圖片上傳和 LoadImage 節點
- 檢查：
  - 上傳的圖片是否能被 ComfyUI 讀取
  - 是否返回最終輸出而不是臨時預覽圖

#### Test 3: flf_veo3
- 目的：驗證多圖片上傳和路徑處理
- 檢查：
  - first_frame 和 last_frame 是否能正確上傳
  - Veo3 節點能否正確執行

### 3. 檢查日誌

關注以下日誌輸出：

**圖片上傳**:
```
💾 已保存圖片: upload_xxx_source.png (962550 bytes) 至 C:\ComfyUI_windows_portable\ComfyUI\input\...
✅ 檔案驗證成功: upload_xxx_source.png
```

**輸出處理**:
```
✓ 過濾後剩餘 X 個真實輸出
[ComfyClient] 檢查檔案路徑: C:\ComfyUI_windows_portable\ComfyUI\output\...
[ComfyClient] ✓ 已複製檔案: ... -> ...
```

---

## 預期改善

修復後應該看到以下改進：

### ✅ text_to_image
- 能正確找到並複製輸出圖片
- 不再顯示「找不到輸出檔案」錯誤

### ✅ face_swap
- LoadImage 節點能正確讀取上傳的圖片
- 返回最終合成圖片，不是 SigmasPreview 預覽圖
- 不再顯示 "Invalid image file" 錯誤

### ✅ flf_veo3
- first_frame 和 last_frame 能正確上傳並被讀取
- 不再顯示 "Invalid image file" 錯誤

---

## 後續改進建議

### 1. Workflow 配置檢查

Face_swap workflow 只返回臨時預覽圖，建議檢查：
- 是否有 SaveImage 節點配置
- 節點連接是否正確

### 2. 錯誤處理增強

考慮添加：
- 重試機制（圖片上傳失敗時）
- 更詳細的錯誤訊息（告訴用戶具體哪個步驟失敗）

### 3. 監控和告警

考慮添加：
- Worker 健康檢查 API
- 檔案寫入失敗告警
- ComfyUI 連接狀態監控

---

## 修改文件清單

1. ✅ `.env` - 更新 ComfyUI 路徑配置
2. ✅ `worker/src/main.py` - 增強圖片保存和過濾邏輯
3. ✅ `worker/src/comfy_client.py` - 改進輸出檔案處理
4. ✅ `scripts/test_config.py` - 新增配置測試腳本
5. ✅ `docs/fix_plan_output_issues.md` - 問題診斷文檔
6. ✅ `docs/fix_summary.md` - 本修復總結文檔（當前文件）

---

## 完成狀態

- ✅ 環境配置更新（避免硬編碼路徑）
- ✅ 圖片保存可靠性增強
- ✅ 輸出檔案處理邏輯改進
- ✅ 臨時預覽圖過濾
- ⏳ 等待測試驗證

**下一步**：請重啟 Worker 並測試各個 workflow，檢查問題是否解決。
