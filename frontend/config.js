// Auto-generated config - DO NOT EDIT
const API_BASE_NGROK = 'https://0ef32562dd8a.ngrok-free.app';
const API_BASE_LOCAL = 'http://localhost:5000';

// Logic: Use Local API if on localhost, otherwise use Ngrok
const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = (isLocalhost || !API_BASE_NGROK) ? API_BASE_LOCAL : API_BASE_NGROK;

console.log('API Base URL:', API_BASE);
