// Ngrok URL - 可由 update_ngrok_config.ps1 自動更新
const API_BASE_NGROK = 'https://6cbe14b0dbb5.ngrok-free.app';

// 本地開發 URL
const API_BASE_LOCAL = 'http://localhost:5000';

// 自動偵測環境：如果是 localhost 使用本地 URL，否則使用 Ngrok URL
const isLocalhost = window.location.hostname === 'localhost' || 
                    window.location.hostname === '127.0.0.1' || 
                    window.location.hostname === '';

// 計算最終的 API URL
const API_BASE = isLocalhost ? API_BASE_LOCAL : API_BASE_NGROK;

// 同時賦值到全局變數 window.API_BASE（向後兼容）
window.API_BASE = API_BASE;

// 開發調試信息
console.log('🌍 環境偵測:', isLocalhost ? '本地開發' : '遠端 Ngrok');
console.log('🔗 API_BASE:', API_BASE);
