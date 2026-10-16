'use strict';

const $ = id => document.getElementById(id);
const toolConfig = {};
const drafts = {};
const jobs = [];
const selectedJobs = {};
const toolPollingIntervals = {};
const statusLabels = {submitting: '正在提交…', queued: '排隊中', running: '生成中', completed: '已完成', failed: '失敗', cancelled: '已取消'};
const categories = {all: '全部工具', image: '圖片', video: '影片', avatar: '數位人像'};
const fieldLabels = {source: '來源圖片', target: '目標圖片', input: '參考圖片', image: '參考圖片', extra: '額外圖片', avatar: '頭像圖片', audio: '音訊', video: '影片', first_frame: '首幀圖片', last_frame: '尾幀圖片', size: '尺寸', background: '背景', scale: '放大倍率', width: '寬度', height: '高度', duration: '秒數', video_width: '影片寬度', video_height: '影片高度', video_duration: '影片秒數', retake_start: '開始秒數', retake_end: '結束秒數'};
let catalog = [];
let currentTool = '';
let homeCategory = 'all';
let galleryStatus = 'completed';
let galleryOffset = 0;
let galleryRequest = 0;
let pendingPrompt = null;
let models = [];

function element(tag, className = '', text = '') {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
}
function button(text, action, className = 'btn') {
    const node = element('button', className, text);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
}
async function requestJSON(path, options = {}) {
    const response = await fetch(`${window.API_URL || ''}${path}`, {signal: AbortSignal.timeout(15000), ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `服務暫時無法使用（${response.status}）`);
    return data;
}
function routeFor(tool) {
    return tool.category === 'avatar' ? '#/avatar' : `#/${tool.category}/${tool.id}`;
}
function parseRoute(hash = location.hash) {
    const [, section, requested] = hash.split('/');
    if (section === 'home' || section === 'gallery') return {section};
    if (['image', 'video', 'avatar'].includes(section)) {
        const candidates = catalog.filter(tool => tool.category === section);
        const fallback = section === 'video' ? 'ltx_i2v' : section === 'image' ? 'text_to_image' : 'virtual_human';
        const tool = candidates.find(item => item.id === window.normalizeStudioWorkflowId(requested || fallback)) || candidates.find(item => item.id === fallback) || candidates[0];
        if (tool) return {section, tool};
    }
    return {section: 'home'};
}
function openTool(tool, prompt) {
    if (prompt !== undefined) pendingPrompt = {tool: tool.id, prompt};
    const route = routeFor(tool);
    if (location.hash === route) render();
    else location.hash = route;
}
function saveToolState() {
    if (!currentTool || !drafts[currentTool]) return;
    const state = drafts[currentTool];
    state.prompt = $('prompt-input').value;
    state.seed = $('seed-input').value;
    state.model = $('model-select').value;
    document.querySelectorAll('[data-runtime-input]').forEach(control => {
        if (!control.closest('[hidden]')) state.values[control.dataset.runtimeInput] = control.value;
    });
}
function render() {
    saveToolState();
    const route = parseRoute();
    const canonical = route.tool ? routeFor(route.tool) : `#/${route.section}`;
    if (location.hash !== canonical) history.replaceState(null, '', canonical);
    $('view-home').hidden = route.section !== 'home';
    $('view-workspace').hidden = !route.tool;
    $('view-gallery').hidden = route.section !== 'gallery';
    document.querySelectorAll('[data-sec]').forEach(link => {
        if (link.dataset.sec === route.section) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
    });
    currentTool = route.tool?.id || '';
    if (route.tool) {
        if (!drafts[currentTool]) drafts[currentTool] = {prompt: '', seed: '-1', model: '', ratio: '1:1', batch: 1, files: {}, images: {}, values: {...toolConfig[currentTool].defaults}};
        if (pendingPrompt?.tool === currentTool) {
            drafts[currentTool].prompt = pendingPrompt.prompt;
            pendingPrompt = null;
        }
        renderWorkspace(route.tool);
    } else if (route.section === 'gallery') loadHistory();
    else loadRecentWorks();
    syncHeroVideo();
}
function toolCard(tool, closePicker = false) {
    const node = button('', () => {
        if (closePicker) $('tool-picker').close();
        openTool(tool);
    }, 'tool-card');
    node.dataset.workflow = tool.id;
    node.dataset.category = tool.category;
    const icon = element('span', 'ic');
    const glyph = element('i'); glyph.dataset.lucide = tool.frontend.icon || 'sparkles'; icon.append(glyph);
    node.append(element('span', 'tag', categories[tool.category]), icon, element('b', '', tool.frontend.title), element('small', '', tool.frontend.description));
    return node;
}
function renderToolGrid() {
    $('tool-grid').replaceChildren(...catalog.filter(tool => homeCategory === 'all' || tool.category === homeCategory).map(tool => toolCard(tool)));
    window.lucide?.createIcons();
}
function renderFilters(container, options, selected, onSelect) {
    container.replaceChildren(...Object.entries(options).map(([value, label]) => {
        const control = button(label, () => onSelect(value), 'tab');
        control.setAttribute('aria-pressed', String(selected === value));
        return control;
    }));
}
function renderHomeFilters() {
    renderFilters($('tool-filters'), categories, homeCategory, value => { homeCategory = value; renderHomeFilters(); renderToolGrid(); });
}
function addField(container, name, type, value, choices = []) {
    const label = element('label', 'field');
    label.append(element('span', 'lbl', fieldLabels[name] || name.replaceAll('_', ' ')));
    const control = element(choices.length ? 'select' : 'input', 'input');
    control.dataset.runtimeInput = name;
    control.id = `runtime-${name}`;
    if (choices.length) choices.forEach(choice => {
        const option = element('option', '', `${choice}${toolConfig[currentTool].units[name] || ''}`);
        option.value = String(choice); control.append(option);
    });
    else { control.type = type; if (type === 'number') control.step = 'any'; }
    control.value = String(value ?? '');
    label.append(control); container.append(label);
    return control;
}
function renderWorkspace(tool) {
    const config = toolConfig[tool.id];
    const state = drafts[tool.id];
    $('current-tool-name').textContent = tool.frontend.title;
    $('current-tool-desc').textContent = tool.frontend.description;
    $('view-workspace').dataset.category = tool.category;
    const icon = element('i'); icon.dataset.lucide = tool.frontend.icon || 'sparkles';
    $('current-tool-icon').replaceChildren(icon);
    $('prompt-input').value = state.prompt;
    $('seed-input').value = state.seed;
    $('prompt-field').hidden = tool.id === 'multi_angle' || (config.requiredInputs.length > 0 && ![...config.requiredInputs, ...config.optionalInputs].includes('prompt'));
    $('image-settings').hidden = tool.category !== 'image' || tool.id === 'image_upscale_seedvr2';
    $('model-field').hidden = tool.id !== 'text_to_image';
    $('model-select').replaceChildren();
    const defaultOption = element('option', '', '使用工作流程預設模型'); defaultOption.value = '';
    $('model-select').append(defaultOption);
    models.forEach(model => {
        const value = typeof model === 'object' ? model.value ?? model.id ?? '' : String(model);
        const option = element('option', '', typeof model === 'object' ? model.name || value : value.split(/[\\/]/).pop().replace('.safetensors', ''));
        option.value = value; $('model-select').append(option);
    });
    $('model-select').value = state.model;
    renderFilters($('ratio-controls'), {'1:1': '1:1', '16:9': '16:9', '9:16': '9:16', '2:3': '2:3'}, state.ratio, value => { state.ratio = value; renderRatioControls(); });
    renderFilters($('batch-controls'), {1: '1', 2: '2', 4: '4'}, String(state.batch), value => { state.batch = Number(value); renderRatioControls(); });
    $('runtime-inputs').replaceChildren();
    const names = [...new Set([...config.requiredInputs, ...config.optionalInputs])];
    names.forEach(name => {
        const type = config.inputTypes[name];
        if (['prompt', 'seed'].includes(name) || !['select', 'number', 'text'].includes(type)) return;
        addField($('runtime-inputs'), name, type === 'number' ? 'number' : 'text', state.values[name], config.choices[name] || []);
    });
    if (['ltx_i2v', 'ltx_flf'].includes(tool.id)) {
        [['video_width', 1280, 512, 1920], ['video_height', 720, 512, 1920], ['video_duration', 5, 1, 10]].forEach(([name, value, min, max]) => {
            const control = addField($('runtime-inputs'), name, 'number', state.values[name] ?? value);
            control.min = min; control.max = max; control.step = '1';
        });
    }
    if (tool.id === 'ltx_retake_v2v') {
        addField($('runtime-inputs'), 'retake_start', 'number', state.values.retake_start ?? 0).min = '0';
        addField($('runtime-inputs'), 'retake_end', 'number', state.values.retake_end ?? 5).min = '0';
    }
    $('advanced-settings').open = tool.category === 'video';
    $('upload-zones').replaceChildren(...config.uploads.map(upload => uploadControl(tool.id, upload)));
    $('multiangle-fields').hidden = tool.id !== 'multi_angle';
    if (tool.id === 'multi_angle' && !window.multiangleCameraControl) window.multiangleCameraControl = new MultiangleCameraControl($('multiangle-fields'));
    const regional = tool.id === 'ideogram4_regional_t2i';
    $('regional-fields').hidden = !regional;
    $('regional-canvas-mount').hidden = !regional;
    if (!regional) $('regional-fields').replaceChildren();
    if (regional) {
        if (!window.regionalCanvasEditor) window.regionalCanvasEditor = new RegionalCanvasEditor($('regional-canvas-mount'));
        $('regional-fields').replaceChildren();
        [['background', ''], ['aesthetics', ''], ['lighting', ''], ['medium', 'Photograph'], ['width', 1080], ['height', 1920]].forEach(([name, fallback]) => {
            const dimension = ['width', 'height'].includes(name);
            const control = addField($('regional-fields'), name, dimension ? 'number' : 'text', state.values[name] ?? fallback);
            if (dimension) {
                control.min = '256'; control.max = '4096'; control.step = '1';
                control.addEventListener('input', () => window.regionalCanvasEditor.setAspect(Number($('runtime-width').value), Number($('runtime-height').value)));
            }
        });
        window.regionalCanvasEditor.setAspect(Number($('runtime-width').value), Number($('runtime-height').value));
    }
    $('status-message').textContent = '';
    renderStage(selectedJobs[currentTool]); renderHistoryStrip(currentTool);
    window.lucide?.createIcons();
}
function renderRatioControls() {
    const state = drafts[currentTool];
    for (const [id, selected] of [['ratio-controls', state.ratio], ['batch-controls', String(state.batch)]]) {
        $(id).querySelectorAll('button').forEach(control => control.setAttribute('aria-pressed', String(control.textContent === selected)));
    }
}
function uploadControl(tool, upload) {
    const state = drafts[tool];
    const zone = element('div', 'upload-field');
    const label = element('label', 'up');
    const name = upload.label;
    const input = element('input'); input.type = 'file'; input.id = `file-${upload.id}`;
    input.accept = upload.type === 'audio' ? '.wav,.mp3' : upload.type === 'video' ? '.mp4,.mov' : 'image/*';
    label.htmlFor = input.id; input.setAttribute('aria-label', name);
    const preview = element('img', 'upload-preview'); preview.alt = name; preview.hidden = !state.images[upload.id];
    if (state.images[upload.id]) preview.src = state.images[upload.id];
    const caption = element('span', '', state.files[upload.id]?.name || `${name}${upload.optional ? '（選填）' : ''}`);
    label.append(preview, element('span', 'upload-symbol', '+'), caption, input);
    const clear = button('移除', () => {
        delete state.files[upload.id]; delete state.images[upload.id];
        input.value = ''; preview.removeAttribute('src'); preview.hidden = true;
        caption.textContent = name; clear.hidden = true;
    }, 'btn sm');
    clear.setAttribute('aria-label', `移除${name}`); clear.hidden = !state.files[upload.id];
    const accept = async file => {
        if (!file) return;
        try {
            if (upload.type === 'image' && !file.type.startsWith('image/')) throw new Error('請選擇圖片檔案');
            const data = upload.type === 'image' ? await fileToBase64(file) : null;
            state.files[upload.id] = file;
            if (data) { state.images[upload.id] = data; preview.src = data; preview.hidden = false; }
            caption.textContent = file.name; clear.hidden = false;
        } catch (error) { if (currentTool === tool) $('status-message').textContent = error.message; }
    };
    input.addEventListener('change', () => accept(input.files[0]));
    zone.addEventListener('dragover', event => event.preventDefault());
    zone.addEventListener('drop', event => { event.preventDefault(); accept(event.dataTransfer.files[0]); });
    zone.append(label, clear);
    return zone;
}
// Existing FileReader upload contract, shared by image, motion and avatar.
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}
async function uploadVideoFile(file) {
    const formData = new FormData(); formData.append('file', file);
    const data = await requestJSON('/api/upload', {method: 'POST', body: formData});
    if (!data.filename) throw new Error('影片上傳失敗，請重試');
    return data.filename;
}
function validateInputs(tool, state, config) {
    for (const upload of config.uploads) {
        if (!upload.optional && !state.files[upload.id]) return `請先上傳『${upload.label}』`;
    }
    if (config.promptRequired && !state.prompt.trim()) return '請輸入提示詞';
    if (!$('workspace-form').checkValidity()) return '請檢查數值範圍與格式';
    if (tool.id === 'ltx_retake_v2v' && !(Number(state.values.retake_start) >= 0 && Number(state.values.retake_end) > Number(state.values.retake_start))) return '開始秒數需 ≥ 0 且小於結束秒數';
    if (tool.id === 'ideogram4_regional_t2i') {
        const result = window.regionalCanvasEditor.validate();
        if (!result.valid) { window.regionalCanvasEditor.selectIndex(result.index); return result.message; }
    }
    return '';
}

// Payload fields retain the legacy generate contract and specialised controls.
async function handleGenerate() {
    const tool = catalog.find(item => item.id === currentTool);
    if (!tool || jobs.some(job => job.tool === tool.id && ['submitting', 'queued', 'running'].includes(job.status))) return;
    saveToolState();
    const state = drafts[tool.id];
    const config = toolConfig[tool.id];
    const error = validateInputs(tool, state, config);
    if (error) { $('status-message').textContent = error; return; }
    const job = {id: '', tool: tool.id, prompt: state.prompt.trim(), status: 'submitting', progress: 0, outputs: [], error: '', ratio: state.ratio, type: tool.category === 'image' ? 'image' : 'video'};
    jobs.unshift(job); selectedJobs[tool.id] = job;
    renderStage(job); renderHistoryStrip(tool.id);
    try {
        let payload = {
            workflow: tool.id, prompt: job.prompt, seed: Number(state.seed), model: state.model,
            aspect_ratio: state.ratio, batch_size: state.batch,
            images: config.inputTypes.images === 'multi-image'
                ? config.uploads.filter(upload => upload.field === 'images').map(upload => state.images[upload.id]).filter(Boolean)
                : {...state.images}
        };
        const extraParams = {};
        for (const name of [...config.requiredInputs, ...config.optionalInputs]) {
            if (['prompt', 'seed'].includes(name) || !['select', 'number', 'text'].includes(config.inputTypes[name])) continue;
            const value = state.values[name];
            if (value === undefined || value === '') continue;
            const choice = (config.choices[name] || []).find(item => String(item) === String(value));
            extraParams[name] = choice ?? (config.inputTypes[name] === 'number' ? Number(value) : value);
        }
        if (Object.keys(extraParams).length) payload.extra_params = extraParams;
        if (tool.id === 'ideogram4_regional_t2i') {
            payload.width = Number(state.values.width); payload.height = Number(state.values.height);
            payload.elements_data = window.regionalCanvasEditor.getElementsData();
            for (const field of ['background', 'aesthetics', 'lighting', 'medium']) payload[field] = state.values[field] || '';
        }
        if (tool.id === 'multi_angle') Object.assign(payload, window.multiangleCameraControl.getValues());
        if (tool.category === 'video') payload = await handleMotionGenerate(payload, tool.id, state);
        if (tool.category === 'avatar') payload = await generateAvatarVideo(payload, state);
        const data = await requestJSON('/api/generate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
        if (!data.job_id) throw new Error('生成服務暫時無回應，請重試');
        job.id = data.job_id; job.status = 'queued';
        pollStatus(job);
    } catch (error) { job.status = 'failed'; job.error = error.message || '生成失敗，請重試'; }
    updateJob(job);
}
async function handleMotionGenerate(payload, currentVideoTool, state) {
    payload.workflow = currentVideoTool;
    if (currentVideoTool === 'ltx_i2v' || currentVideoTool === 'ltx_flf') {
        for (const name of ['video_width', 'video_height', 'video_duration']) payload[name] = Number(state.values[name]);
    } else if (currentVideoTool === 'ltx_retake_v2v') {
        payload.video = await uploadVideoFile(state.files.video);
        payload.retake_start = Number(state.values.retake_start);
        payload.retake_end = Number(state.values.retake_end);
        delete payload.images;
    }
    return payload;
}
async function generateAvatarVideo(payload, state) {
    payload.workflow = 'virtual_human';
    payload.images = {avatar: state.images.avatar};
    payload.audio = await fileToBase64(state.files.audio);
    return payload;
}
function normalizeJobStatus(data) {
    const status = String(data?.status || data?.state || '').toLowerCase();
    if (['finished', 'success', 'succeeded'].includes(status)) return 'completed';
    if (status === 'processing') return 'running';
    return status;
}
function pickJobOutputPath(data) {
    return data.image_path || data.image_url || data.result_url || data.output_url || data.url || data.output?.url || data.result?.url || data.output_path || (typeof data.result === 'string' ? data.result : '');
}
function resolveOutputUrl(outputPath) {
    if (typeof outputPath !== 'string' || !outputPath) return '';
    const path = outputPath.replace(/\\/g, '/');
    if (/^\/outputs\/[A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(path)) return path;
    // Legacy worker responses can contain a filesystem path; expose only the validated basename.
    if (path.includes('://')) return '';
    const filename = path.split('/').pop();
    return /^[A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(filename) ? `/outputs/${filename}` : '';
}
function pollStatus(job) {
    clearInterval(toolPollingIntervals[job.tool]);
    let pollCount = 0;
    let checking = false;
    const deadline = Date.now() + 40 * 60 * 1000;
    toolPollingIntervals[job.tool] = setInterval(async () => {
        if (Date.now() >= deadline || ++pollCount > 1200) {
            job.status = 'failed'; job.error = '生成逾時：已超過 40 分鐘，請重試';
            stopPolling(job); updateJob(job); return;
        }
        if (checking) return;
        checking = true;
        try {
            const data = await requestJSON(`/api/status/${encodeURIComponent(job.id)}`);
            if (!['queued', 'running'].includes(job.status)) return;
            const status = normalizeJobStatus(data);
            if (['queued', 'running', 'completed', 'failed', 'cancelled'].includes(status)) job.status = status;
            job.progress = Math.max(0, Math.min(100, Number(data.progress) || 0));
            job.reconnecting = false;
            if (job.status === 'completed') {
                const paths = Array.isArray(data.outputs) ? data.outputs.map(item => typeof item === 'string' ? item : pickJobOutputPath(item)) : [pickJobOutputPath(data)];
                job.outputs = [...new Set(paths.map(resolveOutputUrl).filter(Boolean))];
                if (!job.outputs.length) { job.status = 'failed'; job.error = '任務已完成，但沒有可用的輸出，請重試'; }
                if (job.tool === 'ideogram4_regional_t2i' && job.outputs[0]) window.regionalCanvasEditor?.setBackgroundImage(job.outputs[0]);
            } else if (job.status === 'failed') job.error = data.error || '生成失敗，請重試';
            if (['completed', 'failed', 'cancelled'].includes(job.status)) stopPolling(job);
        } catch (_) { if (['queued', 'running'].includes(job.status)) job.reconnecting = true; }
        finally { checking = false; updateJob(job); }
    }, 2000);
}
function stopPolling(job) {
    clearInterval(toolPollingIntervals[job.tool]);
    delete toolPollingIntervals[job.tool];
}
function updateJob(job) {
    if (currentTool === job.tool) {
        if (selectedJobs[currentTool] === job) renderStage(job);
        renderHistoryStrip(job.tool);
    }
}
async function cancelJob(job) {
    if (job.cancelling) return;
    job.cancelling = true; updateJob(job);
    try {
        await requestJSON(`/api/cancel/${encodeURIComponent(job.id)}`, {method: 'POST'});
        job.status = 'cancelled'; job.error = ''; stopPolling(job);
    } catch (error) { job.notice = `取消失敗：${error.message}`; }
    finally { job.cancelling = false; updateJob(job); }
}
function mediaElement(url, type, title) {
    if (!/^\/outputs\/[A-Za-z0-9_-][A-Za-z0-9_.-]*$/.test(url)) return null;
    const media = element(type === 'video' ? 'video' : 'img');
    media.src = `${window.API_URL || ''}${url}`;
    if (type === 'video') { media.controls = true; media.preload = 'metadata'; }
    else { media.alt = title; media.loading = 'lazy'; }
    media.addEventListener('error', () => {
        media.closest('.g-item, .result')?.querySelectorAll('a[download]').forEach(link => {
            if (link.href === media.src) link.replaceWith(element('span', 'help', '無法下載'));
        });
        media.replaceWith(element('p', 'note missing-output', '檔案已清除或無法載入'));
    }, {once: true});
    return media;
}
function reuseJob(job) {
    const tool = catalog.find(item => item.id === (job.tool || job.workflow));
    if (tool) openTool(tool, job.prompt || '');
}
function renderStage(job) {
    const stage = $('result-stage');
    const active = jobs.some(item => item.tool === currentTool && ['submitting', 'queued', 'running'].includes(item.status));
    $('btn-generate').disabled = active;
    $('btn-generate').textContent = active ? '生成中…' : '開始生成 ↗';
    if (!job) { stage.replaceChildren(element('div', 'stage-empty', '你的下一件作品，從這裡開始。\n完成左側設定後，開始生成。')); return; }
    const busy = ['submitting', 'queued', 'running'].includes(job.status);
    const content = element('div', busy ? 'run' : 'results');
    const status = element('p', job.status === 'failed' ? 'err' : 'stage-status', statusLabels[job.status]);
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    if (busy) {
        const skeleton = element('div', 'skeleton'); skeleton.style.aspectRatio = (job.type === 'video' ? '16:9' : job.ratio).replace(':', '/');
        const progress = element('progress'); progress.max = 100; progress.value = job.progress;
        progress.setAttribute('aria-label', '生成進度');
        content.append(skeleton, status, progress, element('p', 'help', `${job.progress}%`));
        if (job.reconnecting) content.append(element('p', 'help', '重新連線中…'));
        if (job.notice) content.append(element('p', 'err', job.notice));
        if (job.id) content.append(button(job.cancelling ? '取消中…' : '取消', () => cancelJob(job)));
    } else {
        content.append(status);
        for (const url of job.outputs) {
            const media = mediaElement(url, job.type, '生成結果');
            if (!media) continue;
            const figure = element('figure', 'result');
            const download = element('a', 'btn sm', '下載'); download.href = `${window.API_URL || ''}${url}`; download.download = '';
            figure.append(media, download); content.append(figure);
        }
        if (job.error) content.append(element('p', 'err', job.error));
        content.append(button(job.status === 'completed' ? '再生成' : '重試', () => handleGenerate(), 'btn primary'));
    }
    stage.replaceChildren(content);
}
function renderHistoryStrip(tool) {
    $('tool-history').replaceChildren(...jobs.filter(job => job.tool === tool).map((job, index) => {
        const control = button('', () => { selectedJobs[tool] = job; renderStage(job); renderHistoryStrip(tool); });
        control.setAttribute('aria-label', `任務 ${index + 1}：${statusLabels[job.status]}`);
        control.setAttribute('aria-pressed', String(selectedJobs[tool] === job));
        if (job.outputs[0] && job.type === 'image') control.append(mediaElement(job.outputs[0], 'image', '作品縮圖'));
        control.append(element('span', 'st', statusLabels[job.status]));
        return control;
    }));
}
function historyCard(item) {
    const card = element('article', 'g-item');
    const tool = catalog.find(tool => tool.id === item.workflow);
    const media = mediaElement(item.output_url, item.output_type, item.prompt || '作品');
    if (media) card.append(media);
    const info = element('div', 'info');
    info.append(element('b', '', tool?.frontend.title || item.workflow), element('p', '', item.prompt || '—'));
    const timestamp = Date.parse(item.created_at);
    const seconds = Math.round((timestamp - Date.now()) / 1000);
    const unit = Math.abs(seconds) < 3600 ? 'minute' : Math.abs(seconds) < 86400 ? 'hour' : 'day';
    const time = Number.isFinite(timestamp) ? new Intl.RelativeTimeFormat('zh-TW', {numeric: 'auto'}).format(Math.round(seconds / ({minute: 60, hour: 3600, day: 86400}[unit])), unit) : '—';
    info.append(element('small', '', `${statusLabels[item.status] || item.status} · ${time}`));
    if (item.error) info.append(element('p', 'err', item.error));
    const actions = element('div', 'row');
    if (media) { const link = element('a', 'btn sm', '下載'); link.href = media.src; link.download = ''; actions.append(link); }
    if (tool) actions.append(button('再生成', () => reuseJob(item), 'btn sm'));
    info.append(actions); card.append(info);
    return card;
}
function historyError(container, retry) {
    const banner = element('div', 'banner', '作品載入失敗');
    banner.append(button('重試', retry, 'btn sm')); container.replaceChildren(banner);
}
async function loadRecentWorks() {
    const container = $('recent-works'); container.textContent = '載入作品中…';
    try {
        const data = await requestJSON('/api/history?limit=6&status=completed');
        container.replaceChildren(...data.items.map(historyCard));
        if (!data.items.length) container.append(element('p', 'help', '目前沒有作品，開始你的第一件創作。'));
    } catch (_) { historyError(container, loadRecentWorks); }
}
function renderGalleryFilters() {
    renderFilters($('gallery-filters'), {all: '全部', completed: '完成', running: '生成中', failed: '失敗'}, galleryStatus, value => { galleryStatus = value; renderGalleryFilters(); loadHistory(); });
}
async function loadHistory(append = false) {
    const sequence = ++galleryRequest;
    if (!append) { galleryOffset = 0; $('gallery-grid').replaceChildren(); }
    const offset = galleryOffset;
    $('load-more').hidden = true; $('gallery-notice').textContent = '載入作品中…';
    try {
        const data = await requestJSON(`/api/history?status=${galleryStatus}&offset=${offset}&limit=24`);
        if (sequence !== galleryRequest) return;
        $('gallery-notice').replaceChildren(); $('gallery-grid').append(...data.items.map(historyCard));
        galleryOffset = offset + data.items.length;
        $('load-more').hidden = !data.items.length || galleryOffset >= data.total;
        if (!galleryOffset) {
            const empty = element('div', 'empty', '目前沒有作品');
            const link = element('a', 'btn', '開始創作'); link.href = '#/image/text_to_image';
            empty.append(link); $('gallery-notice').append(empty);
        }
    } catch (_) { if (sequence === galleryRequest) historyError($('gallery-notice'), () => loadHistory(append)); }
}
async function checkHealth() {
    let healthy = false;
    try { const data = await requestJSON('/api/health'); healthy = ['ok', 'healthy'].includes(data.status); } catch (_) { /* Render a controlled offline indicator. */ }
    $('system-status').querySelector('.dot').classList.toggle('offline', !healthy);
    $('system-status').querySelector('span').textContent = healthy ? '系統正常' : '連線異常';
    $('system-status').setAttribute('aria-label', healthy ? '系統正常' : '連線異常');
}
let heroPaused = false;
function syncHeroVideo() {
    const video = $('hero-video');
    const play = !heroPaused && !$('view-home').hidden && !matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (play) video.play().catch(() => {}); else video.pause();
    const label = video.paused ? '播放動畫' : '暫停動畫';
    $('pause-hero').textContent = label; $('pause-hero').setAttribute('aria-label', label);
    $('pause-hero').setAttribute('aria-pressed', String(!video.paused));
}
document.addEventListener('DOMContentLoaded', async () => {
    await window.STUDIO_RUNTIME_READY;
    // image_to_video had no reachable workspace in the legacy UI; keep the four supported motion tools.
    catalog = window.getStudioWorkflowCatalog().filter(tool => tool.category !== 'video' || ['ltx_i2v', 'ltx_flf', 'ltx_retake_v2v', 'video_minimax_h3'].includes(tool.id));
    Object.assign(toolConfig, window.buildStudioImageToolConfig());
    catalog.forEach(tool => {
        const config = toolConfig[tool.id] ||= {uploads: [], requiredInputs: [], optionalInputs: [], inputTypes: {}, choices: {}, units: {}, defaults: {}};
        config.uploads.forEach(upload => {
            upload.type = 'image'; upload.optional = config.optionalInputs.includes(upload.field);
            upload.label = fieldLabels[upload.field] || upload.label;
            if (config.inputTypes[upload.field] === 'multi-image') upload.label = `參考圖片 ${Number(upload.id.split('.').pop()) + 1}`;
            if (upload.field === 'extra') upload.optional = true;
        });
        if (tool.id === 'ltx_i2v' || tool.id === 'ltx_flf') config.uploads = (tool.id === 'ltx_i2v' ? ['input'] : ['first_frame', 'last_frame']).map(id => ({id, field: id, label: fieldLabels[id], type: 'image'}));
        if (tool.id === 'ltx_retake_v2v') config.uploads = [{id: 'video', label: '影片', type: 'video'}];
        if (tool.id === 'virtual_human') config.uploads = [{id: 'avatar', label: '頭像圖片', type: 'image'}, {id: 'audio', label: '音訊', type: 'audio'}];
        config.promptRequired = ['text_to_image', 'ideogram4_regional_t2i', 'ltx_i2v', 'ltx_flf', 'ltx_retake_v2v'].includes(tool.id) || config.requiredInputs.includes('prompt');
        const option = element('option', '', tool.frontend.title); option.value = tool.id; $('hero-tool').append(option);
    });
    $('catalog-error').hidden = catalog.length > 0;
    renderHomeFilters(); renderToolGrid(); renderGalleryFilters();
    $('workspace-form').addEventListener('submit', event => { event.preventDefault(); handleGenerate(); });
    $('hero-form').addEventListener('submit', event => { event.preventDefault(); const tool = catalog.find(item => item.id === $('hero-tool').value); if (tool) openTool(tool, $('hero-prompt').value); });
    $('tool-switch').addEventListener('click', () => {
        const category = catalog.find(tool => tool.id === currentTool)?.category;
        $('picker-grid').replaceChildren(...catalog.filter(tool => tool.category === category).map(tool => toolCard(tool, true)));
        window.lucide?.createIcons(); $('tool-picker').showModal();
    });
    $('close-picker').addEventListener('click', () => $('tool-picker').close());
    $('tool-picker').addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const controls = [...$('tool-picker').querySelectorAll('button')];
        const first = controls[0], last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    $('load-more').addEventListener('click', () => loadHistory(true));
    $('pause-hero').addEventListener('click', () => {
        heroPaused = !$('hero-video').paused;
        if (!heroPaused && matchMedia('(prefers-reduced-motion: reduce)').matches) $('hero-video').play().catch(() => {});
        else syncHeroVideo();
    });
    $('hero-video').addEventListener('play', () => { $('pause-hero').textContent = '暫停動畫'; $('pause-hero').setAttribute('aria-label', '暫停動畫'); });
    matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', syncHeroVideo);
    window.addEventListener('hashchange', render);
    render(); checkHealth(); setInterval(checkHealth, 30000);
    try {
        const data = await requestJSON('/api/models');
        models = data.by_task_type?.text_to_image || data.unet_models || data.models || [];
        if (currentTool === 'text_to_image') { saveToolState(); renderWorkspace(catalog.find(tool => tool.id === currentTool)); }
    } catch (_) { /* Workflow defaults remain selectable when model discovery is unavailable. */ }
});
