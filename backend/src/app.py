"""
Backend API for Studio Core
提供任务提交和状态查询的接口
"""
import os
import json
import uuid
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis, RedisError
from werkzeug.utils import secure_filename

# ============================================
# 載入 .env 環境變數
# ============================================
def load_env():
    """自動載入專案根目錄的 .env 檔案"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"✓ 已載入 .env 檔案: {env_path}")

load_env()

# ============================================
# Configuration & Logging Setup
# ============================================
app = Flask(__name__)
CORS(app)

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
CORS(app, 
     origins=["*"],
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=False)

# 手動處理 OPTIONS 預檢請求
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        return response

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    
    # 記錄請求日誌
    logger.info(f"{request.method} {request.path} - {response.status_code}")
    
    return response

# 配置日志记录器 (使用 RotatingFileHandler)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 確保 logs 目錄存在
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'backend.log')

# 配置 RotatingFileHandler (5MB, 保留 3 份)
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# 配置控制台輸出
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

# 配置 root logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 同時配置 Flask app logger
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.addHandler(console_handler)

# 從 config 載入配置
from config import (
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, JOB_QUEUE,
    STORAGE_OUTPUT_DIR
)
REDIS_QUEUE_NAME = JOB_QUEUE

# ============================================
# Database Connection Setup
# ============================================
from database import Database

# 載入資料庫配置
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "studio_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "studio_password")
DB_NAME = os.getenv("DB_NAME", "studio_db")

# 初始化資料庫連接
db_client = None
try:
    db_client = Database(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    logger.info(f"✓ 資料庫連接成功: {DB_HOST}:{DB_PORT}/{DB_NAME}")
except Exception as e:
    logger.warning(f"⚠️ 資料庫連接失敗 (功能降級): {e}")

# ============================================
# Redis Connection Setup
# ============================================
try:
    redis_client = Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    redis_client.ping()
    logger.info(f"✓ Redis 连接成功: {REDIS_HOST}:{REDIS_PORT}")
    
    # 配置 Limiter 使用 Redis
    limiter.storage_uri = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/1"
    
except RedisError as e:
    logger.error(f"✗ Redis 连接失败: {e}")
    redis_client = None

# ============================================
# 音訊上傳設定
# ============================================
ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3'}
UPLOAD_FOLDER = Path(__file__).parent.parent.parent / 'storage' / 'inputs'
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


# ============================================
# API Endpoints
# ============================================

@app.route('/api/upload', methods=['POST'])
@limiter.limit("30 per minute")
def upload_audio():
    """
    POST /api/upload
    上傳音訊檔案 (支援 .wav, .mp3)
    
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
        
        if file_ext not in ALLOWED_AUDIO_EXTENSIONS:
            logger.warning(f"不支援的音訊格式: {file_ext}")
            return jsonify({
                'error': f'Unsupported file type. Allowed: {", ".join(ALLOWED_AUDIO_EXTENSIONS)}'
            }), 400
        
        # 3. 生成唯一檔名 (保留原副檔名)
        unique_id = str(uuid.uuid4())[:12]
        new_filename = f"audio_{unique_id}{file_ext}"
        
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
            'original_name': file.filename  # 使用原始檔名（未經 secure_filename 處理）
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
    try:
        # 1. 验证请求数据
        data = request.get_json()
        if not data:
            logger.warning("请求缺少 JSON 数据")
            return jsonify({'error': 'Missing JSON data'}), 400
        
        prompt = data.get('prompt', '').strip()
        workflow = data.get('workflow', 'text_to_image')
        
        # ===== 安全性驗證：Prompt 長度限制 =====
        if len(prompt) > 1000:
            logger.warning(f"Prompt 超過長度限制: {len(prompt)} > 1000")
            return jsonify({'error': 'Prompt exceeds maximum length of 1000 characters'}), 400
        
        # 只有 text_to_image 需要 prompt
        if workflow == 'text_to_image' and not prompt:
            logger.warning("text_to_image 的 prompt 参数为空")
            return jsonify({'error': 'prompt is required for text_to_image'}), 400
        
        # 2. 生成唯一的 job_id
        job_id = str(uuid.uuid4())
        
        # 3. 构造任务数据 (包含所有前端傳來的參數)
        job_data = {
            'job_id': job_id,
            'prompt': prompt,
            'seed': data.get('seed', -1),  # -1 表示随机
            'workflow': data.get('workflow', 'text_to_image'),
            'model': data.get('model', 'turbo_fp8'),
            'aspect_ratio': data.get('aspect_ratio', '1:1'),
            'batch_size': data.get('batch_size', 1),
            'images': data.get('images', {}),  # Base64 圖片字典
            'audio': data.get('audio', ''),  # 音訊檔名 (virtual_human 工作流使用)
            'created_at': datetime.now().isoformat()
        }
        
        # 4. 推送到 Redis 队列
        if redis_client is None:
            logger.error("Redis 客户端未初始化")
            return jsonify({'error': 'Redis service unavailable'}), 503
        
        redis_client.rpush(REDIS_QUEUE_NAME, json.dumps(job_data))
        logger.info(f"✓ 任务已推送到队列: job_id={job_id}, prompt='{prompt}'")
        
        # 5. 初始化状态 Hash
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
        
        # 6. 寫入資料庫 (如果資料庫可用)
        if db_client:
            db_client.insert_job(
                job_id=job_id,
                prompt=prompt,
                workflow=workflow,
                model=job_data.get('model', 'turbo_fp8'),
                aspect_ratio=job_data.get('aspect_ratio', '1:1'),
                batch_size=job_data.get('batch_size', 1),
                seed=job_data.get('seed', -1),
                status='queued',
                input_audio_path=job_data.get('audio', None)  # Phase 7: 記錄音訊檔名
            )
        
        # 7. 返回成功响应
        return jsonify({
            'job_id': job_id,
            'status': 'queued'
        }), 202
    
    except Exception as e:
        logger.error(f"✗ generate 接口异常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/status/<job_id>', methods=['GET'])
@limiter.limit("2 per second")  # 每秒 2 次 = 每分鐘 120 次（寬鬆限制，適合輪詢）
def status(job_id):
    """
    GET /api/status/<job_id>
    查询任务状态
    
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
        if redis_client is None:
            logger.error("Redis 客户端未初始化")
            return jsonify({'error': 'Redis service unavailable'}), 503
        
        # 从 Redis 读取状态
        status_key = f"job:status:{job_id}"
        job_status = redis_client.hgetall(status_key)
        
        if not job_status:
            logger.warning(f"任务不存在: job_id={job_id}")
            return jsonify({'error': 'Job not found'}), 404
        
        # 如果任務已完成且資料庫可用，同步狀態到資料庫
        current_status = job_status.get('status', 'unknown')
        if db_client and current_status in ['finished', 'failed', 'cancelled']:
            output_path = job_status.get('image_url', '')
            db_client.update_job_status(job_id, current_status, output_path)
        
        # 返回状态信息
        return jsonify({
            'job_id': job_status.get('job_id', job_id),
            'status': job_status.get('status', 'unknown'),
            'progress': int(job_status.get('progress', 0)),
            'image_url': job_status.get('image_url', ''),
            'error': job_status.get('error', '')
        }), 200
    
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
                'message': f'Cannot cancel job with status: {current_status}'
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


@app.route('/api/history', methods=['GET'])
def get_history():
    """
    GET /api/history?limit=50&offset=0
    獲取歷史記錄列表
    
    Query Parameters:
        limit: 返回數量 (預設 50)
        offset: 偏移量 (預設 0)
    
    Response:
    {
        "total": 120,
        "limit": 50,
        "offset": 0,
        "jobs": [
            {
                "id": "uuid",
                "prompt": "...",
                "workflow": "text_to_image",
                "model": "turbo_fp8",
                "status": "finished",
                "output_path": "/outputs/xxx.png,/outputs/yyy.png",
                "created_at": "2024-12-31T10:00:00"
            }
        ]
    }
    """
    try:
        if db_client is None:
            logger.error("資料庫未初始化")
            return jsonify({'error': 'Database service unavailable'}), 503
        
        # 解析查詢參數
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))
        
        # 限制單次查詢數量
        limit = min(limit, 100)
        
        # 從資料庫獲取歷史記錄
        jobs = db_client.get_history(limit=limit, offset=offset)
        
        # 處理 output_path：轉換為前端可訪問的 URL 格式
        for job in jobs:
            output_path = job.get('output_path')
            if output_path:
                # 如果是逗號分隔的多個路徑，處理每一個
                paths = output_path.split(',')
                # 移除路徑前綴，只保留檔名，並轉換為 URL 格式
                formatted_paths = []
                for path in paths:
                    path = path.strip()
                    if path:
                        # 提取檔名（移除可能的路徑前綴）
                        filename = path.split('/')[-1].split('\\')[-1]
                        # 轉換為完整 URL
                        formatted_paths.append(f"/outputs/{filename}")
                # 用逗號連接所有路徑
                job['output_path'] = ','.join(formatted_paths) if formatted_paths else ''
        
        logger.info(f"✓ 查詢歷史記錄: {len(jobs)} 筆 (limit={limit}, offset={offset})")
        
        return jsonify({
            'total': len(jobs),  # 簡化版本，實際可查詢總數
            'limit': limit,
            'offset': offset,
            'jobs': jobs
        }), 200
    
    except Exception as e:
        logger.error(f"✗ history 接口异常: {e}", exc_info=True)
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
            'active_jobs': active_jobs
        }), 200
    
    except Exception as e:
        logger.error(f"✗ metrics 接口异常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/health', methods=['GET'])
def health():
    """健康检查接口 - 檢查 Redis 和 MySQL 狀態"""
    redis_status = 'healthy' if redis_client and redis_client.ping() else 'unavailable'
    
    mysql_status = 'unavailable'
    if db_client:
        mysql_status = 'healthy' if db_client.check_connection() else 'error'
    
    overall_status = 'ok' if redis_status == 'healthy' else 'degraded'
    
    return jsonify({
        'status': overall_status,
        'redis': redis_status,
        'mysql': mysql_status
    }), 200


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
# Static File Serving (for generated images/videos)
# ============================================
@app.route('/outputs/<path:filename>', methods=['GET'])
def serve_output(filename):
    """
    GET /outputs/<filename>
    Serve generated images/videos from storage/outputs directory
    支援 .png, .jpg, .mp4 等格式
    防止路徑穿越攻擊
    """
    import os
    import mimetypes
    from flask import send_from_directory, abort, Response
    
    # Get the absolute path to storage/outputs
    current_dir = os.path.dirname(os.path.abspath(__file__))
    outputs_dir = os.path.join(current_dir, '..', '..', 'storage', 'outputs')
    outputs_dir = os.path.abspath(outputs_dir)
    
    # ===== 安全性：防止路徑穿越攻擊 =====
    # 確保請求的檔案路徑嚴格位於 outputs_dir 內
    file_path = os.path.abspath(os.path.join(outputs_dir, filename))
    if not file_path.startswith(outputs_dir):
        logger.warning(f"⚠️ 路徑穿越攻擊嘗試: {filename}")
        return abort(403)  # Forbidden
    
    logger.info(f"📁 Serving file: {filename} from {outputs_dir}")
    
    # Check if file exists
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在: {file_path}")
        return abort(404)
    
    # 確保正確的 MIME Type (特別是影片檔案)
    mimetype, _ = mimetypes.guess_type(file_path)
    if mimetype is None:
        # 根據副檔名手動設定
        ext = os.path.splitext(filename)[1].lower()
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
    return send_from_directory(outputs_dir, filename, mimetype=mimetype)


# ============================================
# Application Entry Point
# ============================================

# Serve frontend static files
@app.route('/')
def serve_index():
    """提供前端 index.html"""
    try:
        frontend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend')
        frontend_dir = os.path.abspath(frontend_dir)
        index_path = os.path.join(frontend_dir, 'index.html')
        
        logger.info(f"Serving index.html from: {frontend_dir}")
        logger.info(f"index.html exists: {os.path.exists(index_path)}")
        
        if not os.path.exists(index_path):
            logger.error(f"index.html not found at {index_path}")
            return jsonify({"error": "Frontend not found"}), 404
            
        return send_from_directory(frontend_dir, 'index.html')
    except Exception as e:
        logger.error(f"Error serving index: {e}")
        return jsonify({"error": str(e)}), 500

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
        file_path = os.path.join(frontend_dir, path)
        
        logger.info(f"Serving static file: {path} from {frontend_dir}")
        logger.info(f"File exists: {os.path.exists(file_path)}")
        
        # 嘗試返回靜態文件
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(frontend_dir, path)
        else:
            # 文件不存在，返回 index.html（支持 SPA 路由）
            logger.warning(f"File not found: {path}, serving index.html instead")
            return send_from_directory(frontend_dir, 'index.html')
            
    except Exception as e:
        logger.error(f"Error serving static file {path}: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# 啟動 Flask 應用
# ==========================================
if __name__ == '__main__':
    import sys
    logger.info("🚀 Backend API 启动中...")
    logger.info("📁 同時提供前端靜態文件服務")
    
    # Windows 下 Flask reloader 有時會導致進程立即退出
    # 使用 threaded=True 確保服務穩定運行
    # use_reloader=False 避免 Windows 上的 reloader 問題
    is_windows = sys.platform.startswith('win')
    
    if is_windows:
        # Windows: 禁用 reloader 避免進程退出問題
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=True, 
            use_reloader=False,
            threaded=True
        )
    else:
        # Linux/Mac: 正常使用 reloader
        app.run(host='0.0.0.0', port=5000, debug=True)