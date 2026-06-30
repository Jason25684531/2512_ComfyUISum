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
import html
from uuid import UUID

# MySQL Connector (連接池)
import mysql.connector
from mysql.connector import pooling, Error, errorcode

# SQLAlchemy ORM
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, scoped_session
from sqlalchemy.dialects.mysql import JSON

# Flask-Login
from flask_login import UserMixin

from shared.config_base import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

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
            # 從共用配置建立 URL，確保本機與容器模式一致
            host = DB_HOST
            port = DB_PORT
            user = DB_USER
            password = DB_PASSWORD
            if not password:
                raise ValueError("Database credentials are not set")
            database = DB_NAME
            db_url = URL.create(
                "mysql+mysqlconnector",
                username=user,
                password=password.strip(),
                host=host,
                port=int(port),
                database=database,
            )
        
        _engine = create_engine(
            db_url,
            pool_size=20,            # Phase 7: 增加至 20 (適應 50 並發)
            max_overflow=30,         # Phase 7: 峰值可達 50 連接
            pool_recycle=3600,
            pool_pre_ping=True,      # Phase 7: 連接前先檢查有效性
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
            "email": html.escape(str(self.email)),
            "name": html.escape(str(self.name)),
            "role": html.escape(str(self.role)),
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
            "prompt": html.escape(str(self.prompt)) if self.prompt else None,
            "workflow": html.escape(str(self.workflow_name)) if self.workflow_name else None,
            "model": html.escape(str(self.model)) if self.model else None,
            "aspect_ratio": self.aspect_ratio,
            "batch_size": self.batch_size,
            "seed": self.seed,
            "status": html.escape(str(self.status)) if self.status else None,
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
        pool_size: int = 20          # Phase 7: 預設改為 20
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

        self.pool = None
        self._initialize_pool()

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return f"`{value.replace('`', '``')}`"

    @staticmethod
    def _quote_sql_literal(value: str) -> str:
        return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"

    def _should_attempt_access_repair(self, exc: Error) -> bool:
        root_password = os.getenv("MYSQL_ROOT_PASSWORD", "").strip()
        if self.config["user"] == "root" or not root_password:
            return False

        errno = getattr(exc, "errno", None)
        if errno == errorcode.ER_ACCESS_DENIED_ERROR:
            return True

        return "access denied" in str(exc).lower()

    def _repair_application_user(self) -> None:
        root_password = os.getenv("MYSQL_ROOT_PASSWORD", "").strip()
        if not root_password:
            raise ValueError("MYSQL_ROOT_PASSWORD is not set; cannot repair local application user")

        connection = None
        cursor = None
        database_name = self._quote_identifier(str(self.config["database"]))
        user_literal = self._quote_sql_literal(str(self.config["user"]))
        password_literal = self._quote_sql_literal(str(self.config["password"]))

        try:
            connection = mysql.connector.connect(
                host=self.config["host"],
                port=self.config["port"],
                user="root",
                password=root_password,
            )
            cursor = connection.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {database_name} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(
                f"CREATE USER IF NOT EXISTS {user_literal}@'%' IDENTIFIED BY {password_literal}"
            )
            cursor.execute(
                f"ALTER USER {user_literal}@'%' IDENTIFIED BY {password_literal}"
            )
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON {database_name}.* TO {user_literal}@'%'"
            )
            cursor.execute("FLUSH PRIVILEGES")
            connection.commit()
            logger.info("✓ MySQL 應用帳號已使用 root 自動同步")
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None and connection.is_connected():
                connection.close()

    def _initialize_pool(self) -> None:
        try:
            self.pool = pooling.MySQLConnectionPool(**self.config)
            logger.info(
                f"✓ MySQL 連接池建立成功: {self.config['host']}:{self.config['port']}/{self.config['database']}"
            )
            self._init_schema()
        except Error as e:
            if self._should_attempt_access_repair(e):
                logger.warning("⚠️ 偵測到 MySQL 應用帳號驗證失敗，嘗試以 root 自動修復本機帳號與權限")
                self._repair_application_user()
                self.pool = pooling.MySQLConnectionPool(**self.config)
                logger.info(
                    f"✓ MySQL 連接池建立成功: {self.config['host']}:{self.config['port']}/{self.config['database']}"
                )
                self._init_schema()
                return

            logger.exception("✗ MySQL 連接池建立失敗")
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
        
        conn = None
        cursor = None
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
            logger.exception("✗ 建立表失敗")
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None and conn.is_connected():
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

        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (job_id, user_id, prompt, workflow, workflow_json, model, aspect_ratio, batch_size, seed, status, input_audio_path))
            conn.commit()
            logger.info(f"✓ 任務記錄插入成功: {job_id}" + (f" (User: {user_id})" if user_id else ""))
            return True
        except Error as e:
            logger.exception("✗ 插入任務失敗")
            return False
        finally:
            if conn is not None and conn.is_connected():
                if cursor is not None:
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

        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            logger.info(f"✓ 任務狀態更新: {job_id} -> {status}")
            return True
        except Error as e:
            logger.exception("✗ 更新任務狀態失敗")
            return False
        finally:
            if conn is not None and conn.is_connected():
                if cursor is not None:
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
            logger.exception("✗ 查詢歷史失敗")
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

        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (job_id,))
            conn.commit()
            logger.info(f"✓ 任務已軟刪除: {job_id}")
            return True
        except Error as e:
            logger.exception("✗ 軟刪除失敗")
            return False
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def soft_delete_by_output_path(self, output_path: str) -> bool:
        """
        向後相容：從 output_path 或檔名推導 job_id 並執行軟刪除。

        Args:
            output_path: 可為 `/outputs/<job_id>.png` 或純檔名 `<job_id>.png`

        Returns:
            是否成功
        """
        if not output_path:
            return False

        filename = os.path.basename(str(output_path).strip())
        job_id, _ = os.path.splitext(filename)

        try:
            normalized_job_id = str(UUID(job_id))
        except (ValueError, TypeError, AttributeError):
            logger.debug(f"略過無法對應 job_id 的輸出檔: {output_path}")
            return False

        return self.soft_delete_job(normalized_job_id)
    
    def get_or_create_user_id(self, ip_address: str) -> int:
        """
        根據 IP 地址獲取或建立用戶 ID
        
        Args:
            ip_address: 用戶的 IP 地址
        
        Returns:
            用戶 ID (INT)
        """
        conn = None
        cursor = None
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
            logger.exception("✗ 獲取或建立用戶 ID 失敗")
            return -1
        finally:
            if conn is not None and conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()

    def get_active_users_count(self) -> int:
        """獲取過去 24 小時內活躍的用戶數"""
        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            sql = "SELECT COUNT(*) FROM user_mapping WHERE last_active >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"
            cursor.execute(sql)
            result = cursor.fetchone()
            return result[0] if result else 0
        except Error as e:
            logger.exception("✗ 查詢活躍用戶失敗")
            return 0
        finally:
            if conn is not None and conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()

    def check_connection(self) -> bool:
        """檢查資料庫連接是否正常"""
        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except Error as e:
            logger.exception("✗ 資料庫連接檢查失敗")
            return False
        finally:
            if conn is not None and conn.is_connected():
                if cursor is not None:
                    cursor.close()
                conn.close()
