// ============================================
// StudioCore Frontend - Configuration
// 環境自動偵測：K8s (Nginx) / Local Flask / Ngrok
// ============================================

(function() {
    'use strict';

    // --- 環境常數 ---
    const NGROK_URL = 'https://0ef32562dd8a.ngrok-free.app';
    const LOCAL_FLASK_URL = 'http://localhost:5000';

    // --- 環境偵測 ---
    const hostname = window.location.hostname;
    const port = window.location.port;
    const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1';
    const isServedByFlask = isLocalhost && (port === '5000' || port === '');
    const isServedByNginx = !isLocalhost || port === '80' || port === '';
    const isK8sEnv = hostname.endsWith('.local') || hostname.endsWith('.svc.cluster.local');

    // --- API 基礎路徑決策 ---
    // 優先級：K8s/Nginx 環境 > Flask 同源 > 本地開發 > Ngrok
    let apiBase;
    if (isK8sEnv || (isServedByNginx && !isLocalhost)) {
        // K8s 環境或 Nginx 代理：使用相對路徑，由 Nginx reverse proxy 處理
        apiBase = '';
    } else if (isServedByFlask) {
        // 直接從 Flask 提供：使用相對路徑確保 cookie 正確
        apiBase = '';
    } else if (isLocalhost) {
        // 本地開發（非 Flask 端口，如 Live Server）
        apiBase = LOCAL_FLASK_URL;
    } else {
        // 外部存取（Ngrok 等）
        apiBase = NGROK_URL;
    }

    // --- 匯出全域變數 ---
    window.API_URL = apiBase;

    // --- 偵錯日誌 ---
    const env = isK8sEnv ? 'K8s' : (isServedByFlask ? 'Flask' : (isLocalhost ? 'Local Dev' : 'External'));
    console.log(`[Config] Environment: ${env}`);
    console.log(`[Config] API Base URL: ${apiBase || '(relative path)'}`);
})();
