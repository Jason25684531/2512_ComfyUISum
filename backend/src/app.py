"""
Backend API for Studio Core
提供任务提交和状态查询的接口
"""
import os
import sys
import json
import uuid
import html
import logging
import threading
import time
import base64  # <--- 🟢 請補上這一行！
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, g, redirect
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import escape
from redis import Redis, RedisError
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

# ============================================
# 添加 shared 模組路徑並載入 .env
# ============================================
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.utils import load_env
from shared.security import (
    INTERNAL_SERVER_ERROR_MESSAGE,
    OPERATION_FAILED_MESSAGE,
    get_flask_debug_mode,
    sanitize_response_payload,
)
load_env()
from frontend_compat import resolve_legacy_redirect, resolve_root_document
from shared.runtime_services import (
    build_job_data,
    build_runtime_config_payload,
    build_runtime_diagnostics,
    resolve_workflow_request,
)
from shared.elements_data_validator import ElementsDataValidator
from shared.config_base import JOB_OBSERVABILITY_ENABLED
from shared.job_contracts import JobStatus, iso_utc
from shared.job_tracker import JobTracker
from shared.observability_runtime import job_repository, new_request_id
from admin_routes import admin_bp

# ============================================
# Configuration & Logging Setup
# ============================================
app = Flask(__name__)
app.register_blueprint(admin_bp)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_SIZE_MB', '200')) * 1024 * 1024

FLASK_DEBUG_MODE = get_flask_debug_mode()
DEFAULT_ALLOWED_CORS_ORIGINS = {
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:5000',
    'http://127.0.0.1:5000',
}


def _load_allowed_cors_origins():
    configured_origins = os.getenv('CORS_ALLOWED_ORIGINS', '').strip()
    if not configured_origins:
        return DEFAULT_ALLOWED_CORS_ORIGINS

    return {
        origin.strip()
        for origin in configured_origins.split(',')
        if origin.strip()
    }


ALLOWED_CORS_ORIGINS = _load_allowed_cors_origins()


def _get_request_origin():
    origin = request.headers.get('Origin')
    if origin and origin in ALLOWED_CORS_ORIGINS:
        return origin
    return None


def _apply_cors_headers(response):
    origin = _get_request_origin()
    if origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Vary'] = 'Origin'
    return response


def _sanitize_json_response(response):
    if not response.is_json:
        return response

    payload = response.get_json(silent=True)
    if payload is None:
        return response

    response.set_data(json.dumps(sanitize_response_payload(payload), ensure_ascii=False))
    return response

# ============================================
# ProxyFix: 修正 TWCC LB → Nginx 反向代理鏈的標頭
# 僅在 PROXY_FIX=true 時啟用，不影響本地 Windows 開發
# ============================================
if os.getenv('PROXY_FIX', 'false').lower() == 'true':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Local HTTP development must not mark auth cookies as Secure, otherwise
# browsers and test clients will store them but never send them back.
def _get_cookie_secure_setting() -> bool:
    configured = os.getenv('SESSION_COOKIE_SECURE')
    if configured is not None:
        return configured.strip().lower() == 'true'

    if FLASK_DEBUG_MODE:
        return False

    return os.getenv('PROXY_FIX', 'false').lower() == 'true'


COOKIE_SECURE = _get_cookie_secure_setting()


def _build_deployment_diagnostics(redis_status: str, mysql_status: str, worker_status: str) -> dict:
    return build_runtime_diagnostics(
        project_root=PROJECT_ROOT,
        redis_status=redis_status,
        mysql_status=mysql_status,
        worker_status=worker_status,
    )

# Session Cookie 配置 - 確保跨域請求能正確處理 cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 允許同站導航攜帶 cookie
app.config['SESSION_COOKIE_SECURE'] = COOKIE_SECURE
app.config['SESSION_COOKIE_HTTPONLY'] = True    # 防止 JS 讀取 cookie
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = COOKIE_SECURE

# ============================================
# 自訂日誌過濾器
# ============================================

class UserIdFilter(logging.Filter):
    """日誌過濾器，將 g.user_id 注入到日誌記錄中"""
    def filter(self, record):
        try:
            # 從 Flask 上下文中獲取 user_id，如果不存在則使用 'INIT'
            user_id = getattr(g, 'user_id', 'INIT')
        except (RuntimeError, AttributeError):
            # 在應用上下文外或沒有活躍請求時，使用預設值
            user_id = 'INIT'
        
        record.user_id = user_id
        return True

# ============================================

# 初始化 Rate Limiter (使用 Redis 作為儲存後端)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=None,  # 將在後續設置
    # default_limits=["100 per hour"],
    default_limits=["10000 per hour"],  # <-- 改成這樣，或者直接拿掉這行
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window"
)

# 設定 CORS - 允許所有來源的跨域請求
# 使用 supports_credentials=True 以支援會話 Cookie
CORS(app, 
    origins=sorted(ALLOWED_CORS_ORIGINS),
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=True)

# 手動處理 OPTIONS 預檢請求
@app.before_request
def before_request_handler():
    """
    在每個請求前處理：
    1. 提取客戶端 IP 地址
    2. 存儲到 Flask g 對象，供日誌使用
    """
    # 獲取客戶端 IP 地址（考慮代理）
    ip_address = request.headers.get('X-Forwarded-For')
    if ip_address:
        # 代理情況下，取第一個 IP
        ip_address = ip_address.split(',')[0].strip()
    else:
        ip_address = request.remote_addr or 'unknown'

    g.user_id = f"IP#{ip_address}"
    g.request_id = new_request_id(request.headers.get('X-Request-ID'))
    global _outbox_last_run
    if time.monotonic() - _outbox_last_run > 5:
        _outbox_last_run = time.monotonic()
        dispatch_pending_jobs()

    # 記錄請求開始
    logger.debug(f"📨 {request.method} {request.path} - IP: {ip_address}")

# 手動處理 OPTIONS 預檢請求
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        _apply_cors_headers(response)
        return response

@app.after_request
def after_request(response):
    response = _sanitize_json_response(response)
    response = _apply_cors_headers(response)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    if hasattr(g, 'request_id'):
        response.headers['X-Request-ID'] = g.request_id
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; media-src 'self' data: blob: https:; connect-src 'self' https: ws: wss:; font-src 'self' data:"
    )
    
    # 記錄請求完成 + Redis 隊列深度
    try:
        queue_depth = redis_client.llen(REDIS_QUEUE_NAME) if redis_client else 0
        logger.info(f"✓ {request.method} {request.path} - {response.status_code} | Queue: {queue_depth}")
    except Exception:
        logger.info(f"✓ {request.method} {request.path} - {response.status_code}")
    
    return response

# ==========================================
# Phase 8C: 使用新的結構化日誌系統
# ==========================================
from shared.utils import setup_logger

logger = setup_logger("backend", log_level=logging.INFO)
app.logger = logger

# 從 config 載入配置
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, JOB_QUEUE,
    PROJECT_ROOT
)
REDIS_QUEUE_NAME = JOB_QUEUE
WARMUP_STATUS_KEY = os.getenv('WARMUP_STATUS_KEY', 'worker:warmup:status')

# ============================================
# Redis Connection Setup
# ============================================
try:
    from shared.utils import get_redis_client
    redis_client = get_redis_client(decode_responses=True)
    logger.info(f"✓ Redis 连接成功: {REDIS_HOST}:{REDIS_PORT}")
    
    # 配置 Limiter 使用 Redis
    limiter.storage_uri = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/1"
    
except Exception as e:
    logger.exception("✗ Redis 连接失败")
    redis_client = None

# ============================================
# 音訊/影片上傳設定
# ============================================
ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov'}
ALLOWED_UPLOAD_EXTENSIONS = ALLOWED_AUDIO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS
UPLOAD_FOLDER = Path(__file__).parent.parent.parent / 'storage' / 'inputs'
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

_outbox_lock = threading.Lock()
_outbox_last_run = 0.0


def dispatch_pending_jobs():
    """Replay committed dispatch intents; duplicate delivery is stopped by worker CAS."""
    if not redis_client or not _outbox_lock.acquire(blocking=False):
        return
    try:
        repo, tracker = job_repository(), JobTracker(job_repository())
        for dispatch in repo.pending_dispatches(20):
            try:
                job = repo.get_job(dispatch['job_id']) or {}
                if job.get('status') == JobStatus.CREATED.value:
                    if not tracker.transition(dispatch['job_id'], JobStatus.CREATED, JobStatus.QUEUED):
                        continue
                elif job.get('status') != JobStatus.QUEUED.value:
                    repo.mark_dispatched(dispatch['job_id'], iso_utc())
                    continue
                tracker.event(dispatch['job_id'], 'job_queued', resulting_status='queued')
                redis_client.rpush(JOB_QUEUE, json.dumps(dispatch['payload'], ensure_ascii=False))
                repo.mark_dispatched(dispatch['job_id'], iso_utc())
            except Exception as exc:
                repo.mark_dispatched(dispatch['job_id'], iso_utc(), str(exc)[:500])
    finally:
        _outbox_lock.release()


# ============================================
# API Endpoints
# ============================================


@app.errorhandler(413)
def handle_upload_too_large(_error):
    max_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({'error': f'File too large. Maximum allowed size is {max_mb}MB'}), 413


# ============================================
# File Upload API
# ============================================

@app.route('/api/upload', methods=['POST'])
@limiter.limit("30 per minute")
def upload_audio():
    """
    POST /api/upload
    上傳音訊或影片檔案 (支援 .wav, .mp3, .mp4, .mov)

    Request: multipart/form-data, Key: 'file'

    Response:
    {
        "filename": "audio_550e8400-e29b.wav",
        "original_name": "林志玲.wav"
    }
    """
    try:
        # 1. 驗證檔案是否存在
        if 'file' not in request.files:
            logger.warning("上傳請求缺少 'file' 欄位")
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            logger.warning("上傳的檔案名稱為空")
            return jsonify({'error': 'No file selected'}), 400

        # 2. 驗證檔案類型
        original_filename = secure_filename(file.filename)
        file_ext = os.path.splitext(original_filename)[1].lower()

        if file_ext not in ALLOWED_UPLOAD_EXTENSIONS:
            logger.warning(f"不支援的檔案格式: {file_ext}")
            return jsonify({
                'error': f'Unsupported file type. Allowed: {", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}'
            }), 400

        # 3. 生成唯一檔名 (保留原副檔名)
        unique_id = str(uuid.uuid4())[:12]
        file_prefix = 'video' if file_ext in ALLOWED_VIDEO_EXTENSIONS else 'audio'
        new_filename = f"{file_prefix}_{unique_id}{file_ext}"
        
        # 4. 確保安全的檔名
        safe_filename = secure_filename(new_filename)
        
        # 5. 儲存檔案
        file_path = UPLOAD_FOLDER / safe_filename
        
        try:
            file.save(str(file_path))
            logger.info(f"✅ 音訊上傳成功: {safe_filename} (原始: {original_filename})")
        except PermissionError as e:
            logger.error(f"❌ 儲存檔案權限不足: {e}")
            return jsonify({'error': 'Permission denied when saving file'}), 500
        except FileNotFoundError as e:
            logger.error(f"❌ 儲存路徑不存在: {e}")
            return jsonify({'error': 'Upload directory not found'}), 500
        
        # 6. 回傳結果
        return jsonify({
            'filename': safe_filename,
            'original_name': html.escape(str(file.filename))
        }), 200
    
    except Exception as e:
        logger.error(f"✗ upload 接口異常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/generate', methods=['POST', 'OPTIONS'])
@limiter.limit("10 per minute")
def generate():
    """
    POST /api/generate
    接收生成请求并将任务推送到 Redis 队列
    
    ⭐ Phase 10: 實作嚴格事務響應 (Strict Transactional Response)
    流程: Start Transaction → Insert DB → Flush → Push Redis → Commit → Return 200
    
    Request Body:
    {
        "prompt": "a cyberpunk cat",
        "seed": 12345,
        "workflow": "sdxl"
    }
    
    Response:
    {
        "job_id": "uuid...",
        "status": "queued"
    }
    """
    session = None
    try:
        # 1. 验证请求数据
        data = request.get_json()
        if not data:
            logger.warning("请求缺少 JSON 数据")
            return jsonify({'error': 'Missing JSON data'}), 400
        
        prompt = data.get('prompt', '').strip()
        prompts = data.get('prompts', [])
        try:
            workflow_resolution = resolve_workflow_request(PROJECT_ROOT, data.get('workflow', 'text_to_image'))
        except KeyError:
            return jsonify({'error': 'Unsupported workflow'}), 400
        workflow = workflow_resolution.workflow_id
        if workflow_resolution.alias_hit:
            logger.info(
                "workflow alias normalized: requested=%s canonical=%s source=%s",
                workflow_resolution.requested_id,
                workflow_resolution.workflow_id,
                workflow_resolution.source,
            )
        
        # ===== 安全性驗證：Prompt 長度限制 =====
        if len(prompt) > 1000:
            logger.warning(f"Prompt 超過長度限制: {len(prompt)} > 1000")
            return jsonify({'error': 'Prompt exceeds maximum length of 1000 characters'}), 400
        
        # Veo3 Long Video: 驗證 prompts 列表
        if prompts:
            if not isinstance(prompts, list):
                return jsonify({'error': 'prompts must be a list'}), 400
            if len(prompts) > 10:  # 最多支持 10 個 segment
                return jsonify({'error': 'Too many prompts (max 10)'}), 400
            for p in prompts:
                if len(str(p)) > 1000:
                    return jsonify({'error': 'Individual prompt exceeds maximum length'}), 400
        
        # 只有 text_to_image 需要 prompt
        if workflow == 'text_to_image' and not prompt:
            logger.warning("text_to_image 的 prompt 参数为空")
            return jsonify({'error': 'prompt is required for text_to_image'}), 400

        # ltx_retake_v2v: 影片重生成，驗證影片、prompt 與起訖秒數
        retake_start_val = data.get('retake_start', 0)
        retake_end_val = data.get('retake_end', 0)
        video_filename = data.get('video', '')
        if workflow == 'ltx_retake_v2v':
            if not video_filename:
                return jsonify({'error': 'video is required for ltx_retake_v2v'}), 400
            video_path = UPLOAD_FOLDER / secure_filename(str(video_filename))
            if not video_path.exists():
                return jsonify({'error': 'uploaded video not found, please re-upload'}), 400
            if not prompt:
                return jsonify({'error': 'prompt is required for ltx_retake_v2v'}), 400
            try:
                retake_start_val = float(retake_start_val)
                retake_end_val = float(retake_end_val)
            except (TypeError, ValueError):
                return jsonify({'error': 'retake_start/retake_end must be numbers'}), 400
            if retake_start_val < 0 or retake_end_val <= retake_start_val:
                return jsonify({'error': 'retake_start must be >= 0 and less than retake_end'}), 400

        extra_params = {}
        if workflow == 'ltx_retake_v2v':
            extra_params = {'retake_start': retake_start_val, 'retake_end': retake_end_val}

        # ideogram4_regional_t2i: 區域提示詞文生圖，於信任邊界驗證 elements_data 與風格欄位
        if workflow == 'ideogram4_regional_t2i':
            if not prompt:
                return jsonify({'error': 'prompt is required for ideogram4_regional_t2i'}), 400
            try:
                canonical_elements_data = ElementsDataValidator.validate(data.get('elements_data') or '[]')
            except ValueError:
                return jsonify({'error': 'invalid elements_data'}), 400

            width_val = data.get('width', 1080)
            height_val = data.get('height', 1920)
            try:
                width_val = int(width_val)
                height_val = int(height_val)
            except (TypeError, ValueError):
                return jsonify({'error': 'width and height must be integers'}), 400
            if not (256 <= width_val <= 4096) or not (256 <= height_val <= 4096):
                return jsonify({'error': 'width and height must be between 256 and 4096'}), 400

            extra_params = {
                'elements_data': canonical_elements_data,
                'width': width_val,
                'height': height_val,
            }
            for field_name in ('background', 'style', 'aesthetics', 'lighting', 'medium', 'style_palette_data'):
                field_value = data.get(field_name)
                if field_value is None:
                    continue
                if not isinstance(field_value, str) or len(field_value) > 2000:
                    return jsonify({'error': f'{field_name} must be a string up to 2000 characters'}), 400
                extra_params[field_name] = field_value

        if workflow == 'multi_angle':
            input_filename = (data.get('images') or {}).get('input')
            if not input_filename:
                return jsonify({'error': 'input image is required for multi_angle'}), 400

            for field_name, minimum, maximum, integer_only in (
                ('horizontal_angle', 0, 360, True),
                ('vertical_angle', -30, 60, True),
                ('zoom', 0.0, 10.0, False),
            ):
                if field_name not in data:
                    continue
                raw_value = data[field_name]
                if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                    return jsonify({'error': f'{field_name} must be a number within range'}), 400
                if integer_only and not isinstance(raw_value, int):
                    return jsonify({'error': f'{field_name} must be a number within range'}), 400
                value = raw_value if integer_only else float(raw_value)
                if value < minimum or value > maximum:
                    return jsonify({'error': f'{field_name} must be within range'}), 400
                extra_params[field_name] = value

        if workflow in {'ltx_i2v', 'ltx_flf'}:
            required_images = ('input',) if workflow == 'ltx_i2v' else ('first_frame', 'last_frame')
            images = data.get('images') or {}
            for field_name in required_images:
                if not images.get(field_name):
                    return jsonify({'error': f'{field_name} image is required'}), 400

            for field_name, minimum, maximum in (
                ('video_width', 512, 1920),
                ('video_height', 512, 1920),
                ('video_duration', 1, 10),
            ):
                if field_name not in data:
                    continue
                raw_value = data[field_name]
                if isinstance(raw_value, bool) or isinstance(raw_value, float):
                    return jsonify({'error': f'{field_name} must be an integer between {minimum} and {maximum}'}), 400
                try:
                    value = int(raw_value)
                except (TypeError, ValueError):
                    return jsonify({'error': f'{field_name} must be an integer between {minimum} and {maximum}'}), 400
                if not minimum <= value <= maximum:
                    return jsonify({'error': f'{field_name} must be between {minimum} and {maximum}'}), 400
                extra_params[field_name] = value
        # =====================================================
        # 這裡會檢查 data['audio'] 是否為 Base64 字串
        # 如果是，就轉存成檔案，並把 data['audio'] 替換成檔名
        # 這樣後面的 job_data 就會拿到檔名，而不是超長的字串
        # =====================================================
        audio_val = data.get('audio', '')
        if audio_val and isinstance(audio_val, str) and audio_val.startswith('data:audio'):
            try:
                # 1. 解析 Base64 Header
                header, encoded = audio_val.split(",", 1)
                
                # 2. 判斷副檔名
                file_ext = '.wav'  # 預設
                if 'audio/mpeg' in header:
                    file_ext = '.mp3'
                elif 'audio/wav' in header:
                    file_ext = '.wav'
                
                # 3. 生成音訊檔專用的唯一檔名 (這不會影響下面的 job_id)
                audio_filename = f"audio_{uuid.uuid4().hex[:12]}{file_ext}"
                save_path = UPLOAD_FOLDER / audio_filename
                
                # 4. 存檔
                with open(save_path, "wb") as f:
                    f.write(base64.b64decode(encoded))
                
                logger.info(f"✓ Base64 音訊已自動轉存: {audio_filename}")
                
                # 5. 【關鍵】將變數替換為檔名，這樣寫入 DB 時就不會過長了
                data['audio'] = audio_filename 
                
            except Exception as e:
                logger.error(f"❌ Base64 音訊解碼失敗: {e}")
                return jsonify({'error': 'Invalid base64 audio data'}), 400
        # 2. 生成唯一的 job_id
        job_id = str(uuid.uuid4())
        user_label_for_job = getattr(g, 'user_id', 'anonymous') or 'anonymous'

        # 3. 构造任务数据 (包含所有前端傳來的參數)
        job_data = {
            'job_id': job_id,
            'request_id': g.request_id,
            'schema_version': 2,
            'prompt': prompt,
            'prompts': prompts,  # Veo3 Long Video: 新增 prompts 列表
            'seed': data.get('seed', -1),  # -1 表示随机
            'workflow': workflow,
            'workflow_requested': workflow_resolution.requested_id,
            'workflow_resolution': workflow_resolution.source,
            'user_id': None,
            'user_label': user_label_for_job,
            'model': data.get('model', 'turbo_fp8'),
            'aspect_ratio': data.get('aspect_ratio', '1:1'),
            'batch_size': data.get('batch_size', 1),
            'images': data.get('images', {}),  # Base64 圖片字典
            'audio': data.get('audio', ''),  # 音訊檔名 (virtual_human 工作流使用)
            'video': video_filename,  # 影片檔名 (ltx_retake_v2v 工作流使用)
            'retake_start': retake_start_val,
            'retake_end': retake_end_val,
            'extra_params': extra_params,
            'created_at': iso_utc(),
            'submitted_at': iso_utc(),
            'workflow_version': workflow_resolution.entry.version,
            'workflow_category': workflow_resolution.entry.category,
        }
        tracker = None
        if JOB_OBSERVABILITY_ENABLED:
            try:
                tracker = JobTracker(job_repository())
                tracker.create(
                    job_id,
                    g.request_id,
                    workflow_id=workflow,
                    workflow_version=workflow_resolution.entry.version,
                    workflow_category=workflow_resolution.entry.category,
                    model_name=str(job_data['model']),
                    dispatch_payload=job_data,
                )
                tracker.event(job_id, 'validation_passed', resulting_status='created')
            except Exception:
                logger.exception('job observability create failed', extra={'job_id': job_id, 'request_id': g.request_id})
                return jsonify({'error': 'Job persistence unavailable'}), 503
        
        # 4. 檢查 Redis 可用性
        if redis_client is None:
            logger.error("Redis 客户端未初始化")
            if tracker:
                tracker.fail(job_id, JobStatus.CREATED, stage='redis_enqueue', code='QUEUE_WRITE_ERROR', message='Queue unavailable')
            return jsonify({'error': 'Redis service unavailable'}), 503

        trace_extra = {
            'job_id': job_id,
            'workflow': workflow,
            'user_label': user_label_for_job,
        }

        try:
            # 5. 推送到 Redis 佇列
            if tracker and not tracker.transition(job_id, JobStatus.CREATED, JobStatus.QUEUED):
                raise RedisError('durable job enqueue transition failed')
            if tracker:
                tracker.event(job_id, 'job_queued', resulting_status='queued')
            redis_client.rpush(REDIS_QUEUE_NAME, json.dumps(job_data))
            if tracker:
                tracker.repository.mark_dispatched(job_id, iso_utc())
            logger.info("job enqueued to redis", extra=trace_extra)
            logger.info(f"✓ Job {job_id} 已推送至 Redis")

            # 6. 初始化 Redis 狀態 Hash
            status_key = f"job:status:{job_id}"
            redis_client.hset(status_key, mapping={
                'job_id': job_id,
                'status': 'queued',
                'progress': 0,
                'image_url': '',
                'error': '',
                'updated_at': datetime.now().isoformat()
            })
            redis_client.expire(status_key, 86400)  # 24小时过期
            logger.info(f"✓ Job {job_id} Redis 狀態已初始化")

            # 7. 返回成功响应
            return jsonify({
                'job_id': job_id,
                'status': 'queued',
                'message': '任務已成功提交'
            }), 202 if workflow in {'ltx_i2v', 'ltx_flf'} else 200

        except RedisError:
            if tracker:
                current = (tracker.repository.get_job(job_id) or {}).get('status')
                tracker.fail(job_id, JobStatus(current) if current in {JobStatus.CREATED.value, JobStatus.QUEUED.value} else JobStatus.CREATED,
                             stage='redis_enqueue', code='QUEUE_WRITE_ERROR', message='Queue write failed')
            logger.exception("❌ Redis Push 失敗")
            return jsonify({
                'error': OPERATION_FAILED_MESSAGE
            }), 500

    except Exception as e:
        logger.exception("✗ generate 接口异常")
        return jsonify({'error': INTERNAL_SERVER_ERROR_MESSAGE}), 500


@app.route('/api/status/<job_id>', methods=['GET'])
@limiter.limit("2 per second")  # 每秒 2 次 = 每分鐘 120 次（寬鬆限制，適合輪詢）
def status(job_id):
    """
    GET /api/status/<job_id>
    查询任务状态

    流程: Redis (活動任務) → 404
    (無歷史資料庫回退，Job 狀態僅存活於 Redis TTL 期間)

    Response:
    {
        "job_id": "...",
        "status": "processing",
        "progress": 50,
        "image_url": null,
        "error": ""
    }
    """
    try:
        # 1. 優先從 Redis 讀取狀態 (活動任務)
        if redis_client:
            status_key = f"job:status:{job_id}"
            job_status = redis_client.hgetall(status_key)
            
            if job_status:
                current_status = job_status.get('status', 'unknown')

                # 返回 Redis 中的狀態
                return jsonify({
                    'job_id': str(escape(job_status.get('job_id', job_id))),
                    'status': str(escape(current_status)),
                    'progress': int(job_status.get('progress', 0)),
                    'image_url': str(escape(job_status.get('image_url', ''))),
                    'error': str(escape(job_status.get('error', ''))),
                    'source': 'redis'  # 標記數據來源
                }), 200

        # Redis TTL is ephemeral; MySQL is the durable status fallback.
        job = job_repository().get_job(job_id)
        if job:
            legacy = {'created': 'queued', 'queued': 'queued', 'running': 'processing',
                      'completed': 'finished', 'failed': 'failed', 'cancelled': 'cancelled'}
            return jsonify({'job_id': job_id, 'status': legacy.get(job['status'], 'unknown'),
                            'progress': job.get('progress') or 0, 'image_url': '',
                            'error': job.get('sanitized_error_message') or '', 'source': 'mysql'}), 200
        return jsonify({'error': 'Job not found', 'job_id': job_id}), 404
    
    except Exception as e:
        logger.error(f"✗ status 接口异常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    """
    POST /api/cancel/<job_id>
    取消正在執行的任務
    
    Response:
    {
        "success": true,
        "message": "Task cancelled"
    }
    """
    try:
        job = job_repository().get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        current = job['status']
        if current in ('completed', 'failed', 'cancelled'):
            return jsonify({'success': False, 'message': 'Job cannot be cancelled in its current state'}), 400
        tracker = JobTracker(job_repository())
        state = JobStatus.QUEUED if current == 'queued' else JobStatus.RUNNING
        if not tracker.request_cancel(job_id, state):
            return jsonify({'success': False, 'message': 'Job state changed'}), 409
        if redis_client is not None:
            key = f"job:status:{job_id}"
            if state is JobStatus.QUEUED:
                redis_client.hset(key, mapping={'status': 'cancelled', 'canonical_status': 'cancelled', 'error': 'Task cancelled by user'})
            else:
                redis_client.hset(key, 'cancel_requested', 'true')
        return jsonify({'success': True, 'message': 'Task cancelled' if state is JobStatus.QUEUED else 'Cancellation requested'}), (200 if state is JobStatus.QUEUED else 202)

        if redis_client is None:
            logger.error("Redis 客户端未初始化")
            return jsonify({'error': 'Redis service unavailable'}), 503
        
        # 檢查任務是否存在
        status_key = f"job:status:{job_id}"
        job_status = redis_client.hgetall(status_key)
        
        if not job_status:
            logger.warning(f"任務不存在: job_id={job_id}")
            return jsonify({'error': 'Job not found'}), 404
        
        current_status = job_status.get('status', 'unknown')
        
        # 如果任務已經完成或失敗，無法取消
        if current_status in ['finished', 'failed', 'cancelled']:
            return jsonify({
                'success': False,
                'message': 'Job cannot be cancelled in its current state'
            }), 400
        
        # 將狀態設置為 cancelled
        redis_client.hset(status_key, 'status', 'cancelled')
        redis_client.hset(status_key, 'error', 'Task cancelled by user')
        
        logger.info(f"✓ 任務已標記為取消: job_id={job_id}")
        
        return jsonify({
            'success': True,
            'message': 'Task cancelled'
        }), 200
    
    except Exception as e:
        logger.error(f"✗ cancel 接口异常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/metrics', methods=['GET'])
@limiter.limit("2 per second")  # 每秒 2 次 = 每分鐘 120 次（監控儀表板專用）
def metrics():
    """
    GET /api/metrics
    系統監控指標端點（Phase 6 - 高頻輪詢專用）
    
    Response:
    {
        "queue_length": 5,          // Redis 佇列中等待的任務數量
        "worker_status": "online",  // Worker 狀態 (online/offline)
        "active_jobs": 2            // 當前正在處理的任務數量
    }
    """
    try:
        if redis_client is None:
            logger.error("Redis 客户端未初始化")
            return jsonify({'error': 'Redis service unavailable'}), 503
        
        # 1. 獲取佇列長度
        queue_length = redis_client.llen(REDIS_QUEUE_NAME)
        
        # 2. 檢查 Worker 心跳狀態
        worker_heartbeat = redis_client.get('worker:heartbeat')
        worker_status = 'online' if worker_heartbeat else 'offline'
        warmup_snapshot = _get_worker_warmup_snapshot()
        deployment_diagnostics = _build_deployment_diagnostics('healthy', 'n/a', worker_status)
        
        # 3. 統計當前正在處理的任務（status='processing'）
        active_jobs = 0
        # 掃描所有 job:status:* 鍵
        status_keys = redis_client.keys('job:status:*')
        for key in status_keys:
            job_status = redis_client.hget(key, 'status')
            if job_status == 'processing':
                active_jobs += 1
        
        logger.info(f"📊 Metrics: queue={queue_length}, worker={worker_status}, active={active_jobs}")
        
        return jsonify({
            'queue_length': queue_length,
            'worker_status': worker_status,
            'active_jobs': active_jobs,
            **deployment_diagnostics,
            **warmup_snapshot,
        }), 200
    
    except Exception as e:
        logger.error(f"✗ metrics 接口异常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health():
    """健康检查接口 - 檢查 Redis 狀態"""
    redis_status = 'healthy' if redis_client and redis_client.ping() else 'unavailable'
    worker_status = 'offline'
    warnings = []
    warmup_snapshot = _get_worker_warmup_snapshot()
    if redis_client:
        try:
            worker_status = 'online' if redis_client.get('worker:heartbeat') else 'offline'
        except Exception as exc:
            logger.warning(f"讀取 Worker 心跳失敗: {exc.__class__.__name__}")

    try:
        with job_repository().transaction() as cursor:
            cursor.execute('SELECT 1')
        mysql_status = 'healthy'
    except Exception:
        mysql_status = 'unavailable'

    overall_status = 'ok' if redis_status == 'healthy' and mysql_status == 'healthy' else 'degraded'

    if worker_status == 'offline':
        warnings.append('Worker heartbeat unavailable')
    if warmup_snapshot['warmup_status'] == 'running':
        warnings.append('GPU warmup in progress')
    if warmup_snapshot['warmup_status'] == 'failed' and warmup_snapshot['warmup_last_error']:
        warnings.append(warmup_snapshot['warmup_last_error'])
    deployment_diagnostics = _build_deployment_diagnostics(redis_status, mysql_status, worker_status)
    
    return jsonify({
        'status': overall_status,
        'redis': redis_status,
        'mysql': mysql_status,
        'worker': worker_status,
        **deployment_diagnostics,
        **warmup_snapshot,
        'warnings': warnings,
    }), 200


@app.route('/api/runtime-config', methods=['GET'])
def runtime_config():
    try:
        return jsonify(build_runtime_config_payload(PROJECT_ROOT)), 200
    except Exception as exc:
        logger.error(f"runtime-config failed: {exc.__class__.__name__}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/models', methods=['GET'])
def get_models():
    """
    GET /api/models
    掃描 ComfyUI 模型目錄，回傳可用模型列表
    
    Response:
    {
        "models": ["model1.safetensors", "model2.ckpt"],
        "unet_models": ["unet1.safetensors"]
    }
    """
    from config import COMFYUI_CHECKPOINTS_DIR, COMFYUI_UNET_DIR
    
    models = []
    unet_models = []
    
    # 掃描 Checkpoints 目錄
    try:
        if COMFYUI_CHECKPOINTS_DIR.exists():
            for file_path in COMFYUI_CHECKPOINTS_DIR.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in ['.safetensors', '.ckpt']:
                    # 使用相對路徑（相對於 checkpoints 目錄）
                    rel_path = file_path.relative_to(COMFYUI_CHECKPOINTS_DIR)
                    models.append(str(rel_path))
            logger.info(f"✓ 找到 {len(models)} 個 Checkpoint 模型")
        else:
            logger.warning(f"Checkpoints 目錄不存在: {COMFYUI_CHECKPOINTS_DIR}")
    except Exception as e:
        logger.error(f"掃描 Checkpoints 失敗: {e}")
    
    # 掃描 UNET 目錄
    try:
        if COMFYUI_UNET_DIR.exists():
            for file_path in COMFYUI_UNET_DIR.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in ['.safetensors', '.ckpt', '.pt']:
                    rel_path = file_path.relative_to(COMFYUI_UNET_DIR)
                    unet_models.append(str(rel_path))
            logger.info(f"✓ 找到 {len(unet_models)} 個 UNET 模型")
        else:
            logger.warning(f"UNET 目錄不存在: {COMFYUI_UNET_DIR}")
    except Exception as e:
        logger.error(f"掃描 UNET 失敗: {e}")
    
    # 如果沒有找到任何模型，返回預設列表
    if not models and not unet_models:
        logger.warning("未找到任何模型，返回預設列表")
        models = ["default_model.safetensors"]
        unet_models = ["z-image/z-image-turbo-fp8-e4m3fn.safetensors"]
    
    return jsonify({
        'models': sorted(models),
        'unet_models': sorted(unet_models)
    }), 200


# ============================================
# Statistics & Monitoring Functions (Phase 3)
# ============================================

def _parse_redis_bool(value) -> bool:
    return str(value).strip().lower() == 'true'


def _parse_redis_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_worker_warmup_snapshot() -> dict:
    snapshot = {
        'warmup_status': 'unknown',
        'warmup_profile': '',
        'warmup_last_error': '',
        'warmup_mode': '',
        'warmup_started_at': '',
        'warmup_completed_at': '',
        'warmup_updated_at': '',
        'warmup_enabled': False,
        'warmup_terminal': False,
        'warmup_timeout_seconds': 0,
    }

    if not redis_client:
        return snapshot

    try:
        raw_snapshot = redis_client.hgetall(WARMUP_STATUS_KEY) or {}
    except Exception as exc:
        logger.warning(f"讀取暖機狀態失敗: {exc.__class__.__name__}")
        snapshot['warmup_last_error'] = 'Warmup status unavailable'
        return snapshot

    if not raw_snapshot:
        return snapshot

    snapshot.update({
        'warmup_status': html.escape(str(raw_snapshot.get('status', 'unknown'))),
        'warmup_profile': html.escape(str(raw_snapshot.get('profile', ''))),
        'warmup_last_error': html.escape(str(raw_snapshot.get('last_error', ''))),
        'warmup_mode': html.escape(str(raw_snapshot.get('mode', ''))),
        'warmup_started_at': html.escape(str(raw_snapshot.get('started_at', ''))),
        'warmup_completed_at': html.escape(str(raw_snapshot.get('completed_at', ''))),
        'warmup_updated_at': html.escape(str(raw_snapshot.get('updated_at', ''))),
        'warmup_enabled': _parse_redis_bool(raw_snapshot.get('enabled', 'false')),
        'warmup_terminal': _parse_redis_bool(raw_snapshot.get('terminal', 'false')),
        'warmup_timeout_seconds': _parse_redis_int(raw_snapshot.get('timeout_seconds', 0)),
    })
    return snapshot

def get_redis_stats() -> dict:
    """
    獲取 Redis 統計信息
    
    Returns:
        dict: 包含 queue_length, memory_usage, keys_count 等信息
    """
    stats = {
        'queue_length': 0,
        'memory_mb': 0,
        'total_keys': 0,
        'worker_online': False,
        'warmup_status': 'unknown',
    }
    
    if not redis_client:
        return stats
    
    try:
        # 隊列長度
        stats['queue_length'] = redis_client.llen(REDIS_QUEUE_NAME) or 0
        
        # Redis 記憶體使用情況
        info = redis_client.info('memory')
        stats['memory_mb'] = round(info.get('used_memory', 0) / (1024 * 1024), 2)
        
        # 鍵總數
        keyspace = redis_client.info('keyspace')
        db0 = keyspace.get('db0', {})
        stats['total_keys'] = db0.get('keys', 0)
        
        # Worker 線上狀態
        stats['worker_online'] = bool(redis_client.get('worker:heartbeat'))
        stats['warmup_status'] = _get_worker_warmup_snapshot()['warmup_status']
    except Exception as e:
        logger.warning(f"獲取 Redis 統計資訊失敗: {e}")
    
    return stats

def get_task_stats() -> dict:
    """
    獲取任務統計信息
    
    Returns:
        dict: 包含 total_tasks, active_jobs, finished, failed 等信息
    """
    stats = {
        'total_jobs': 0,
        'queued_jobs': 0,
        'processing_jobs': 0,
        'finished_jobs': 0,
        'failed_jobs': 0
    }
    
    if not redis_client:
        return stats
    
    try:
        # 掃描所有 job:status:* 鍵
        all_keys = redis_client.keys('job:status:*')
        stats['total_jobs'] = len(all_keys)
        
        # 按狀態統計
        for key in all_keys:
            status_info = redis_client.hgetall(key)
            status = status_info.get('status', 'unknown')
            
            if status == 'queued':
                stats['queued_jobs'] += 1
            elif status == 'processing':
                stats['processing_jobs'] += 1
            elif status == 'finished':
                stats['finished_jobs'] += 1
            elif status == 'failed':
                stats['failed_jobs'] += 1
    except Exception as e:
        logger.warning(f"獲取任務統計資訊失敗: {e}")
    
    return stats

# Phase 8C: Rich 監控面板已移除，改用結構化日誌系統
# 如需系統狀態，請查看 /api/metrics 端點或檢查 JSON 日誌檔案

# ============================================
# Static File Serving (for generated images/videos)
# ============================================
@app.route('/outputs/<path:filename>', methods=['GET'])
def serve_output(filename):
    """
    GET /outputs/<filename>
    Serve generated images/videos from storage/outputs directory
    Current target is local filesystem output serving only.
    支援 .png, .jpg, .mp4 等格式
    防止路徑穿越攻擊
    """
    import mimetypes
    from flask import abort

    # 強制清洗檔名，截斷路徑穿越與 Open Redirect 的污點
    safe_filename = secure_filename(filename)
    if not safe_filename:
        logger.warning(f"⚠️ 不安全的檔名: {filename}")
        return abort(400)

    # Get the absolute path to storage/outputs
    outputs_dir = os.getenv("STORAGE_OUTPUT_DIR")
    if not outputs_dir:
        outputs_dir = os.path.join(app.root_path, "..", "storage", "outputs")
    outputs_dir = os.path.abspath(outputs_dir)
    
    # ===== 安全性：防止路徑穿越攻擊 =====
    # 確保請求的檔案路徑嚴格位於 outputs_dir 內
    file_path = os.path.abspath(os.path.join(outputs_dir, safe_filename))
    if not file_path.startswith(outputs_dir):
        logger.warning(f"⚠️ 路徑穿越攻擊嘗試: {safe_filename}")
        return abort(403)  # Forbidden
    
    logger.info(f"📁 Serving file: {safe_filename} from {outputs_dir}")
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在: {file_path}")
        return abort(404)
    
    # 確保正確的 MIME Type (特別是影片檔案)
    mimetype, _ = mimetypes.guess_type(file_path)
    if mimetype is None:
        # 根據副檔名手動設定
        ext = os.path.splitext(safe_filename)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        mimetype = mime_map.get(ext, 'application/octet-stream')
    
    logger.info(f"📹 MIME Type: {mimetype}")
    return send_from_directory(outputs_dir, safe_filename, mimetype=mimetype)

# ============================================
# Application Entry Point
# ============================================

# Serve frontend static files
@app.route('/')
def serve_index():
    """
    單使用者模式：直接提供 dashboard.html（無登入閘門）
    """
    try:
        frontend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend')
        frontend_dir = os.path.abspath(frontend_dir)
        target_document = resolve_root_document(Path(frontend_dir))
        target_path = os.path.join(frontend_dir, target_document)
        if os.path.exists(target_path):
            return send_from_directory(frontend_dir, target_document)

        logger.error(f"frontend document not found at {target_path}")
        return jsonify({"error": "Frontend not found"}), 404

    except Exception as e:
        logger.exception("Error serving page")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/<path:path>')
def serve_static(path):
    """提供前端靜態文件（CSS, JS, 圖片等）"""
    # 這些路徑已經有專門的路由處理，跳過
    # 注意: 不要 raise NotFound()，而是直接 pass through
    if path.startswith('api/') or path.startswith('health') or path.startswith('outputs/'):
        # 返回 404，讓其他路由接管
        return jsonify({"error": "Not found"}), 404
    
    try:
        frontend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend')
        frontend_dir = os.path.abspath(frontend_dir)
        redirect_target = resolve_legacy_redirect(path)
        if redirect_target:
            return redirect(redirect_target, code=302)

        if path == 'favicon.ico':
            favicon_path = os.path.join(frontend_dir, 'favicon.ico')
            logo_dir = os.path.join(frontend_dir, 'image')
            logo_path = os.path.join(logo_dir, 'LOGO.png')

            if os.path.exists(favicon_path) and os.path.isfile(favicon_path):
                return send_from_directory(frontend_dir, 'favicon.ico')

            if os.path.exists(logo_path) and os.path.isfile(logo_path):
                return send_from_directory(logo_dir, 'LOGO.png', mimetype='image/png')

            return '', 204

        file_path = os.path.join(frontend_dir, path)
        if not os.path.abspath(file_path).startswith(frontend_dir + os.sep):
            logger.warning("Rejected invalid frontend path request")
            return jsonify({"error": "Forbidden"}), 403
        file_path = os.path.abspath(file_path)
        
        logger.info(f"Serving static file from {frontend_dir}")
        logger.info(f"File exists: {os.path.exists(file_path)}")
        
        # 嘗試返回靜態文件
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(frontend_dir, path)
        else:
            # 文件不存在，返回 dashboard.html（單使用者模式首頁，支持 SPA 路由）
            logger.warning(f"File not found: {path}, serving dashboard.html instead")
            return send_from_directory(frontend_dir, 'dashboard.html')
            
    except Exception as e:
        logger.exception("Error serving static file")
        return jsonify({"error": "Internal server error"}), 500

# ==========================================
# 啟動 Flask 應用
# ==========================================
if __name__ == '__main__':
    import sys
    
    logger.info("🚀 Backend API 啟動中...")
    logger.info("📁 同時提供前端靜態文件服務")
    logger.info("✓ 結構化日誌系統已啟動（雙通道輸出）")
    
    is_windows = sys.platform.startswith('win')
    is_debug = FLASK_DEBUG_MODE
    
    try:
        if is_windows:
            # Windows: 禁用 reloader 避免進程退出問題
            app.run(
                host='0.0.0.0', 
                port=5000, 
                debug=is_debug, 
                use_reloader=False,
                threaded=True
            )
        else:
            # Linux/Mac: 正常使用 reloader
            app.run(host='0.0.0.0', port=5000, debug=is_debug)
    except KeyboardInterrupt:
        logger.info("\n⏹️ 正在關閉 Backend...")
        logger.info("✓ Backend 已優雅關閉")
        sys.exit(0)
