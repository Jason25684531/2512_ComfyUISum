# 前端導航流程文檔

## 頁面跳轉邏輯

### 1. 登入流程 (login.html)
- **目標**: 用戶認證
- **成功後**: 跳轉到 `/dashboard.html`
- **已登入**: 自動跳轉到 `/dashboard.html`
- **API 端點**: 
  - `POST /api/login` - 登入
  - `POST /api/register` - 註冊
  - `GET /api/me` - 檢查登入狀態

### 2. 主控台 (dashboard.html)
- **目標**: 創作中心
- **功能**:
  - Image Composition (圖片合成工具)
  - Video Studio (影片生成工具)
  - Avatar Studio (虛擬人像生成)
  - Personal Gallery (作品庫)
- **連結到**:
  - `/profile.html` - 用戶個人頁面（側邊欄和頂部欄的用戶頭像）
  - `/login.html` - 登入按鈕（未登入狀態）
- **認證**: 
  - 不強制登入，但未登入時顯示「登入/註冊」按鈕
  - 已登入時顯示用戶名稱
- **API 端點**:
  - `GET /api/me` - 檢查登入狀態
  - `GET /api/history` - 載入歷史作品

### 3. 個人頁面 (profile.html)
- **目標**: 作品庫管理
- **功能**:
  - 查看所有歷史作品
  - 刪除作品
  - 登出功能
- **連結到**:
  - `/dashboard.html` - 創作中心按鈕（頂部欄）
  - `/dashboard.html` - 側邊欄導航
  - `/login.html` - 登出後或認證失敗時
- **認證**: 
  - **必須登入**，未登入時自動跳轉到 `/login.html`
  - 頁面載入時執行 `checkAuth()`
- **API 端點**:
  - `GET /api/me` - 檢查登入狀態（必須）
  - `GET /api/history?limit=100` - 載入所有作品
  - `POST /api/logout` - 登出

## 導航流程圖

```
┌─────────────┐
│ login.html  │
│  (登入頁)    │
└──────┬──────┘
       │ 登入成功
       │ 或已登入
       ↓
┌─────────────────┐
│ dashboard.html  │◄──────────────┐
│   (主控台)       │               │
└────────┬────────┘               │
         │ 點擊用戶頭像             │
         ↓                         │
    ┌─────────────┐                │
    │profile.html │                │
    │  (作品庫)    │────────────────┘
    └──────┬──────┘    返回創作中心
           │
           │ 登出或認證失敗
           ↓
    ┌─────────────┐
    │ login.html  │
    └─────────────┘
```

## API 端點統一說明

### 認證相關
- `POST /api/login` - 登入
  - Request: `{ email, password }`
  - Response: `{ success: true, user: {...} }`

- `POST /api/register` - 註冊
  - Request: `{ email, password, name }`
  - Response: `{ success: true }`

- `POST /api/logout` - 登出
  - Response: `{ success: true }`

- `GET /api/me` - 取得當前用戶資訊
  - Response: `{ logged_in: true/false, user: {...} }`

### 歷史記錄
- `GET /api/history` - 取得歷史作品
  - Response (支援兩種格式):
    - `{ history: [...] }` 或
    - `{ jobs: [...] }`
  - 每個項目包含:
    - `id` - 作品 ID
    - `tool` / `workflow` - 工具名稱
    - `output_url` / `output_path` - 輸出圖片路徑
    - `prompt` - 提示詞
    - `created_at` - 創建時間

## 修復內容

### profile.html
1. ✅ 啟用 `checkAuth()` 函數（之前被註解）
2. ✅ 登出後跳轉到 `/login.html` 而不是 `/`
3. ✅ 認證失敗時跳轉到 `/login.html` 而不是 `/`
4. ✅ 添加 console.log 用於調試

### dashboard.html
1. ✅ 統一 API 回應處理，支援 `data.history` 和 `data.jobs` 兩種格式
2. ✅ 支援 `output_url` 和 `output_path` 兩種欄位名
3. ✅ 支援 `tool` 和 `workflow` 兩種欄位名
4. ✅ 改善錯誤處理和用戶回饋

### login.html
1. ✅ 已正確配置跳轉邏輯到 `/dashboard.html`
2. ✅ 已登入時自動跳轉到 `/dashboard.html`

## 測試檢查清單

- [ ] 未登入訪問 `/dashboard.html` - 應顯示登入按鈕
- [ ] 未登入訪問 `/profile.html` - 應自動跳轉到 `/login.html`
- [ ] 登入成功 - 應跳轉到 `/dashboard.html`
- [ ] 在 dashboard 點擊用戶頭像 - 應跳轉到 `/profile.html`
- [ ] 在 profile 點擊「創作中心」- 應跳轉到 `/dashboard.html`
- [ ] 在 profile 點擊「登出」- 應跳轉到 `/login.html`
- [ ] API 錯誤處理 - 應顯示友善的錯誤訊息
- [ ] 刷新頁面 - 應保持登入狀態（如果使用 session/cookie）
