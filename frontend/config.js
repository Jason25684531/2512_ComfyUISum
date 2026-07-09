const _API_ORIGIN_LOCAL = "http://localhost:5000";

const _isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const _isFileProtocol = window.location.protocol === "file:";
const _currentPort = window.location.port;

const _isServedByFlask = _isLocalhost && (_currentPort === "5000" || _currentPort === "");
const _isServedByFastAPI = _isLocalhost && _currentPort === "8000";
const _isServedByProxy = !_isLocalhost && !_isFileProtocol;
const _defaultApiOrigin = (_isServedByFlask || _isServedByProxy || _isServedByFastAPI)
    ? window.location.origin
    : _API_ORIGIN_LOCAL;

const _fallbackWorkflowCatalog = [
    { id: "text_to_image", aliases: [], category: "image", frontend: { title: "Text to Image", description: "文字生圖", icon: "type", color: "blue", inputs: [] } },
    { id: "face_swap", aliases: [], category: "image", frontend: { title: "Face Swap", description: "換臉", icon: "users", color: "purple", inputs: ["source", "target"] } },
    { id: "multi_image_blend", aliases: ["multi_blend"], category: "image", frontend: { title: "Multi-Blend", description: "多圖融合", icon: "layers-3", color: "amber", inputs: ["source", "target", "extra"] } },
    { id: "sketch_to_image", aliases: ["sketch"], category: "image", frontend: { title: "Sketch to Image", description: "草圖轉圖", icon: "pencil", color: "emerald", inputs: ["input"] } },
    { id: "image_edit", aliases: ["single_image_edit", "single_edit"], category: "image", frontend: { title: "Image Edit", description: "單圖編輯", icon: "image", color: "pink", inputs: ["input"] } },
    { id: "virtual_human", aliases: ["avatar_talk"], category: "avatar", frontend: { title: "Avatar Talk", description: "數位人像", icon: "mic", color: "teal", inputs: ["avatar"] } },
    { id: "veo3_long_video", aliases: [], category: "video", frontend: { title: "Veo3 Long Video", description: "多鏡頭長影片", icon: "video", color: "cyan", inputs: ["shot_0", "shot_1", "shot_2", "shot_3", "shot_4"] } },
    { id: "image_to_video", aliases: [], category: "video", frontend: { title: "Image to Video", description: "圖生影片", icon: "clapperboard", color: "sky", inputs: ["shot_0"] } },
    { id: "t2v_veo3", aliases: ["T2V"], category: "video", frontend: { title: "T2V", description: "文字轉影片", icon: "sparkles", color: "indigo", inputs: [] } },
    { id: "flf_veo3", aliases: ["FLF"], category: "video", frontend: { title: "FLF", description: "首尾幀動畫", icon: "film", color: "rose", inputs: ["first_frame", "last_frame"] } },
    { id: "ltx_retake_v2v", aliases: [], category: "video", frontend: { title: "影片重生成 ReTake", description: "上傳影片並重新生成指定時間區段", icon: "redo-2", color: "orange", inputs: ["video"] } },
    { id: "ideogram4_regional_t2i", aliases: [], category: "image", frontend: { title: "區域提示詞 Regional Prompt", description: "以 BBox 畫布指定各區域內容並生成圖片", icon: "layout-grid", color: "cyan", inputs: [] } }
];

window.API_URL = _defaultApiOrigin;
window.API_BASE_URL = `${window.API_URL}/api`;
window.API_BASE = window.API_URL;
window.STUDIO_RUNTIME_CONFIG = {
    api_origin: window.API_URL,
    runtime_profile: "unknown",
    deployment_topology: "local-dev",
    workflow_catalog: _fallbackWorkflowCatalog
};

function _buildWorkflowAliasIndex(catalog) {
    const aliasIndex = {};
    catalog.forEach((entry) => {
        aliasIndex[entry.id] = entry.id;
        (entry.aliases || []).forEach((alias) => {
            aliasIndex[alias] = entry.id;
        });
    });
    return aliasIndex;
}

function _getWorkflowCatalog() {
    return Array.isArray(window.STUDIO_RUNTIME_CONFIG.workflow_catalog)
        ? window.STUDIO_RUNTIME_CONFIG.workflow_catalog
        : _fallbackWorkflowCatalog;
}

window.normalizeStudioWorkflowId = function normalizeStudioWorkflowId(workflowId) {
    const requested = String(workflowId || "text_to_image");
    const aliasIndex = _buildWorkflowAliasIndex(_getWorkflowCatalog());
    return aliasIndex[requested] || requested;
};

window.getStudioWorkflowCatalog = function getStudioWorkflowCatalog() {
    return _getWorkflowCatalog().map((entry) => ({
        ...entry,
        id: window.normalizeStudioWorkflowId(entry.id)
    }));
};

window.buildStudioToolStates = function buildStudioToolStates(previousStates = {}) {
    const nextStates = {};
    window.getStudioWorkflowCatalog()
        .filter((entry) => entry.category === "image")
        .forEach((entry) => {
            nextStates[entry.id] = {
                prompt: "",
                images: {},
                canvasHtml: "",
                canvasHidden: true,
                isGenerating: false,
                ...(previousStates[entry.id] || {})
            };
        });
    return nextStates;
};

window.buildStudioImageToolConfig = function buildStudioImageToolConfig() {
    const config = {};
    window.getStudioWorkflowCatalog()
        .filter((entry) => entry.category === "image")
        .forEach((entry) => {
            config[entry.id] = {
                uploads: (entry.frontend.inputs || []).map((inputId) => ({
                    id: inputId,
                    label: inputId
                        .split("_")
                        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
                        .join(" "),
                    icon: inputId === "input" ? "image" : (inputId === "source" ? "user" : "image")
                })),
                color: entry.frontend.color
            };
        });
    return config;
};

window.buildStudioToolInfo = function buildStudioToolInfo() {
    const info = {};
    window.getStudioWorkflowCatalog()
        .filter((entry) => entry.category === "image")
        .forEach((entry) => {
            info[entry.id] = {
                name: entry.frontend.title,
                desc: entry.frontend.description,
                icon: entry.frontend.icon,
                color: entry.frontend.color
            };
        });
    return info;
};

window.STUDIO_RUNTIME_READY = (async () => {
    try {
        const response = await fetch(`${window.API_URL}/api/runtime-config`, {
            credentials: "include"
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const payload = await response.json();
        if (payload && Array.isArray(payload.workflow_catalog)) {
            window.STUDIO_RUNTIME_CONFIG = {
                ...window.STUDIO_RUNTIME_CONFIG,
                ...payload,
                api_origin: payload.api_origin || window.API_URL
            };
            window.API_URL = window.STUDIO_RUNTIME_CONFIG.api_origin;
            window.API_BASE = window.API_URL;
            window.API_BASE_URL = `${window.API_URL}/api`;
        }
    } catch (error) {
        console.warn("[RuntimeConfig] Falling back to built-in workflow catalog:", error.message);
    }

    return window.STUDIO_RUNTIME_CONFIG;
})();

console.log("API Origin:", window.API_URL);
console.log("API Base URL:", window.API_BASE_URL);
console.log("Served by Flask:", _isServedByFlask);
console.log("Served by Nginx/LB:", _isServedByProxy);
