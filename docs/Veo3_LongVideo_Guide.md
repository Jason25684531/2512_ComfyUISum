# Veo3 Long Video 功能文檔

## 📅 實施日期
2026-01-12 ~ 2026-01-13

---

## 📌 功能概述

Veo3 Long Video 功能允許用戶創建最多 5 段連續視頻，每段可以有獨立的文本描述（prompt）。

### 核心特點
- **Strategy B（允許空字串）**：用戶可以留空某些片段，系統會為空片段注入空字串
- **動態裁剪**：根據實際上傳的圖片數量，自動裁剪工作流
- **UI 位置**：整合到 Motion Workspace 頁面

---

## ✅ 已完成的實施

### 1. 配置更新 (`ComfyUIworkflow/config.json`)

```json
"veo3_long_video": {
  "file": "Veo3_VideoConnection.json",
  "description": "Veo3 Long Video - 5 段視頻拼接",
  "mapping": {
    "output_node_id": "110",
    "prompt_segments": {
      "0": "10",
      "1": "21",
      "2": "31",
      "3": "41",
      "4": "51"
    }
  }
}
```

### 2. Backend API (`backend/src/app.py`)

- 支持 `prompts` 列表參數
- 完整驗證邏輯（列表類型、最多10個、每個最長1000字符）
- 向後兼容單個 `prompt` 參數

**API 使用範例**:
```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "veo3_long_video",
    "prompts": ["A lady is talking", "", "Camera zooms in", "", "She smiles"]
  }'
```

### 3. Worker (`worker/src/main.py` & `json_parser.py`)

- 提取並傳遞 `prompts` 參數
- **Strategy B** 實施：迭代 Config 的 `prompt_segments`，空白欄位注入空字串
- 動態裁剪工作流（`trim_veo3_workflow` 函數）

### 4. 前端 (`frontend/index.html` & `motion-workspace.js`)

- 5 個獨立的 Shot 上傳區
- 5 個 Segment 文本輸入框
- 單段/多段模式切換功能
- 進度輪詢和結果顯示

---

## 🔧 技術架構

```
Frontend (Motion Workspace)
    ↓ POST /api/generate { workflow, prompts[], images{} }
Backend (app.py)
    ↓ Push to Redis Queue
Worker (main.py)
    ↓ parse_workflow() with prompts injection
ComfyUI
    ↓ VeoVideoGenerator nodes execution
Output (storage/outputs/*.mp4)
```

---

## 📋 修改文件清單

| 文件 | 說明 |
|------|------|
| `ComfyUIworkflow/config.json` | 添加 veo3_long_video 配置 |
| `backend/src/app.py` | 支持 prompts 參數 |
| `worker/src/main.py` | 提取並傳遞 prompts |
| `worker/src/json_parser.py` | Strategy B + 動態裁剪 |
| `worker/src/config.py` | 添加 WORKFLOW_CONFIG_PATH |
| `frontend/index.html` | Motion Workspace UI |
| `frontend/motion-workspace.js` | JavaScript 函數 |

---

## 🧪 測試指南

### 啟動服務
```powershell
# 終端 1 - Backend
python backend\src\app.py

# 終端 2 - Worker  
python worker\src\main.py

# 確保 ComfyUI 已啟動
```

### 測試步驟
1. 瀏覽器開啟 `http://localhost:5000`
2. 點擊左側選單 "Image to Video"
3. 上傳 1-5 張圖片到 Shot 區域
4. 填寫對應的 Segment 描述
5. 點擊 "Generate Long Video"
6. 等待完成，預覽區會顯示影片

---

## 📝 注意事項

1. **空片段處理**：用戶可以留空某些 Segment，系統會自動注入空字串
2. **圖片要求**：至少需要上傳 1 張圖片
3. **超時設定**：影片生成可能需要較長時間（預設 1 小時超時）
4. **輸出格式**：最終輸出為 MP4 格式

---

*本文檔整合自原始的 Veo3_Implementation_Report.md、Veo3_Summary_ZH.md、Veo3_Test_Report.md、VEOACTION_COMPLETE.md*
