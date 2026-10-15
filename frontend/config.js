const _API_ORIGIN_LOCAL = "http://localhost:5000";

const _isLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const _currentPort = window.location.port;

const _isServedByFlask = _isLocalhost && (_currentPort === "5000" || _currentPort === "");
const _isServedByFastAPI = _isLocalhost && _currentPort === "8000";
const _defaultApiOrigin = (_isServedByFlask || _isServedByFastAPI)
    ? window.location.origin
    : _API_ORIGIN_LOCAL;

window.API_URL = _defaultApiOrigin;
window.API_BASE_URL = `${window.API_URL}/api`;
window.API_BASE = window.API_URL;
window.STUDIO_RUNTIME_CONFIG = {
    api_origin: window.API_URL,
    runtime_profile: "unknown",
    deployment_topology: "local-dev",
    workflow_catalog: []
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
        ? window.STUDIO_RUNTIME_CONFIG.workflow_catalog.filter((entry) => entry.enabled !== false)
        : [];
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
        .filter((entry) => entry.category === "image" || (entry.category === "video" && (entry.required_inputs || []).length))
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
        .filter((entry) => entry.category === "image" || (entry.category === "video" && (entry.required_inputs || []).length))
        .forEach((entry) => {
            const inputTypes = entry.input_types || {};
            const schemaInputs = [...(entry.required_inputs || []), ...(entry.optional_inputs || [])];
            const imageInputs = schemaInputs.filter((name) =>
                ["image", "multi-image"].includes(inputTypes[name])
            );
            config[entry.id] = {
                uploads: (imageInputs.length ? imageInputs : (entry.frontend.inputs || [])).flatMap((inputId) => {
                    const isMulti = inputTypes[inputId] === "multi-image";
                    const count = isMulti ? entry.max_items[inputId] : 1;
                    const label = inputId
                        .split("_")
                        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
                        .join(" ");
                    return Array.from({length: count}, (_, index) => ({
                        id: isMulti ? `${inputId}.${index}` : inputId,
                        field: inputId,
                        label: `${label}${count > 1 ? ` ${index + 1}` : ''}${(entry.optional_inputs || []).includes(inputId) ? ' (optional)' : ''}`,
                        icon: inputId === "source" ? "user" : "image"
                    }));
                }),
                color: entry.frontend.color,
                requiredInputs: entry.required_inputs || [],
                optionalInputs: entry.optional_inputs || [],
                inputTypes,
                choices: entry.choices || {},
                units: entry.units || {},
                defaults: entry.defaults || {},
                actionLabel: entry.frontend.action_label || "Generate",
                outputType: entry.output_type || "image",
                supportedModes: entry.supported_modes || []
            };
        });
    return config;
};

window.buildStudioToolInfo = function buildStudioToolInfo() {
    const info = {};
    window.getStudioWorkflowCatalog()
        .filter((entry) => entry.category === "image" || (entry.category === "video" && (entry.required_inputs || []).length))
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
        console.warn("[RuntimeConfig] Runtime catalog unavailable:", error.message);
    }

    return window.STUDIO_RUNTIME_CONFIG;
})();

console.log("API Origin:", window.API_URL);
console.log("API Base URL:", window.API_BASE_URL);
console.log("Served by Flask:", _isServedByFlask);
