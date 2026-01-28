/**
 * Image Upload Utilities
 * =======================
 * 統一的圖片上傳、預覽、清除邏輯
 * 避免各工具中重複代碼
 * 
 * @author AI Architect
 * @date 2026-01-28
 */

/**
 * 通用圖片處理與預覽函式
 * 
 * @param {File} file - 上傳的圖片檔案
 * @param {string} slotId - 上傳區域 ID (如 'first_frame', 'shot_0', 't2i-source')
 * @param {object} storage - 儲存圖片的全域物件 (如 window.flfImages, window.motionShotImages)
 * @param {string} borderColor - 上傳成功後的邊框顏色 (如 'purple', 'amber', 'blue')
 */
function processImageUpload(file, slotId, storage, borderColor) {
    if (!file || !file.type.startsWith('image/')) {
        console.warn('[ImageUtils] 非圖片檔案，已忽略');
        return;
    }

    var reader = new FileReader();
    reader.onload = function (e) {
        // 1. 儲存 Base64 數據到全域狀態
        storage[slotId] = e.target.result;

        // 2. 更新 DOM 預覽
        var preview = document.getElementById('preview-' + slotId);
        var placeholder = document.getElementById('placeholder-' + slotId);
        var zone = document.getElementById('zone-' + slotId);

        if (preview && placeholder && zone) {
            var img = preview.querySelector('img');
            if (img) img.src = e.target.result;
            
            preview.classList.remove('hidden');
            placeholder.classList.add('hidden');
            zone.classList.add('has-image', 'border-solid', 'border-' + borderColor + '-500/50');
        }

        // 3. 重新初始化圖示 (Lucide Icons)
        if (typeof lucide !== 'undefined' && lucide.createIcons) {
            lucide.createIcons();
        }

        console.log('[ImageUtils] 圖片已上傳:', slotId);
    };

    reader.onerror = function(error) {
        console.error('[ImageUtils] 圖片讀取失敗:', error);
        alert('圖片讀取失敗，請重試');
    };

    reader.readAsDataURL(file);
}

/**
 * 通用圖片清除函式
 * 
 * @param {string} slotId - 上傳區域 ID
 * @param {object} storage - 儲存圖片的全域物件
 * @param {string} borderColor - 邊框顏色 (用於移除樣式)
 */
function clearImageUpload(slotId, storage, borderColor) {
    // 1. 清除全域狀態
    storage[slotId] = null;

    // 2. 重置 DOM
    var preview = document.getElementById('preview-' + slotId);
    var placeholder = document.getElementById('placeholder-' + slotId);
    var zone = document.getElementById('zone-' + slotId);
    var fileInput = document.getElementById('file-' + slotId);

    if (preview) preview.classList.add('hidden');
    if (placeholder) placeholder.classList.remove('hidden');
    if (zone) zone.classList.remove('has-image', 'border-solid', 'border-' + borderColor + '-500/50');
    if (fileInput) fileInput.value = '';

    console.log('[ImageUtils] 圖片已清除:', slotId);
}

/**
 * 觸發檔案選擇對話框
 * 
 * @param {string} slotId - 上傳區域 ID
 */
function triggerFileUpload(slotId) {
    var fileInput = document.getElementById('file-' + slotId);
    if (fileInput) {
        fileInput.click();
    } else {
        console.error('[ImageUtils] 找不到檔案輸入元素:', 'file-' + slotId);
    }
}

/**
 * 處理檔案選擇事件 (File Input onChange)
 * 
 * @param {Event} event - Input 事件
 * @param {string} slotId - 上傳區域 ID
 * @param {object} storage - 儲存圖片的全域物件
 * @param {string} borderColor - 邊框顏色
 */
function handleFileSelect(event, slotId, storage, borderColor) {
    var file = event.target.files[0];
    if (file) {
        processImageUpload(file, slotId, storage, borderColor);
    }
}

/**
 * 處理拖放事件 (Drop Zone onDrop)
 * 
 * @param {DragEvent} event - Drag 事件
 * @param {string} slotId - 上傳區域 ID
 * @param {object} storage - 儲存圖片的全域物件
 * @param {string} borderColor - 邊框顏色
 */
function handleFileDrop(event, slotId, storage, borderColor) {
    event.preventDefault();
    
    // 移除拖放視覺效果
    var zone = document.getElementById('zone-' + slotId);
    if (zone) {
        zone.classList.remove('border-' + borderColor + '-500/70', 'bg-' + borderColor + '-500/10');
    }

    var file = event.dataTransfer.files[0];
    if (file) {
        processImageUpload(file, slotId, storage, borderColor);
    }
}

/**
 * 處理拖入事件 (Drop Zone onDragOver)
 * 
 * @param {DragEvent} event - Drag 事件
 * @param {string} slotId - 上傳區域 ID
 * @param {string} borderColor - 邊框顏色
 */
function handleDragOver(event, slotId, borderColor) {
    event.preventDefault();
    var zone = document.getElementById('zone-' + slotId);
    if (zone) {
        zone.classList.add('border-' + borderColor + '-500/70', 'bg-' + borderColor + '-500/10');
    }
}

/**
 * 處理拖出事件 (Drop Zone onDragLeave)
 * 
 * @param {DragEvent} event - Drag 事件
 * @param {string} slotId - 上傳區域 ID
 * @param {string} borderColor - 邊框顏色
 */
function handleDragLeave(event, slotId, borderColor) {
    var zone = document.getElementById('zone-' + slotId);
    if (zone) {
        zone.classList.remove('border-' + borderColor + '-500/70', 'bg-' + borderColor + '-500/10');
    }
}

/**
 * 驗證圖片是否已上傳
 * 
 * @param {object} storage - 儲存圖片的全域物件
 * @param {string[]} requiredSlots - 必填的上傳區域 ID 列表
 * @returns {boolean} - 是否所有必填圖片都已上傳
 */
function validateRequiredImages(storage, requiredSlots) {
    for (var i = 0; i < requiredSlots.length; i++) {
        var slotId = requiredSlots[i];
        if (!storage[slotId]) {
            console.warn('[ImageUtils] 缺少必填圖片:', slotId);
            return false;
        }
    }
    return true;
}

// ==========================================
// 導出為全域函式 (供其他腳本使用)
// ==========================================
if (typeof window !== 'undefined') {
    window.ImageUtils = {
        processImageUpload: processImageUpload,
        clearImageUpload: clearImageUpload,
        triggerFileUpload: triggerFileUpload,
        handleFileSelect: handleFileSelect,
        handleFileDrop: handleFileDrop,
        handleDragOver: handleDragOver,
        handleDragLeave: handleDragLeave,
        validateRequiredImages: validateRequiredImages
    };
    console.log('[ImageUtils] 圖片工具模組已載入');
}
