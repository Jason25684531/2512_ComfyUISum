"""
Database Module for Studio Core
提供 MySQL 連接池、ORM 模型 (User, Job) 和資料庫操作

Phase: Member System Beta
- 新增 User 模型 (UserMixin)
- 新增 Job 模型 (FK: user_id)
- 移除 output_path，改用 ID 推導檔名
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

# MySQL Connector (連接池)
import mysql.connector
from mysql.connector import pooling, Error

# SQLAlchemy ORM
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.dialects.mysql import JSON

# Flask-Login
from flask_login import UserMixin

logger = logging.getLogger(__name__)

# ===========================================
# SQLAlchemy Base 和 Engine
# ===========================================
Base = declarative_base()

# 全局 Session 和 Engine (延遲初始化)
_engine = None
_session_factory = None


def get_db_engine(db_url: Optional[str] = None):
    """獲取或建立 SQLAlchemy Engine"""
    global _engine
    if _engine is None:
        if db_url is None:
            # 從環境變數建立 URL
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "3306")
            user = os.getenv("DB_USER", "studio_user")
            password = os.getenv("DB_PASSWORD", "studio_password")
            database = os.getenv("DB_NAME", "studio_db")
            db_url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
        
        _engine = create_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            echo=False
        )
        logger.info(f"✓ SQLAlchemy Engine 建立成功")
    return _engine


def get_db_session():
    """獲取 Scoped Session"""
    global _session_factory
    if _session_factory is None:
        engine = get_db_engine()
        _session_factory = scoped_session(sessionmaker(bind=engine))
    return _session_factory()


def init_db():
    """初始化資料庫表格 (使用 ORM 建立)"""
    engine = get_db_engine()
    Base.metadata.create_all(engine)
    logger.info("✓ SQLAlchemy ORM 表格初始化完成")


# ===========================================
# ORM Models
# ===========================================

class User(UserMixin, Base):
    """
    用戶模型 - 支援 Flask-Login
    
    Attributes:
        id: 用戶 ID (PK)
        email: 登入帳號 (Unique)
        password_hash: Bcrypt 加密密碼
        name: 顯示暱稱
        role: 權限 (member/admin)
        created_at: 註冊時間
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    role = Column(String(20), default='member')
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationship: User -> Jobs (一對多)
    jobs = relationship("Job", back_populates="user", lazy="dynamic")
    
    def to_dict(self):
        """轉換為字典（API 回應用）"""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Job(Base):
    """
    任務模型 - 算圖任務記錄
    
    Attributes:
        id: 任務 ID (PK, UUID 字串)
        user_id: 用戶 ID (FK, 可為空以相容舊資料)
        prompt: 提示詞
        workflow_name: 工作流名稱
        workflow_data: ComfyUI 完整參數 (JSON)
        model: 模型名稱
        aspect_ratio: 圖片比例
        batch_size: 批次大小
        seed: 隨機種子
        status: 任務狀態
        input_audio_path: 輸入音訊檔名
        created_at: 建立時間
        updated_at: 更新時間
        deleted_at: 軟刪除時間 (Nullable)
    """
    __tablename__ = 'jobs'
    
    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    prompt = Column(Text, nullable=True)
    workflow_name = Column(String(50), nullable=True)  # 工作流名稱
    workflow_data = Column(JSON, nullable=True)  # 完整 ComfyUI 參數
    model = Column(String(100), nullable=True)
    aspect_ratio = Column(String(10), nullable=True)
    batch_size = Column(Integer, default=1)
    seed = Column(Integer, default=-1)
    status = Column(String(20), default='queued')
    input_audio_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True)
    
    # 相容舊欄位 (標記為棄用，保留以避免遷移錯誤)
    is_deleted = Column(Boolean, default=False)
    
    # Relationship: Job -> User (多對一)
    user = relationship("User", back_populates="jobs")
    
    def to_dict(self):
        """轉換為字典（API 回應用）"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "prompt": self.prompt,
            "workflow": self.workflow_name,
            "model": self.model,
            "aspect_ratio": self.aspect_ratio,
            "batch_size": self.batch_size,
            "seed": self.seed,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


# ===========================================
# 原有 Database 類 (連接池 + 原生 SQL)
# 保留以相容現有程式碼
# ===========================================

class Database:
    """MySQL 資料庫管理類 (使用連接池)"""
    
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        pool_name: str = "studio_pool",
        pool_size: int = 5
    ):
        """
        初始化資料庫連接池
        
        Args:
            host: MySQL 主機位址
            port: MySQL 端口
            user: 用戶名
            password: 密碼
            database: 資料庫名稱
            pool_name: 連接池名稱
            pool_size: 連接池大小
        """
        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "pool_name": pool_name,
            "pool_size": pool_size,
            "pool_reset_session": True,
        }
        
        try:
            self.pool = pooling.MySQLConnectionPool(**self.config)
            logger.info(f"✓ MySQL 連接池建立成功: {host}:{port}/{database}")
            self._init_schema()
        except Error as e:
            logger.error(f"✗ MySQL 連接池建立失敗: {e}")
            raise
    
    def _init_schema(self):
        """初始化資料庫 Schema - 建立 users, jobs, user_mapping 表"""
        # 新增 users 表
        create_users_table_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INT PRIMARY KEY AUTO_INCREMENT,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            name VARCHAR(50) NOT NULL,
            role VARCHAR(20) DEFAULT 'member',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_email (email)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        # 更新 jobs 表 (新增 user_id, workflow_data, deleted_at)
        create_jobs_table_sql = """
        CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR(36) PRIMARY KEY,
            user_id INT DEFAULT NULL,
            prompt TEXT,
            workflow_name VARCHAR(50),
            workflow_data JSON,
            model VARCHAR(100),
            aspect_ratio VARCHAR(10),
            batch_size INT DEFAULT 1,
            seed INT DEFAULT -1,
            status VARCHAR(20),
            input_audio_path VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP NULL DEFAULT NULL,
            is_deleted BOOLEAN DEFAULT FALSE,
            INDEX idx_user_id (user_id),
            INDEX idx_status (status),
            INDEX idx_created_at (created_at),
            INDEX idx_deleted_at (deleted_at),
            CONSTRAINT fk_jobs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        create_user_mapping_table_sql = """
        CREATE TABLE IF NOT EXISTS user_mapping (
            id INT PRIMARY KEY AUTO_INCREMENT,
            ip_address VARCHAR(45) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_ip (ip_address),
            INDEX idx_last_active (last_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            
            # 先建立 users 表 (因為 jobs 有 FK 依賴)
            cursor.execute(create_users_table_sql)
            cursor.execute(create_jobs_table_sql)
            cursor.execute(create_user_mapping_table_sql)
            conn.commit()
            logger.info("✓ Users, Jobs, user_mapping 表初始化成功")
        except Error as e:
            logger.error(f"✗ 建立表失敗: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def insert_job(
        self,
        job_id: str,
        prompt: str,
        workflow: str,
        model: str,
        aspect_ratio: str = "1:1",
        batch_size: int = 1,
        seed: int = -1,
        status: str = "queued",
        input_audio_path: Optional[str] = None,
        user_id: Optional[int] = None,
        workflow_data: Optional[dict] = None
    ) -> bool:
        """
        插入新任務記錄
        
        Args:
            job_id: 任務 ID (UUID)
            prompt: 提示詞
            workflow: 工作流名稱
            model: 模型名稱
            aspect_ratio: 圖片比例
            batch_size: 批次大小
            seed: 隨機種子
            status: 任務狀態
            input_audio_path: 輸入音訊檔名
            user_id: 用戶 ID (Member System)
            workflow_data: 完整工作流參數 (JSON)
        
        Returns:
            是否成功
        """
        import json
        
        sql = """
        INSERT INTO jobs (id, user_id, prompt, workflow_name, workflow_data, model, aspect_ratio, batch_size, seed, status, input_audio_path)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        workflow_json = json.dumps(workflow_data) if workflow_data else None
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (job_id, user_id, prompt, workflow, workflow_json, model, aspect_ratio, batch_size, seed, status, input_audio_path))
            conn.commit()
            logger.info(f"✓ 任務記錄插入成功: {job_id}" + (f" (User: {user_id})" if user_id else ""))
            return True
        except Error as e:
            logger.error(f"✗ 插入任務失敗: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def update_job_status(
        self,
        job_id: str,
        status: str,
        output_path: Optional[str] = None  # 保留參數相容性，但不再使用
    ) -> bool:
        """
        更新任務狀態
        
        Args:
            job_id: 任務 ID
            status: 新狀態 (finished, failed, cancelled)
            output_path: [已棄用] 輸出路徑（不再儲存，改用 ID 推導）
        
        Returns:
            是否成功
        """
        sql = "UPDATE jobs SET status = %s WHERE id = %s"
        params = (status, job_id)
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            logger.info(f"✓ 任務狀態更新: {job_id} -> {status}")
            return True
        except Error as e:
            logger.error(f"✗ 更新任務狀態失敗: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        獲取歷史記錄
        
        Args:
            limit: 返回數量
            offset: 偏移量
            include_deleted: 是否包含已刪除記錄
            user_id: 用戶 ID (Member System 過濾)
        
        Returns:
            任務記錄列表
        """
        where_clauses = []
        params = []
        
        if not include_deleted:
            where_clauses.append("deleted_at IS NULL AND is_deleted = FALSE")
        
        if user_id is not None:
            where_clauses.append("user_id = %s")
            params.append(user_id)
        
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        sql = f"""
        SELECT id, user_id, prompt, workflow_name as workflow, model, aspect_ratio, batch_size, seed,
               status, created_at, updated_at
        FROM jobs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        
        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            logger.info(f"🔍 執行 SQL 查詢 (limit={limit}, offset={offset}, user_id={user_id})")
            cursor.execute(sql, tuple(params))
            results = cursor.fetchall()
            
            logger.info(f"📊 fetchall() 返回 {len(results)} 筆記錄")
            
            # 將 datetime 轉換為 ISO 字串
            for row in results:
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat()
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
                
                # 構建輸出路徑 (使用 ID 推導)
                row['output_path'] = f"/outputs/{row['id']}.png"
            
            return results
        except Error as e:
            logger.error(f"✗ 查詢歷史失敗: {e}", exc_info=True)
            return []
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
    
    def soft_delete_job(self, job_id: str) -> bool:
        """
        軟刪除任務 (設置 deleted_at)
        
        Args:
            job_id: 任務 ID
        
        Returns:
            是否成功
        """
        sql = "UPDATE jobs SET deleted_at = CURRENT_TIMESTAMP, is_deleted = TRUE WHERE id = %s"
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (job_id,))
            conn.commit()
            logger.info(f"✓ 任務已軟刪除: {job_id}")
            return True
        except Error as e:
            logger.error(f"✗ 軟刪除失敗: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_or_create_user_id(self, ip_address: str) -> int:
        """
        根據 IP 地址獲取或建立用戶 ID
        
        Args:
            ip_address: 用戶的 IP 地址
        
        Returns:
            用戶 ID (INT)
        """
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            query_sql = "SELECT id FROM user_mapping WHERE ip_address = %s"
            cursor.execute(query_sql, (ip_address,))
            result = cursor.fetchone()
            
            if result:
                update_sql = "UPDATE user_mapping SET last_active = CURRENT_TIMESTAMP WHERE ip_address = %s"
                cursor.execute(update_sql, (ip_address,))
                conn.commit()
                return result['id']
            else:
                insert_sql = "INSERT INTO user_mapping (ip_address) VALUES (%s)"
                cursor.execute(insert_sql, (ip_address,))
                conn.commit()
                user_id = cursor.lastrowid
                logger.debug(f"✓ 新用戶建立: User #{user_id} ({ip_address})")
                return user_id
        except Error as e:
            logger.error(f"✗ 獲取或建立用戶 ID 失敗: {e}")
            return -1
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_active_users_count(self) -> int:
        """獲取過去 24 小時內活躍的用戶數"""
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            sql = "SELECT COUNT(*) FROM user_mapping WHERE last_active >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"
            cursor.execute(sql)
            result = cursor.fetchone()
            return result[0] if result else 0
        except Error as e:
            logger.error(f"✗ 查詢活躍用戶失敗: {e}")
            return 0
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def check_connection(self) -> bool:
        """檢查資料庫連接是否正常"""
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Error as e:
            logger.error(f"✗ 資料庫連接檢查失敗: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
