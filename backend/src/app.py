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
CORS(app)  # 允许前端跨域访问

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

# Redis 连接配置
# 本地开发默认 localhost，Docker Compose 环境设置环境变量 REDIS_HOST=redis
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'mysecret')
REDIS_QUEUE_NAME = 'job_queue'

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

@app.route('/api/generate', methods=['POST'])
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
        if not prompt:
            logger.warning("prompt 参数为空")
            return jsonify({'error': 'prompt is required and cannot be empty'}), 400
        
        # 2. 生成唯一的 job_id
        job_id = str(uuid.uuid4())
        
        # 3. 构造任务数据
        job_data = {
            'job_id': job_id,
            'prompt': prompt,
            'seed': data.get('seed', -1),  # -1 表示随机
            'workflow': data.get('workflow', 'sdxl'),
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
        
        # 6. 返回成功响应
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


@app.route('/health', methods=['GET'])
def health():
    """健康检查接口"""
    redis_status = 'healthy' if redis_client and redis_client.ping() else 'unavailable'
    return jsonify({
        'status': 'ok',
        'redis': redis_status
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