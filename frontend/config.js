// Auto-generated config - DO NOT EDIT
const _API_BASE_NGROK = 'https://0ef32562dd8a.ngrok-free.app';
const _API_BASE_LOCAL = 'http://localhost:5000';

// Logic: Use relative path for same-origin requests, otherwise use full URL
const _isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const _currentPort = window.location.port;

// 如果當前頁面已經是從 Flask (port 5000) 提供，使用相對路徑以確保 cookie 正確傳遞
const _isServedByFlask = _isLocalhost && (_currentPort === '5000' || _currentPort === '');

// 使用相對路徑 '' 當從 Flask 提供時，否則使用完整 URL
const _apiBase = _isServedByFlask ? '' : (_isLocalhost ? _API_BASE_LOCAL : _API_BASE_NGROK);

// Export for use in other scripts (login.html, profile.html, etc.)
window.API_URL = _apiBase;

console.log('API Base URL:', _apiBase || '(relative path)');
console.log('Served by Flask:', _isServedByFlask);
