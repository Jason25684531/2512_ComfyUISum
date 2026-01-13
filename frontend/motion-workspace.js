/**
 * Motion Workspace - Veo3 Long Video JavaScript Functions
 * ========================================================
 * This file contains all Motion Workspace functionality
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
    if (fileInput) {
        fileInput.click();
    }
}

/**
 * Handle file selection
 */
function handleMotionShotSelect(event, shotId) {
    var file = event.target.files[0];
    if (file && file.type.startsWith('image/')) {
        processMotionShot(file, shotId);
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
        processMotionShot(file, shotId);
    }
}

/**
 * Process and preview image
 */
function processMotionShot(file, shotId) {
    var reader = new FileReader();
    reader.onload = function (e) {
        window.motionShotImages[shotId] = e.target.result;

        var preview = document.getElementById('preview-' + shotId);
        var placeholder = document.getElementById('placeholder-' + shotId);
        var zone = document.getElementById('zone-' + shotId);

        if (preview && placeholder && zone) {
            var img = preview.querySelector('img');
            if (img) img.src = e.target.result;
            preview.classList.remove('hidden');
            placeholder.classList.add('hidden');
            zone.classList.add('has-image', 'border-solid', 'border-amber-500/50');
        }

        if (typeof lucide !== 'undefined' && lucide.createIcons) {
            lucide.createIcons();
        }
        console.log('[Motion] Shot ' + shotId + ' uploaded');
    };
    reader.readAsDataURL(file);
}

/**
 * Clear shot image
 */
function clearMotionShot(shotId) {
    window.motionShotImages[shotId] = null;

    var preview = document.getElementById('preview-' + shotId);
    var placeholder = document.getElementById('placeholder-' + shotId);
    var zone = document.getElementById('zone-' + shotId);
    var fileInput = document.getElementById('file-' + shotId);

    if (preview) preview.classList.add('hidden');
    if (placeholder) placeholder.classList.remove('hidden');
    if (zone) {
        zone.classList.remove('has-image', 'border-solid', 'border-amber-500/50');
    }
    if (fileInput) fileInput.value = '';

    console.log('[Motion] Shot ' + shotId + ' cleared');
}

/**
 * Generate video handler
 */
function handleMotionGenerate() {
    console.log('[Motion] Starting video generation...');
    showMotionStatus('Starting task submission...', 'info');

    var payload = {
        seed: -1,
        aspect_ratio: '9:16',
        model: 'veo3',
        batch_size: 1
    };

    if (window.isVeo3Mode) {
        var prompts = [];
        for (var i = 0; i < 5; i++) {
            var input = document.getElementById('veo3-segment-' + i);
            prompts.push(input ? input.value.trim() : '');
        }

        var hasContent = prompts.some(function (p) { return p.length > 0; });
        if (!hasContent) {
            showMotionStatus('Please fill at least one segment prompt', 'error');
            return;
        }

        payload.workflow = 'veo3_long_video';
        payload.prompts = prompts;
        payload.prompt = '';

        console.log('[Motion] Veo3 multi-segment mode, prompts:', prompts);
    } else {
        var promptInput = document.getElementById('motion-prompt-input');
        var prompt = promptInput ? promptInput.value.trim() : '';

        if (!prompt) {
            showMotionStatus('Please enter a video prompt', 'error');
            return;
        }

        payload.workflow = 'image_to_video';
        payload.prompt = prompt;
        payload.prompts = [];

        console.log('[Motion] Single mode, prompt:', prompt);
    }

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
                            downloadBtn.onclick = function() {
                                downloadBtn.disabled = true;
                                downloadBtn.innerHTML = '<i data-lucide="loader" class="w-5 h-5 animate-spin"></i> Downloading...';
                                
                                fetch(fullVideoUrl)
                                    .then(function(response) {
                                        if (!response.ok) throw new Error('Download failed');
                                        return response.blob();
                                    })
                                    .then(function(blob) {
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
                                        
                                        setTimeout(function() {
                                            downloadBtn.innerHTML = '<i data-lucide="download" class="w-5 h-5"></i> Download Video';
                                            if (typeof lucide !== 'undefined') lucide.createIcons();
                                        }, 2000);
                                    })
                                    .catch(function(error) {
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
                } else if (data.status === 'processing') {
                    var progress = data.progress || 0;
                    showMotionStatus('Processing... ' + progress + '%', 'info');
                }
            })
            .catch(function (error) {
                console.error('[Motion] Poll error:', error);
            });

    }, 2000);
}

console.log('[Motion] motion-workspace.js loaded');
