# 前端最佳實踐指南

**版本**: 1.0  
**日期**: 2026-01-28  
**目的**: 避免 UI 狀態污染，確保工具間的狀態隔離

---

## 🎯 核心原則

### 1. 工具狀態隔離 (Tool State Isolation)

**問題**：當前架構使用 `toolStates` 物件管理不同工具的狀態，但仍共用同一組 DOM 元素 (如 `#prompt-input`)，可能導致狀態污染。

**解決方案**：已實作的 `saveToolState()` 和 `loadToolState()` 機制有效隔離狀態。

**檢查點**：
```javascript
// ✅ 良好實踐：每個工具有獨立狀態
window.toolStates = {
    'text_to_image': { prompt: '', images: {}, isGenerating: false },
    'face_swap': { prompt: '', images: {}, isGenerating: false },
    // ...
};

// ✅ 切換工具時自動保存/載入狀態
function selectTool(toolId) {
    saveToolState(currentTool);  // 保存當前工具狀態
    currentTool = toolId;
    loadToolState(toolId);        // 載入新工具狀態
}
```

---

## 📝 ID 命名規範

### 當前架構

**共用元素** (Legacy T2I 模式)：
- `#prompt-input` - 主要 prompt 輸入框
- `#btn-generate` - 生成按鈕
- `#model-select` - 模型選擇器
- `#seed-input` - 種子輸入
- `#upload-zones` - 動態上傳區域容器

**工具特定元素** (透過 `renderWorkspace()` 動態生成)：
- `#zone-{uploadId}` - 上傳區域
- `#preview-{uploadId}` - 圖片預覽
- `#placeholder-{uploadId}` - 佔位符

### 未來擴展建議

如需新增獨立工具 UI（不共用 `#prompt-input`），建議：

1. **容器隔離**：
   ```html
   <!-- T2I 模式 (保留現有) -->
   <div id="t2i-container" class="tool-container">
       <textarea id="prompt-input"></textarea>
       <button id="btn-generate"></button>
   </div>
   
   <!-- 新工具 (獨立容器) -->
   <div id="custom-tool-container" class="tool-container hidden">
       <textarea id="custom-prompt"></textarea>
       <button id="custom-generate"></button>
   </div>
   ```

2. **切換邏輯**：
   ```javascript
   function switchToolContainer(toolId) {
       // 隱藏所有容器
       document.querySelectorAll('.tool-container').forEach(c => c.classList.add('hidden'));
       
       // 顯示目標容器
       const targetContainer = getToolContainer(toolId);
       targetContainer.classList.remove('hidden');
   }
   ```

---

## 🎨 圖片上傳最佳實踐

### 使用 image-utils.js 統一模組

**當前問題**：圖片上傳邏輯散落在多處 (T2I, Face Swap, FLF, Shot)。

**解決方案**：已創建 `frontend/image-utils.js` 統一模組。

**使用範例**：
```html
<!-- HTML -->
<div id="zone-source" class="upload-zone">
    <div id="placeholder-source">Click to upload</div>
    <div id="preview-source" class="hidden">
        <img src="" alt="Preview">
    </div>
    <input type="file" id="file-source" class="hidden" 
           onchange="ImageUtils.handleFileSelect(event, 'source', uploadedImages, 'purple')">
</div>

<script>
// JavaScript
function triggerUpload(uploadId) {
    ImageUtils.triggerFileUpload(uploadId);
}

function clearImage(uploadId) {
    ImageUtils.clearImageUpload(uploadId, uploadedImages, 'purple');
}

// 驗證必填圖片
if (!ImageUtils.validateRequiredImages(uploadedImages, ['source', 'target'])) {
    alert('請上傳所有必填圖片');
}
</script>
```

**優勢**：
- ✅ 統一錯誤處理
- ✅ 一致的預覽邏輯
- ✅ 減少重複代碼
- ✅ 易於維護

---

## 🔄 狀態管理最佳實踐

### 當前架構 (toolStates)

**運作方式**：
```javascript
// 1. 初始化狀態
window.toolStates = {
    'text_to_image': {
        prompt: '',
        images: {},
        canvasHtml: '',
        canvasHidden: true,
        isGenerating: false
    }
};

// 2. 切換工具時自動保存/載入
function selectTool(toolId) {
    saveToolState(currentTool);  // 保存當前狀態
    currentTool = toolId;
    renderWorkspace();            // 重新渲染 UI
    loadToolState(toolId);        // 載入目標狀態
}

// 3. 深拷貝避免引用污染
window.toolStates[toolName].images = JSON.parse(JSON.stringify(uploadedImages));
```

**檢查點**：
- ✅ 每個工具有獨立狀態物件
- ✅ 使用深拷貝避免引用污染
- ✅ 切換工具時自動保存/載入
- ✅ 支援保存 Canvas 結果與生成狀態

### 防止狀態污染的關鍵

**問題場景**：
```javascript
// ❌ 錯誤：直接共用全域變數
let globalPrompt = '';  // 所有工具共用，會污染

function handleT2I() {
    globalPrompt = document.getElementById('prompt-input').value;
}

function handleFaceSwap() {
    // 會讀到 T2I 的 prompt！
    globalPrompt = document.getElementById('prompt-input').value;
}
```

**解決方案**：
```javascript
// ✅ 正確：使用工具隔離的狀態
function handleGenerate() {
    // 1. 讀取當前輸入
    const currentPrompt = document.getElementById('prompt-input').value;
    
    // 2. 保存到工具專屬狀態
    window.toolStates[currentTool].prompt = currentPrompt;
    
    // 3. 發送請求時使用工具狀態
    const payload = {
        workflow: currentTool,
        prompt: window.toolStates[currentTool].prompt,  // 使用隔離狀態
        images: window.toolStates[currentTool].images
    };
}
```

---

## 🧪 測試驗證

### UI 狀態隔離測試

**測試步驟**：
1. 進入 Text-to-Image 模式
2. 輸入 Prompt: "a red cat"
3. 上傳一張圖片 (如適用)
4. 切換至 Face-Swap 模式
5. 檢查 Prompt 輸入框 (應為空或該模式的保存值)
6. 切換回 Text-to-Image 模式
7. 確認 Prompt 仍為 "a red cat"，圖片未丟失

**預期結果**：
- ✅ 每個工具的輸入獨立
- ✅ 切換工具不會丟失資料
- ✅ Canvas 結果正確保存/恢復

### 圖片上傳測試

**測試步驟**：
1. 在 Face-Swap 上傳 Source 和 Target 圖片
2. 切換至 Text-to-Image
3. 切換回 Face-Swap
4. 確認兩張圖片仍正確顯示

**預期結果**：
- ✅ 圖片資料正確保存
- ✅ 預覽圖片正確恢復
- ✅ 無圖片遺失或混亂

---

## 🚀 效能優化建議

### 1. 延遲載入 Canvas 結果

```javascript
// 當前：保存完整 HTML (可能很大)
window.toolStates[toolName].canvasHtml = resultsGrid.innerHTML;

// 建議：只保存圖片 URL 列表
window.toolStates[toolName].resultUrls = ['/outputs/img1.png', '/outputs/img2.png'];

// 恢復時動態生成
function restoreCanvas(urls) {
    resultsGrid.innerHTML = urls.map(url => `
        <img src="${url}" class="rounded-xl">
    `).join('');
}
```

### 2. 節流上傳預覽

```javascript
// 當前：立即處理
reader.onload = (e) => {
    preview.src = e.target.result;
};

// 建議：節流大檔案處理
function processImageWithThrottle(file) {
    if (file.size > 5 * 1024 * 1024) {  // > 5MB
        showStatus('⏳ Processing large image...', 'info');
    }
    // ... existing logic
}
```

---

## 📚 相關文件

- [image-utils.js](../frontend/image-utils.js) - 圖片上傳統一模組
- [Stability Refactor Spec](../openspec/specs/001-stability-refactor.md) - 完整技術規格
- [Validation Guide](../docs/Stability_Refactor_Validation_Guide.md) - 驗證測試指南

---

## 🔧 故障排除

### Q1: 切換工具後 Prompt 丟失
**原因**：`saveToolState()` 未正確執行  
**解決**：檢查 console.log 輸出，確認 `[State] 已保存 ...` 訊息

### Q2: 圖片上傳後切換工具消失
**原因**：深拷貝失敗或 `uploadedImages` 未同步  
**解決**：檢查 `JSON.parse(JSON.stringify(...))` 是否正確執行

### Q3: Canvas 結果未保存
**原因**：`resultsGrid.innerHTML` 為空時保存  
**解決**：添加檢查 `if (resultsGrid.innerHTML.trim())` 再保存

---

**維護負責人**: Frontend Team  
**最後更新**: 2026-01-28  
**版本**: 1.0
