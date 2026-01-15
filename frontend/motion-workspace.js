/**
 * Motion Workspace - Video Studio JavaScript Functions
 * ========================================================
 * Supports: Veo3 Long Video, T2V, FLF workflows
 */

// ==========================================
// Motion Workspace Global State
// ==========================================
if (typeof window.isVeo3Mode === 'undefined') {
    window.isVeo3Mode = false;
}
if (typeof window.motionShotImages === 'undefined') {
    window.motionShotImages = {};
}
// 新增: 當前選擇的 Video 工作流
if (typeof window.currentVideoWorkflow === 'undefined') {
    window.currentVideoWorkflow = 'veo3_long_video';
}
// 新增: FLF 圖片儲存
if (typeof window.flfImages === 'undefined') {
    window.flfImages = { first_frame: null, last_frame: null };
}

// ==========================================
// Video Workflow Tab 切換
// ==========================================

/**
 * 顯示 Video Tool 選擇器 Overlay
 */
function showVideoToolMenu() {
    var overlay = document.getElementById('video-tool-selector-overlay');
    var workspace = document.getElementById('video-workspace');
    if (overlay) overlay.classList.remove('hidden');
    if (workspace) workspace.classList.add('hidden');
    if (typeof lucide !== 'undefined' && lucide.createIcons) {
        lucide.createIcons();
    }
    console.log('[Motion] 顯示 Video Tool 選擇器');
}

/**
 * 隱藏 Video Tool 選擇器 Overlay
 */
function hideVideoToolMenu() {
    var overlay = document.getElementById('video-tool-selector-overlay');
    var workspace = document.getElementById('video-workspace');
    if (overlay) overlay.classList.add('hidden');
    if (workspace) workspace.classList.remove('hidden');
    console.log('[Motion] 隱藏 Video Tool 選擇器');
}

/**
 * 選擇 Video 工具 (從 Overlay Card 點擊)
 */
function selectVideoTool(workflowType) {
    window.currentVideoWorkflow = workflowType;
    console.log('[Motion] 選擇工具:', workflowType);

    // 隱藏 Overlay，顯示 Workspace
    hideVideoToolMenu();

    // 更新左側工具 Header
    var toolIcon = document.getElementById('video-tool-icon');
    var toolName = document.getElementById('video-tool-name');
    var toolDesc = document.getElementById('video-tool-desc');

    var toolConfig = {
        'veo3_long_video': { name: '長片生成', desc: 'Multi-Shot', icon: 'film', color: 'amber' },
        't2v_veo3': { name: '文字轉影片', desc: 'Text to Video', icon: 'type', color: 'blue' },
        'flf_veo3': { name: '首尾禎動畫', desc: 'First-Last Frame', icon: 'image', color: 'purple' }
    };

    var config = toolConfig[workflowType] || toolConfig['veo3_long_video'];

    if (toolIcon) {
        toolIcon.className = 'p-2 rounded-lg bg-' + config.color + '-500/20 text-' + config.color + '-300';
        toolIcon.innerHTML = '<i data-lucide="' + config.icon + '" class="w-4 h-4"></i>';
    }
    if (toolName) toolName.textContent = config.name;
    if (toolDesc) toolDesc.textContent = config.desc;

    // 更新面板顯示
    var panels = ['panel-veo3_long_video', 'panel-t2v_veo3', 'panel-flf_veo3'];
    panels.forEach(function (panelId) {
        var panel = document.getElementById(panelId);
        if (panel) {
            if (panelId === 'panel-' + workflowType) {
                panel.classList.remove('hidden');
            } else {
                panel.classList.add('hidden');
            }
        }
    });

    // 更新右側 Prompt 區域
    var toggleBtn = document.getElementById('toggle-veo3-mode');

    if (workflowType === 'veo3_long_video') {
        // 長片模式：顯示切換按鈕
        if (toggleBtn) toggleBtn.classList.remove('hidden');
    } else {
        // T2V/FLF：隱藏切換按鈕，顯示單輸入框
        if (toggleBtn) toggleBtn.classList.add('hidden');
        showMotionSinglePrompt();
    }

    // 重新初始化圖示
    if (typeof lucide !== 'undefined' && lucide.createIcons) {
        lucide.createIcons();
    }

    // 初始化圖片上傳區（長片模式）
    if (workflowType === 'veo3_long_video' && typeof initMotionShotsUI === 'function') {
        initMotionShotsUI();
    }
}

/**
 * 切換 Video 工作流 (舊版相容)
 */
function switchVideoWorkflow(workflowType) {
    selectVideoTool(workflowType);
}

// ==========================================
// 通用圖片上傳處理函式 (合併 FLF 與 Shot 的重複邏輯)
// ==========================================

/**
 * 通用圖片處理與預覽函式
 * @param {File} file - 上傳的圖片檔案
 * @param {string} slotId - 上傳區域 ID (如 'first_frame', 'shot_0')
 * @param {object} storage - 儲存圖片的全域物件 (如 window.flfImages, window.motionShotImages)
 * @param {string} borderColor - 上傳成功後的邊框顏色 (如 'purple', 'amber')
 */
function processImageUpload(file, slotId, storage, borderColor) {
    var reader = new FileReader();
    reader.onload = function (e) {
        storage[slotId] = e.target.result;

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

        if (typeof lucide !== 'undefined' && lucide.createIcons) {
            lucide.createIcons();
        }
        console.log('[Motion] ' + slotId + ' 已上傳');
    };
    reader.readAsDataURL(file);
}

/**
 * 通用圖片清除函式
 */
function clearImageUpload(slotId, storage, borderColor) {
    storage[slotId] = null;

    var preview = document.getElementById('preview-' + slotId);
    var placeholder = document.getElementById('placeholder-' + slotId);
    var zone = document.getElementById('zone-' + slotId);
    var fileInput = document.getElementById('file-' + slotId);

    if (preview) preview.classList.add('hidden');
    if (placeholder) placeholder.classList.remove('hidden');
    if (zone) zone.classList.remove('has-image', 'border-solid', 'border-' + borderColor + '-500/50');
    if (fileInput) fileInput.value = '';

    console.log('[Motion] ' + slotId + ' 已清除');
}

// ==========================================
// FLF 圖片處理函式 (使用通用處理器)
// ==========================================

function triggerFLFUpload(frameType) {
    var fileInput = document.getElementById('file-' + frameType);
    if (fileInput) fileInput.click();
}

function handleFLFSelect(event, frameType) {
    var file = event.target.files[0];
    if (file && file.type.startsWith('image/')) {
        processImageUpload(file, frameType, window.flfImages, 'purple');
    }
}

function handleFLFDrop(event, frameType) {
    event.preventDefault();
    var zone = document.getElementById('zone-' + frameType);
    if (zone) zone.classList.remove('border-purple-500/70', 'bg-purple-500/10');

    var file = event.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        processImageUpload(file, frameType, window.flfImages, 'purple');
    }
}

function clearFLFImage(frameType) {
    clearImageUpload(frameType, window.flfImages, 'purple');
}

/**

 * Toggle single/multi segment mode
 */
function toggleVeo3Mode() {
    window.isVeo3Mode = !window.isVeo3Mode;
    var modeLabel = document.getElementById('mode-label');

    if (window.isVeo3Mode) {
        showMotionMultiPrompts();
        if (modeLabel) modeLabel.textContent = 'Switch to Single Mode';
        console.log('[Motion] Switched to Veo3 multi-segment mode');
    } else {
        showMotionSinglePrompt();
        if (modeLabel) modeLabel.textContent = 'Switch to Multi Mode';
        console.log('[Motion] Switched to single mode');
    }
}

/**
 * Show single prompt input
 */
function showMotionSinglePrompt() {
    var singleContainer = document.getElementById('motion-single-prompt');
    var multiContainer = document.getElementById('motion-multi-prompts');

    if (singleContainer) singleContainer.classList.remove('hidden');
    if (multiContainer) multiContainer.classList.add('hidden');

    window.isVeo3Mode = false;
}

/**
 * Show multi prompts input (Veo3 Long Video)
 */
function showMotionMultiPrompts() {
    var singleContainer = document.getElementById('motion-single-prompt');
    var multiContainer = document.getElementById('motion-multi-prompts');

    if (singleContainer) singleContainer.classList.add('hidden');
    if (multiContainer) multiContainer.classList.remove('hidden');

    window.isVeo3Mode = true;
}

/**
 * Show status message
 */
function showMotionStatus(message, type) {
    type = type || 'info';
    var statusEl = document.getElementById('motion-status-message');
    if (!statusEl) return;

    statusEl.textContent = message;
    statusEl.classList.remove('hidden', 'text-blue-400', 'text-green-400', 'text-red-400', 'text-yellow-400');

    if (type === 'success') {
        statusEl.classList.add('text-green-400');
    } else if (type === 'error') {
        statusEl.classList.add('text-red-400');
    } else if (type === 'warning') {
        statusEl.classList.add('text-yellow-400');
    } else {
        statusEl.classList.add('text-blue-400');
    }

    if (type !== 'error') {
        setTimeout(function () {
            statusEl.classList.add('hidden');
        }, 5000);
    }
}

/**
 * Initialize Shot upload areas (5 slots)
 */
function initMotionShotsUI() {
    var shotContainer = document.getElementById('motion-shots-upload');
    if (!shotContainer) {
        console.warn('[Motion] Container motion-shots-upload not found, skipping init');
        return;
    }

    var shotsHTML = '';
    for (var i = 0; i < 5; i++) {
        var shotId = 'shot_' + i;
        shotsHTML += '<div id="zone-' + shotId + '" ' +
            'class="upload-zone relative flex flex-col items-center justify-center rounded-xl cursor-pointer bg-black/20 p-4 border-2 border-dashed border-white/10 min-h-[100px] hover:border-amber-500/50 transition-colors" ' +
            'onclick="triggerMotionShotUpload(\'' + shotId + '\')" ' +
            'ondragover="event.preventDefault(); this.classList.add(\'border-amber-500/70\', \'bg-amber-500/10\');" ' +
            'ondragleave="this.classList.remove(\'border-amber-500/70\', \'bg-amber-500/10\');" ' +
            'ondrop="handleMotionShotDrop(event, \'' + shotId + '\')">' +
            '<input type="file" id="file-' + shotId + '" class="hidden" accept="image/*" onchange="handleMotionShotSelect(event, \'' + shotId + '\')" />' +
            '<div id="preview-' + shotId + '" class="hidden absolute inset-0">' +
            '<img src="" alt="Preview" class="w-full h-full object-cover rounded-xl" />' +
            '<button onclick="event.stopPropagation(); clearMotionShot(\'' + shotId + '\')" ' +
            'class="absolute top-2 right-2 p-1 bg-black/70 rounded-full hover:bg-red-500/80 transition-colors z-10">' +
            '<i data-lucide="x" class="w-4 h-4 text-white"></i>' +
            '</button>' +
            '</div>' +
            '<div id="placeholder-' + shotId + '" class="flex flex-col items-center pointer-events-none">' +
            '<i data-lucide="image" class="w-6 h-6 text-gray-500 mb-2"></i>' +
            '<span class="text-xs uppercase font-bold text-gray-500">Shot ' + (i + 1) + '</span>' +
            '<span class="text-[10px] text-gray-600 mt-1">(Optional)</span>' +
            '</div>' +
            '</div>';
    }

    shotContainer.innerHTML = shotsHTML;

    if (typeof lucide !== 'undefined' && lucide.createIcons) {
        lucide.createIcons();
    }
    console.log('[Motion] Shot upload areas initialized (5 slots)');
}

/**
 * Trigger file upload dialog
 */
function triggerMotionShotUpload(shotId) {
    var fileInput = document.getElementById('file-' + shotId);
    if (fileInput) fileInput.click();
}

/**
 * Handle file selection
 */
function handleMotionShotSelect(event, shotId) {
    var file = event.target.files[0];
    if (file && file.type.startsWith('image/')) {
        processImageUpload(file, shotId, window.motionShotImages, 'amber');
    }
}

/**
 * Handle drag and drop
 */
function handleMotionShotDrop(event, shotId) {
    event.preventDefault();
    var zone = document.getElementById('zone-' + shotId);
    if (zone) zone.classList.remove('border-amber-500/70', 'bg-amber-500/10');

    var file = event.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        processImageUpload(file, shotId, window.motionShotImages, 'amber');
    }
}

/**
 * Clear shot image
 */
function clearMotionShot(shotId) {
    clearImageUpload(shotId, window.motionShotImages, 'amber');
}


/**
 * Generate video handler
 */
function handleMotionGenerate() {
    console.log('[Motion] Starting video generation...');
    console.log('[Motion] Current workflow:', window.currentVideoWorkflow);
    showMotionStatus('Starting task submission...', 'info');

    var payload = {
        seed: -1,
        aspect_ratio: '9:16',
        model: 'veo3',
        batch_size: 1
    };

    var promptInput = document.getElementById('motion-prompt-input');
    var prompt = promptInput ? promptInput.value.trim() : '';

    // 根據當前工作流類型處理
    if (window.currentVideoWorkflow === 'veo3_long_video') {
        // ==========================================
        // 長片生成工作流
        // ==========================================
        if (window.isVeo3Mode) {
            // 多段模式
            var prompts = [];
            for (var i = 0; i < 5; i++) {
                var input = document.getElementById('veo3-segment-' + i);
                prompts.push(input ? input.value.trim() : '');
            }

            var hasContent = prompts.some(function (p) { return p.length > 0; });
            if (!hasContent) {
                showMotionStatus('請填寫至少一個片段提示詞', 'error');
                return;
            }

            payload.workflow = 'veo3_long_video';
            payload.prompts = prompts;
            payload.prompt = '';
            console.log('[Motion] Veo3 multi-segment mode, prompts:', prompts);
        } else {
            // 單段模式
            if (!prompt) {
                showMotionStatus('請輸入影片描述', 'error');
                return;
            }
            payload.workflow = 'image_to_video';
            payload.prompt = prompt;
            payload.prompts = [];
            console.log('[Motion] Single segment mode, prompt:', prompt);
        }

        // 收集上傳的 Shot 圖片
        var uploadedShots = {};
        var keys = Object.keys(window.motionShotImages);
        for (var j = 0; j < keys.length; j++) {
            var shotId = keys[j];
            if (window.motionShotImages[shotId]) {
                uploadedShots[shotId] = window.motionShotImages[shotId];
            }
        }
        if (Object.keys(uploadedShots).length > 0) {
            payload.images = uploadedShots;
            console.log('[Motion] Uploaded shots:', Object.keys(uploadedShots));
        }

    } else if (window.currentVideoWorkflow === 't2v_veo3') {
        // ==========================================
        // 文字轉影片工作流 (T2V)
        // ==========================================
        if (!prompt) {
            showMotionStatus('請輸入影片描述', 'error');
            return;
        }
        payload.workflow = 't2v_veo3';
        payload.prompt = prompt;
        payload.prompts = [];
        console.log('[Motion] T2V mode, prompt:', prompt);

    } else if (window.currentVideoWorkflow === 'flf_veo3') {
        // ==========================================
        // 首尾禎動畫工作流 (FLF)
        // ==========================================
        if (!prompt) {
            showMotionStatus('請輸入過場動畫描述', 'error');
            return;
        }

        // 驗證必須上傳兩張圖片
        if (!window.flfImages.first_frame || !window.flfImages.last_frame) {
            showMotionStatus('請上傳首禎與尾禎圖片', 'error');
            return;
        }

        payload.workflow = 'flf_veo3';
        payload.prompt = prompt;
        payload.prompts = [];
        payload.images = {
            first_frame: window.flfImages.first_frame,
            last_frame: window.flfImages.last_frame
        };
        console.log('[Motion] FLF mode, prompt:', prompt, 'images:', Object.keys(payload.images));

    } else {
        showMotionStatus('未知的工作流類型', 'error');
        return;
    }

    var apiBase = (typeof API_BASE !== 'undefined') ? API_BASE : 'http://127.0.0.1:5000';


    fetch(apiBase + '/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            var jobId = data.job_id;
            if (!jobId) {
                throw new Error('No job_id received');
            }

            console.log('[Motion] Task submitted, job_id:', jobId);
            showMotionStatus('Task submitted, processing...', 'info');

            pollMotionJobStatus(jobId, apiBase);
        })
        .catch(function (error) {
            console.error('[Motion] Generation error:', error);
            showMotionStatus('Generation failed: ' + error.message, 'error');
        });
}

/**
 * Poll job status
 */
function pollMotionJobStatus(jobId, apiBase) {
    var pollCount = 0;
    var maxPolls = 300;

    var interval = setInterval(function () {
        pollCount++;

        if (pollCount > maxPolls) {
            clearInterval(interval);
            showMotionStatus('Task timeout, please check Backend', 'error');
            return;
        }

        fetch(apiBase + '/api/status/' + jobId)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                console.log('[Motion] Poll ' + pollCount + ':', data.status, '(' + (data.progress || 0) + '%)');

                if (data.status === 'finished') {
                    clearInterval(interval);

                    var videoUrl = data.image_url || data.output_path;
                    if (videoUrl) {
                        var fullVideoUrl = videoUrl.startsWith('http') ? videoUrl : (apiBase + videoUrl);

                        showMotionStatus('Video generation complete!', 'success');
                        console.log('[Motion] Video URL:', fullVideoUrl);

                        // 更新 UI 顯示結果 (使用 Motion Workspace 專用的 ID)
                        var motionPlaceholder = document.getElementById('motion-placeholder');
                        var motionResults = document.getElementById('motion-results');
                        var motionResultsGrid = document.getElementById('motion-results-grid');

                        if (motionPlaceholder && motionResults && motionResultsGrid) {
                            motionPlaceholder.classList.add('hidden');
                            motionResults.classList.remove('hidden');

                            // 清空舊結果
                            motionResultsGrid.innerHTML = '';

                            // 建立容器
                            var container = document.createElement('div');
                            container.className = 'flex flex-col items-center gap-6 w-full max-w-2xl';

                            // 判斷檔案類型 (影片或圖片)
                            var isVideo = fullVideoUrl.match(/\.(mp4|webm|mov)$/i);
                            var filename = fullVideoUrl.split('/').pop();

                            if (isVideo) {
                                // 建立影片播放器容器
                                var videoContainer = document.createElement('div');
                                videoContainer.className = 'relative w-full';

                                // 建立影片播放器
                                var video = document.createElement('video');
                                video.src = fullVideoUrl;
                                video.controls = true;
                                video.autoplay = true;
                                video.loop = true;
                                video.className = 'w-full rounded-xl shadow-2xl border border-white/10 bg-black max-h-[60vh]';
                                videoContainer.appendChild(video);
                                container.appendChild(videoContainer);
                            } else {
                                // 建立圖片預覽
                                var img = document.createElement('img');
                                img.src = fullVideoUrl;
                                img.className = 'w-full rounded-xl shadow-2xl border border-white/10 max-h-[60vh] object-contain';
                                container.appendChild(img);
                            }

                            // 建立下載按鈕容器
                            var btnContainer = document.createElement('div');
                            btnContainer.className = 'flex flex-wrap gap-3 justify-center';

                            // 建立主要下載按鈕 (使用 fetch 下載)
                            var downloadBtn = document.createElement('button');
                            downloadBtn.className = 'flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-xl font-bold transition-all shadow-lg hover:shadow-purple-500/30 hover:scale-105';
                            downloadBtn.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i> Download Video';
                            downloadBtn.onclick = function () {
                                downloadBtn.disabled = true;
                                downloadBtn.innerHTML = '<i data-lucide="loader" class="w-5 h-5 animate-spin"></i> Downloading...';

                                fetch(fullVideoUrl)
                                    .then(function (response) {
                                        if (!response.ok) throw new Error('Download failed');
                                        return response.blob();
                                    })
                                    .then(function (blob) {
                                        var url = window.URL.createObjectURL(blob);
                                        var a = document.createElement('a');
                                        a.href = url;
                                        a.download = filename || 'video.mp4';
                                        document.body.appendChild(a);
                                        a.click();
                                        document.body.removeChild(a);
                                        window.URL.revokeObjectURL(url);

                                        downloadBtn.disabled = false;
                                        downloadBtn.innerHTML = '<i data-lucide="check" class="w-5 h-5"></i> Downloaded!';
                                        if (typeof lucide !== 'undefined') lucide.createIcons();

                                        setTimeout(function () {
                                            downloadBtn.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i> Download Video';
                                            if (typeof lucide !== 'undefined') lucide.createIcons();
                                        }, 2000);
                                    })
                                    .catch(function (error) {
                                        console.error('[Motion] Download error:', error);
                                        // Fallback: 直接開啟連結
                                        window.open(fullVideoUrl, '_blank');
                                        downloadBtn.disabled = false;
                                        downloadBtn.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i> Download Video';
                                        if (typeof lucide !== 'undefined') lucide.createIcons();
                                    });
                            };
                            btnContainer.appendChild(downloadBtn);

                            // 建立「在新視窗開啟」按鈕
                            var openBtn = document.createElement('a');
                            openBtn.href = fullVideoUrl;
                            openBtn.target = '_blank';
                            openBtn.className = 'flex items-center gap-2 px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl font-bold transition-all border border-white/20 hover:scale-105';
                            openBtn.innerHTML = '<i data-lucide="external-link" class="w-5 h-5"></i> Open in New Tab';
                            btnContainer.appendChild(openBtn);

                            container.appendChild(btnContainer);

                            // 顯示檔名
                            var filenameLabel = document.createElement('p');
                            filenameLabel.className = 'text-xs text-gray-500 text-center';
                            filenameLabel.textContent = '📁 ' + filename;
                            container.appendChild(filenameLabel);

                            motionResultsGrid.appendChild(container);

                            // 重新初始化圖示
                            if (typeof lucide !== 'undefined' && lucide.createIcons) {
                                lucide.createIcons();
                            }
                        } else {
                            // Fallback if UI elements not found
                            console.error('[Motion] UI elements not found:', {
                                motionPlaceholder: !!motionPlaceholder,
                                motionResults: !!motionResults,
                                motionResultsGrid: !!motionResultsGrid
                            });
                            alert('Video generated! URL: ' + fullVideoUrl);
                        }
                    } else {
                        showMotionStatus('Task finished but no video path returned', 'warning');
                    }
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    showMotionStatus('Generation failed: ' + (data.error || 'Unknown error'), 'error');
                } else if (data.status === 'queued') {
                    showMotionStatus('🟡 排隊中，等待 Worker 處理...', 'info');
                } else if (data.status === 'processing') {
                    var progress = data.progress || 0;
                    showMotionStatus('🟢 生成中... ' + progress + '%', 'info');
                }
            })
            .catch(function (error) {
                console.error('[Motion] Poll error:', error);
            });

    }, 2000);
}

console.log('[Motion] motion-workspace.js loaded');
