# Worker 輸出問題修復計劃

## 問題總結

從日誌分析出三個主要問題：

### 問題 1：輸出檔案路徑不匹配
```
[ComfyClient] 找不到輸出檔案: D:\02_software\ComfyUI_windows_portable\ComfyUI\output\集成應用1222\文生圖_00084_.png
```

**原因**：
- Worker 配置的 `COMFYUI_OUTPUT_DIR` 路徑與實際 ComfyUI 輸出路徑不一致
- 當前配置默認為: `D:\01_Project\2512_ComfyUISum\..\ComfyUI_windows_portable\ComfyUI`
- 但實際 ComfyUI 在: `D:\02_software\ComfyUI_windows_portable\ComfyUI`

**解決方案**：
1. 在 `.env` 文件中正確設置 `COMFYUI_ROOT` 環境變數
2. 確保 `COMFYUI_OUTPUT_DIR` 指向正確的輸出目錄

---

### 問題 2：LoadImage 節點無法讀取上傳的圖片
```
"details": "image - Invalid image file: upload_47240907-364e-4cb5-af2c-b1653ad673a9_first_frame.png"
```

**原因**：
- 圖片已成功保存到 ComfyUI input 目錄
- 但 ComfyUI 的 LoadImage 節點無法驗證該圖片
- 可能的原因：
  1. 檔案尚未完全寫入磁碟（緩衝區問題）
  2. 檔案編碼問題
  3. ComfyUI 快取問題

**解決方案**：
1. 在保存圖片後添加 `flush()` 和短暫延遲確保檔案寫入
2. 驗證圖片檔案可讀性後再提交 workflow
3. 添加錯誤處理和重試機制

---

### 問題 3：只收到臨時預覽圖，沒有最終輸出
```
[ComfyClient] 輸出圖片: [{'filename': 'SigmasPreview_temp_pyg7g_00001_.png', 'subfolder': '', 'type': 'temp'}]
[ComfyClient] 找不到輸出檔案: D:\02_software\ComfyUI_windows_portable\ComfyUI\output\SigmasPreview_temp_pyg7g_00001_.png
```

**原因**：
- `type: 'temp'` 表示這是臨時預覽圖，存放在 `ComfyUI/temp/` 目錄
- Worker 嘗試在 `output/` 目錄尋找，當然找不到
- Face_swap workflow 可能沒有正確配置最終輸出節點（如 SaveImage）

**解決方案**：
1. 修改 `copy_output_file()` 支持 `type: 'temp'` 的檔案（從 `temp/` 目錄複製）
2. 檢查 face_swap workflow 配置，確保有最終輸出節點
3. 過濾掉臨時預覽圖，只處理真正的輸出

---

## 修復步驟

### Step 1：修復環境配置
更新 `.env` 文件，設置正確的 ComfyUI 路徑：
```env
COMFYUI_ROOT=D:\02_software\ComfyUI_windows_portable\ComfyUI
```

### Step 2：增強圖片保存邏輯
在 `worker/src/main.py` 的 `save_base64_image()` 函數中：
- 添加 `flush()` 確保寫入磁碟
- 添加檔案驗證步驟
- 添加短暫延遲（100-200ms）

### Step 3：改進輸出檔案處理
在 `worker/src/comfy_client.py` 的 `copy_output_file()` 函數中：
- 支持 `type: 'temp'` 檔案（從 `temp/` 目錄複製）
- 支持 `type: 'output'` 檔案（從 `output/` 目錄複製）
- 添加詳細的路徑檢查日誌

### Step 4：過濾臨時預覽圖
在 `worker/src/main.py` 的 `process_job()` 函數中：
- 只處理 `type: 'output'` 的圖片
- 忽略 `type: 'temp'` 的預覽圖
- 如果沒有真正的輸出，記錄警告

---

## 實施優先級

1. **優先級 1（緊急）**：Step 1 - 修復環境配置路徑
2. **優先級 2（重要）**：Step 3 - 改進輸出檔案處理邏輯
3. **優先級 3（重要）**：Step 2 - 增強圖片保存的可靠性
4. **優先級 4（建議）**：Step 4 - 過濾臨時預覽圖

---

## 預期結果

修復完成後：
1. ✅ Worker 能正確找到 ComfyUI 的輸出檔案
2. ✅ 上傳的圖片能被 ComfyUI LoadImage 節點正確讀取
3. ✅ 只返回真正的最終輸出圖片，不返回臨時預覽
4. ✅ 所有 workflow (text_to_image, face_swap, flf_veo3) 都能正常工作
