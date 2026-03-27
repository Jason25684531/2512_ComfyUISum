// Auto-generated config - DO NOT EDIT
const _API_BASE_LOCAL = 'http://localhost:5000';

// 雲端 / 反向代理環境一律走同源相對路徑，本機非 5000 port 開發才回退到 localhost API
const _isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const _currentPort = window.location.port;

// 如果當前頁面已經是從 Flask (port 5000) 提供，使用相對路徑以確保 cookie 正確傳遞
const _isServedByFlask = _isLocalhost && (_currentPort === '5000' || _currentPort === '');

// 如果是透過 Nginx（port 80/443）提供，使用相對路徑（由 Nginx 反向代理到 Flask）
const _isServedByProxy = !_isLocalhost;

// 本機直接開 HTML 或 Live Server 時回退到 localhost:5000，其餘情境都使用相對路徑
const _apiBase = (_isServedByFlask || _isServedByProxy) ? '' : _API_BASE_LOCAL;

// Export for use in other scripts (login.html, profile.html, etc.)
window.API_URL = _apiBase;

console.log('API Base URL:', _apiBase || '(relative path)');
console.log('Served by Flask:', _isServedByFlask);
console.log('Served by Nginx/LB:', _isServedByProxy);
