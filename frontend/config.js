// Auto-generated config - DO NOT EDIT
const _API_ORIGIN_LOCAL = 'http://localhost:5000';

const _isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const _isFileProtocol = window.location.protocol === 'file:';
const _currentPort = window.location.port;

// 雲端部署與同源開發都走目前頁面的 origin，只有本機直接開 HTML / Live Server 才回退到本地 API。
const _isServedByFlask = _isLocalhost && (_currentPort === '5000' || _currentPort === '');
const _isServedByProxy = !_isLocalhost && !_isFileProtocol;
const _apiOrigin = (_isServedByFlask || _isServedByProxy) ? window.location.origin : _API_ORIGIN_LOCAL;

window.API_URL = _apiOrigin;
window.API_BASE_URL = `${_apiOrigin}/api`;

console.log('API Origin:', _apiOrigin);
console.log('API Base URL:', window.API_BASE_URL);
console.log('Served by Flask:', _isServedByFlask);
console.log('Served by Nginx/LB:', _isServedByProxy);
