"""
Backend API for Studio Core
提供任务提交和状态查询的接口
"""
import os
import sys
import json
import uuid
import logging
import threading
import time
import base64  # <--- 🟢 請補上這一行！
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from redis import Redis, RedisError
from werkzeug.utils import secure_filename

# ============================================
# 添加 shared 模組路徑並載入 .env
# ============================================
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.utils import load_env
load_env()

# ============================================
# Configuration & Logging Setup
# ============================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Session Cookie 配置 - 確保跨域請求能正確處理 cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 允許同站導航攜帶 cookie
app.config['SESSION_COOKIE_SECURE'] = False     # 開發環境用 HTTP，正式環境改為 True
app.config['SESSION_COOKIE_HTTPONLY'] = True    # 防止 JS 讀取 cookie
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = False

CORS(app)

# ============================================
# Flask-Login 和 Flask-Bcrypt 設定
# ============================================
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'api_login'  # 未登入時重定向的端點

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
     origins=["*"],
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=True)

# 手動處理 OPTIONS 預檢請求
@app.before_request
def before_request_handler():
    """
    在每個請求前處理：
    1. 提取客戶端 IP 地址
    2. 從資料庫獲取或建立用戶 ID
    3. 存儲到 Flask g 對象，供日誌使用
    """
    # 獲取客戶端 IP 地址（考慮代理）
    ip_address = request.headers.get('X-Forwarded-For')
    if ip_address:
        # 代理情況下，取第一個 IP
        ip_address = ip_address.split(',')[0].strip()
    else:
        ip_address = request.remote_addr or 'unknown'
    
    # 從資料庫獲取或建立用戶 ID
    if db_client:
        user_id = db_client.get_or_create_user_id(ip_address)
        if user_id > 0:
            g.user_id = f"User#{user_id:03d}"
        else:
            g.user_id = "User#ERR"
    else:
        g.user_id = "User#N/A"
    
    # 記錄請求開始
    logger.debug(f"📨 {request.method} {request.path} - IP: {ip_address}")

# 手動處理 OPTIONS 預檢請求
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        # 使用請求的 Origin 而非 *，因為 credentials=True 時不能用 *
        origin = request.headers.get('Origin', 'http://localhost:5000')
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

@app.after_request
def after_request(response):
    # 使用請求的 Origin 而非 *，因為 credentials=True 時不能用 *
    origin = request.headers.get('Origin', 'http://localhost:5000')
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    
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
    STORAGE_OUTPUT_DIR,
    # [TEMP] Veo3 測試模式配置
    VEO3_TEST_MODE, VEO3_TEST_VIDEO_PATH,
    PROJECT_ROOT  # 需要用於定位測試視頻文件
)
REDIS_QUEUE_NAME = JOB_QUEUE

# ============================================
# Database Connection Setup
# ============================================
from shared.database import Database, User, get_db_session, init_db
from shared.config_base import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
)

# 初始化資料庫連接 (使用 shared.config_base 統一配置)
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
# Flask-Login user_loader callback
# ============================================
@login_manager.user_loader
def load_user(user_id):
    """載入用戶（Flask-Login 回調）"""
    try:
        session = get_db_session()
        return session.query(User).get(int(user_id))
    except Exception as e:
        logger.error(f"載入用戶失敗: {e}")
        return None

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

# ============================================
# Auth API - 會員認證
# ============================================

@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per minute")
def api_register():
    """
    POST /api/register
    會員註冊
    
    Request Body:
    {
        "email": "user@example.com",
        "password": "password123",
        "name": "用戶名稱"
    }
    
    Response:
    {
        "success": true,
        "user": {...}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON data'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        
        # 驗證必填欄位
        if not email or not password or not name:
            return jsonify({'error': 'Email, password and name are required'}), 400
        
        # 驗證 Email 格式
        if '@' not in email or '.' not in email:
            return jsonify({'error': 'Invalid email format'}), 400
        
        # 驗證密碼長度
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        session = get_db_session()
        
        # 檢查 Email 是否已存在
        existing_user = session.query(User).filter_by(email=email).first()
        if existing_user:
            return jsonify({'error': 'Email already registered'}), 409
        
        # 建立新用戶
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            email=email,
            password_hash=password_hash,
            name=name,
            role='member'
        )
        
        session.add(new_user)
        session.commit()
        
        logger.info(f"✓ 新用戶註冊: {email}")
        
        return jsonify({
            'success': True,
            'user': new_user.to_dict()
        }), 201
    
    except Exception as e:
        logger.error(f"✗ 註冊失敗: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")
def api_login():
    """
    POST /api/login
    會員登入
    
    Request Body:
    {
        "email": "user@example.com",
        "password": "password123"
    }
    
    Response:
    {
        "success": true,
        "user": {...}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON data'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        session = get_db_session()
        user = session.query(User).filter_by(email=email).first()
        
        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401
        
        if not bcrypt.check_password_hash(user.password_hash, password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        login_user(user, remember=True)
        logger.info(f"✓ 用戶登入: {email}")
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        }), 200
    
    except Exception as e:
        logger.error(f"✗ 登入失敗: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """
    POST /api/logout
    會員登出
    
    Response:
    {
        "success": true,
        "message": "Logged out successfully"
    }
    """
    try:
        if current_user.is_authenticated:
            logger.info(f"✓ 用戶登出: {current_user.email}")
        logout_user()
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200
    except Exception as e:
        logger.error(f"✗ 登出失敗: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/me', methods=['GET'])
def api_me():
    """
    GET /api/me
    檢查登入狀態
    
    Response:
    {
        "logged_in": true,
        "user": {...}
    }
    """
    try:
        if current_user.is_authenticated:
            return jsonify({
                'logged_in': True,
                'user': current_user.to_dict()
            }), 200
        else:
            return jsonify({
                'logged_in': False,
                'user': None
            }), 200
    except Exception as e:
        logger.error(f"✗ 檢查登入狀態失敗: {e}", exc_info=True)
        return jsonify({
            'logged_in': False,
            'user': None
        }), 200


# ============================================
# Member API - 會員管理
# ============================================

@app.route('/api/user/profile', methods=['PUT'])
@login_required
def api_update_profile():
    """
    PUT /api/user/profile
    修改個人資料
    
    Request Body:
    {
        "name": "新名稱",
        "email": "new@example.com"  // 可選
    }
    
    Response:
    {
        "success": true,
        "user": {...}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON data'}), 400
        
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # 更新名稱
        if 'name' in data:
            name = data['name'].strip()
            if name:
                user.name = name
        
        # 更新 Email（需要檢查唯一性）
        if 'email' in data:
            new_email = data['email'].strip().lower()
            if new_email and new_email != user.email:
                existing = session.query(User).filter_by(email=new_email).first()
                if existing:
                    return jsonify({'error': 'Email already in use'}), 409
                user.email = new_email
        
        session.commit()
        logger.info(f"✓ 用戶資料更新: {user.email}")
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        }), 200
    
    except Exception as e:
        logger.error(f"✗ 更新資料失敗: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/user/password', methods=['PUT'])
@login_required
def api_update_password():
    """
    PUT /api/user/password
    修改密碼
    
    Request Body:
    {
        "old_password": "舊密碼",
        "new_password": "新密碼"
    }
    
    Response:
    {
        "success": true,
        "message": "Password updated successfully"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON data'}), 400
        
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return jsonify({'error': 'Old password and new password are required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400
        
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # 驗證舊密碼
        if not bcrypt.check_password_hash(user.password_hash, old_password):
            return jsonify({'error': 'Old password is incorrect'}), 401
        
        # 更新密碼
        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        session.commit()
        
        logger.info(f"✓ 用戶密碼更新: {user.email}")
        
        return jsonify({
            'success': True,
            'message': 'Password updated successfully'
        }), 200
    
    except Exception as e:
        logger.error(f"✗ 更新密碼失敗: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/user/delete', methods=['DELETE'])
@login_required
def api_delete_user():
    """
    DELETE /api/user/delete
    刪除帳號
    
    Response:
    {
        "success": true,
        "message": "Account deleted successfully"
    }
    """
    try:
        session = get_db_session()
        user = session.query(User).get(current_user.id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        email = user.email
        
        # 刪除用戶（CASCADE 會處理相關的 jobs）
        session.delete(user)
        session.commit()
        
        logout_user()
        logger.info(f"✓ 用戶帳號刪除: {email}")
        
        return jsonify({
            'success': True,
            'message': 'Account deleted successfully'
        }), 200
    
    except Exception as e:
        logger.error(f"✗ 刪除帳號失敗: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


# ============================================
# File Upload API
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
        prompts = data.get('prompts', [])  # Veo3 Long Video: 5 段視頻的 prompts
        workflow = data.get('workflow', 'text_to_image')
        
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
        
        # 3. 构造任务数据 (包含所有前端傳來的參數)
        job_data = {
            'job_id': job_id,
            'prompt': prompt,
            'prompts': prompts,  # Veo3 Long Video: 新增 prompts 列表
            'seed': data.get('seed', -1),  # -1 表示随机
            'workflow': data.get('workflow', 'text_to_image'),
            'model': data.get('model', 'turbo_fp8'),
            'aspect_ratio': data.get('aspect_ratio', '1:1'),
            'batch_size': data.get('batch_size', 1),
            'images': data.get('images', {}),  # Base64 圖片字典
            'audio': data.get('audio', ''),  # 音訊檔名 (virtual_human 工作流使用)
            'created_at': datetime.now().isoformat()
        }
        
        # ==========================================
        # [TEMP] Veo3 測試模式: Veo3 Long Video 攔截
        # ==========================================
        if VEO3_TEST_MODE and workflow == 'veo3_long_video':
            logger.info(f"🔧 [TEST MODE] 測試模式已啟用，檢查圖片上傳...")
            logger.info(f"🔧 [TEST MODE] VEO3_TEST_MODE={VEO3_TEST_MODE}, workflow={workflow}")
            
            # 檢查是否有上傳圖片
            images = data.get('images', {})
            has_images = bool(images and len(images) > 0)
            
            logger.info(f"🔧 [TEST MODE] 上傳圖片數量: {len(images) if images else 0}")
            logger.info(f"🔧 [TEST MODE] 檢測結果: has_images={has_images}")
            
            if has_images:
                logger.warning(f"🔧 [TEST MODE] ✅ 檢測到圖片上傳，返回測試視頻: {VEO3_TEST_VIDEO_PATH}")
                
                # 構造假的完成狀態並存入 Redis
                test_video_filename = os.path.basename(VEO3_TEST_VIDEO_PATH)
                test_video_url = f'/api/outputs/{test_video_filename}'
                
                status_key = f"job:status:{job_id}"
                redis_client.hset(status_key, mapping={
                    'job_id': job_id,
                    'status': 'finished',  # 前端檢查 'finished' 狀態
                    'progress': 100,
                    'image_url': test_video_url,  # 前端讀取 'image_url' 欄位
                    'video_url': test_video_url,  # 同時設置 video_url 供未來使用
                    'output_path': test_video_url,  # 備用欄位
                    'error': '',
                    'updated_at': datetime.now().isoformat(),
                    'test_mode': 'true'  # 標記為測試模式
                })
                redis_client.expire(status_key, 86400)
                
                # 將測試視頻複製到 outputs 目錄以便下載
                import shutil
                test_video_src = PROJECT_ROOT / VEO3_TEST_VIDEO_PATH
                test_video_dest = STORAGE_OUTPUT_DIR / test_video_filename
                if test_video_src.exists():
                    shutil.copy2(test_video_src, test_video_dest)
                    logger.info(f"✓ [TEST MODE] 測試視頻已複製到 outputs: {test_video_filename}")
                else:
                    logger.error(f"❌ [TEST MODE] 測試視頻不存在: {test_video_src}")
                
                # 直接返回完成狀態，跳過佇列處理
                return jsonify({
                    'job_id': job_id,
                    'status': 'completed',
                    'video_url': test_video_url,
                    'message': '[TEST MODE] 已返回測試視頻'
                }), 200
            else:
                logger.info(f"🔧 [TEST MODE] ❌ 未檢測到圖片上傳，繼續正常流程")
        
        # ===== Phase 10: 嚴格事務處理開始 =====
        # 4. 檢查 Redis 可用性
        if redis_client is None:
            logger.error("Redis 客户端未初始化")
            return jsonify({'error': 'Redis service unavailable'}), 503
        
        # 5. 開始資料庫事務 (使用 SQLAlchemy Session)
        session = get_db_session()
        
        try:
            # Member System: 獲取當前用戶 ID（如已登入）
            user_id_for_job = None
            if current_user.is_authenticated:
                user_id_for_job = current_user.id
            
            # 6. 建立 Job 物件並加入 Session
            from shared.database import Job
            new_job = Job(
                id=job_id,
                user_id=user_id_for_job,
                prompt=prompt,
                workflow_name=workflow,
                workflow_data=job_data,
                model=job_data.get('model', 'turbo_fp8'),
                aspect_ratio=job_data.get('aspect_ratio', '1:1'),
                batch_size=job_data.get('batch_size', 1),
                seed=job_data.get('seed', -1),
                status='queued',
                input_audio_path=job_data.get('audio', None)
            )
            session.add(new_job)
            
            # 7. Flush：強制寫入資料庫但不提交事務
            session.flush()
            logger.info(f"✓ Job {job_id} 已寫入資料庫 (未提交)")
            
            # 8. 推送到 Redis 佇列
            redis_client.rpush(REDIS_QUEUE_NAME, json.dumps(job_data))
            logger.info(f"✓ Job {job_id} 已推送至 Redis")
            
            # 9. 初始化 Redis 狀態 Hash
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
            
            # 10. 提交事務
            session.commit()
            logger.info(f"✓ Job {job_id} 事務已提交")
            
            # 11. 返回成功响应 (只有在事務提交成功後才返回)
            return jsonify({
                'job_id': job_id,
                'status': 'queued',
                'message': '任務已成功提交'
            }), 200
            
        except RedisError as redis_err:
            # Redis 失敗：回滾資料庫
            session.rollback()
            logger.error(f"❌ Redis Push 失敗，已回滾資料庫: {redis_err}")
            return jsonify({
                'error': '任務佇列異常，請稍後再試',
                'details': str(redis_err)
            }), 500
            
        except Exception as db_err:
            # 資料庫錯誤：回滾
            session.rollback()
            logger.error(f"❌ 資料庫操作失敗: {db_err}", exc_info=True)
            return jsonify({
                'error': '任務建立失敗',
                'details': str(db_err)
            }), 500
        
        # ===== Phase 10: 嚴格事務處理結束 =====
    
    except Exception as e:
        logger.error(f"✗ generate 接口异常: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500
    
    finally:
        # 確保 Session 關閉
        if session:
            session.close()


@app.route('/api/status/<job_id>', methods=['GET'])
@limiter.limit("2 per second")  # 每秒 2 次 = 每分鐘 120 次（寬鬆限制，適合輪詢）
def status(job_id):
    """
    GET /api/status/<job_id>
    查询任务状态
    
    ⭐ Phase 10: 增強查詢邏輯 - 優先 Redis，回退至資料庫
    流程: Redis (活動任務) → Database (歷史任務) → 404
    
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
                # Redis 中找到任務，同步到資料庫（如果已完成）
                current_status = job_status.get('status', 'unknown')
                if db_client and current_status in ['finished', 'failed', 'cancelled']:
                    output_path = job_status.get('image_url', '')
                    db_client.update_job_status(job_id, current_status, output_path)
                
                # 返回 Redis 中的狀態
                return jsonify({
                    'job_id': job_status.get('job_id', job_id),
                    'status': current_status,
                    'progress': int(job_status.get('progress', 0)),
                    'image_url': job_status.get('image_url', ''),
                    'error': job_status.get('error', ''),
                    'source': 'redis'  # 標記數據來源
                }), 200
        
        # 2. Redis 中沒找到，查詢資料庫 (歷史任務或 Redis 過期)
        if db_client:
            session = get_db_session()
            try:
                from shared.database import Job
                
                # 查詢資料庫中的任務記錄
                job = session.query(Job).filter_by(id=job_id).first()
                
                if job:
                    # 從資料庫恢復狀態
                    logger.info(f"✓ 從資料庫恢復任務狀態: {job_id} (status={job.status})")
                    
                    # 處理 output_path 轉換為 image_url 格式
                    image_url = ''
                    if job.status == 'finished':
                        # 從 Job ID 推導輸出檔案路徑 (根據實際儲存邏輯)
                        # 假設格式為: {job_id}_0.png
                        image_url = f"/outputs/{job_id}_0.png"
                    
                    return jsonify({
                        'job_id': job.id,
                        'status': job.status,
                        'progress': 100 if job.status == 'finished' else 0,
                        'image_url': image_url,
                        'error': '',
                        'source': 'database',  # 標記數據來源
                        'created_at': job.created_at.isoformat() if job.created_at else None
                    }), 200
                    
            finally:
                session.close()
        
        # 3. Redis 和資料庫都沒找到，返回 404
        logger.warning(f"任務不存在: job_id={job_id} (Redis 和資料庫均未找到)")
        return jsonify({
            'error': 'Job not found',
            'job_id': job_id,
            'message': '任務不存在或已被刪除'
        }), 404
    
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
        
        logger.info(f"📥 準備查詢資料庫: db_client={db_client is not None}, limit={limit}, offset={offset}")
        
        # Member System: 按登入用戶過濾
        user_id_filter = None
        if current_user.is_authenticated:
            user_id_filter = current_user.id
            logger.info(f"🔒 會員模式: 過濾 user_id={user_id_filter}")
        
        # 從資料庫獲取歷史記錄
        jobs = db_client.get_history(limit=limit, offset=offset, user_id=user_id_filter)
        
        logger.info(f"📤 資料庫返回: {len(jobs)} 筆記錄")
        
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
# Statistics & Monitoring Functions (Phase 3)
# ============================================

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
        'worker_online': False
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
    支援 .png, .jpg, .mp4 等格式
    防止路徑穿越攻擊
    """
    import mimetypes
    from flask import abort
    
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
    """
    根據登入狀態提供不同頁面：
    - 未登入：返回 login.html
    - 已登入：返回 dashboard.html (主應用)
    """
    try:
        frontend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend')
        frontend_dir = os.path.abspath(frontend_dir)
        
        # 檢查登入狀態
        if current_user.is_authenticated:
            # 已登入：返回主應用頁面
            dashboard_path = os.path.join(frontend_dir, 'dashboard.html')
            if os.path.exists(dashboard_path):
                logger.info(f"✓ 已登入用戶 {current_user.email}，返回 dashboard.html")
                return send_from_directory(frontend_dir, 'dashboard.html')
            else:
                # 向後兼容：如果沒有 dashboard.html，使用 index.html
                logger.warning(f"dashboard.html 不存在，使用 index.html")
                return send_from_directory(frontend_dir, 'index.html')
        else:
            # 未登入：返回登入頁面
            login_path = os.path.join(frontend_dir, 'login.html')
            if os.path.exists(login_path):
                logger.info("訪客訪問 /，返回 login.html")
                return send_from_directory(frontend_dir, 'login.html')
            else:
                logger.error(f"login.html not found at {login_path}")
                return jsonify({"error": "Login page not found"}), 404
                
    except Exception as e:
        logger.error(f"Error serving page: {e}", exc_info=True)
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
    
    logger.info("🚀 Backend API 啟動中...")
    logger.info("📁 同時提供前端靜態文件服務")
    logger.info("✓ 結構化日誌系統已啟動（雙通道輸出）")
    
    # [TEMP] 顯示 Veo3 測試模式狀態
    if VEO3_TEST_MODE:
        logger.warning(f"🔧 [TEST MODE] Veo3 測試模式已啟用！")
        logger.warning(f"🔧 [TEST MODE] 觸發條件: veo3_long_video + 上傳圖片")
        logger.warning(f"🔧 [TEST MODE] 測試視頻: {VEO3_TEST_VIDEO_PATH}")
    else:
        logger.info("ℹ️  Veo3 測試模式未啟用")
    
    is_windows = sys.platform.startswith('win')
    
    try:
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
    except KeyboardInterrupt:
        logger.info("\n⏹️ 正在關閉 Backend...")
        logger.info("✓ Backend 已優雅關閉")
        sys.exit(0)