"""
Backend API for Studio Core
提供任务提交和状态查询的接口
"""
import os
import json
import uuid
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from redis import Redis, RedisError

# ============================================
# Configuration & Logging Setup
# ============================================
app = Flask(__name__)

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
    return response

# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
except RedisError as e:
    logger.error(f"✗ Redis 连接失败: {e}")
    redis_client = None

# ============================================
# API Endpoints
# ============================================

@app.route('/api/generate', methods=['POST', 'OPTIONS'])
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
                status='queued'
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
# Static File Serving (for generated images)
# ============================================
@app.route('/outputs/<path:filename>', methods=['GET'])
def serve_output(filename):
    """
    GET /outputs/<filename>
    Serve generated images from storage/outputs directory
    """
    import os
    from flask import send_from_directory, abort
    
    # Get the absolute path to storage/outputs
    current_dir = os.path.dirname(os.path.abspath(__file__))
    outputs_dir = os.path.join(current_dir, '..', '..', 'storage', 'outputs')
    outputs_dir = os.path.abspath(outputs_dir)
    
    logger.info(f"📁 Serving file: {filename} from {outputs_dir}")
    
    # Check if file exists
    file_path = os.path.join(outputs_dir, filename)
    if not os.path.exists(file_path):
        logger.warning(f"文件不存在: {file_path}")
        return abort(404)
    
    return send_from_directory(outputs_dir, filename)


# ============================================
# Application Entry Point
# ============================================
if __name__ == '__main__':
    logger.info("🚀 Backend API 启动中...")
    app.run(host='0.0.0.0', port=5000, debug=True)