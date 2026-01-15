"""
Database Module for Studio Core
提供 MySQL 連接池和 Jobs 表操作
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import mysql.connector
from mysql.connector import pooling, Error

logger = logging.getLogger(__name__)


class Database:
    """MySQL 資料庫管理類"""
    
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
        """初始化資料庫 Schema - 建立 jobs 和 user_mapping 表"""
        create_jobs_table_sql = """
        CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR(36) PRIMARY KEY,
            prompt TEXT,
            workflow VARCHAR(50),
            model VARCHAR(100),
            aspect_ratio VARCHAR(10),
            batch_size INT DEFAULT 1,
            seed INT DEFAULT -1,
            status VARCHAR(20),
            output_path TEXT,
            input_audio_path VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            INDEX idx_status (status),
            INDEX idx_created_at (created_at),
            INDEX idx_is_deleted (is_deleted)
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
            cursor.execute(create_jobs_table_sql)
            cursor.execute(create_user_mapping_table_sql)
            conn.commit()
            logger.info("✓ Jobs 和 user_mapping 表初始化成功")
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
        input_audio_path: Optional[str] = None
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
            input_audio_path: 輸入音訊檔名 (Phase 7 新增)
        
        Returns:
            是否成功
        """
        sql = """
        INSERT INTO jobs (id, prompt, workflow, model, aspect_ratio, batch_size, seed, status, input_audio_path)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (job_id, prompt, workflow, model, aspect_ratio, batch_size, seed, status, input_audio_path))
            conn.commit()
            logger.info(f"✓ 任務記錄插入成功: {job_id}")
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
        output_path: Optional[str] = None
    ) -> bool:
        """
        更新任務狀態
        
        Args:
            job_id: 任務 ID
            status: 新狀態 (finished, failed, cancelled)
            output_path: 輸出圖片路徑 (多張用逗號分隔)
        
        Returns:
            是否成功
        """
        if output_path:
            sql = "UPDATE jobs SET status = %s, output_path = %s WHERE id = %s"
            params = (status, output_path, job_id)
        else:
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
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        獲取歷史記錄
        
        Args:
            limit: 返回數量
            offset: 偏移量
            include_deleted: 是否包含已刪除記錄
        
        Returns:
            任務記錄列表
        """
        where_clause = "" if include_deleted else "WHERE is_deleted = FALSE"
        sql = f"""
        SELECT id, prompt, workflow, model, aspect_ratio, batch_size, seed,
               status, output_path, created_at, updated_at
        FROM jobs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """
        
        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            print(f"[DB DEBUG] 執行 SQL 查詢 (limit={limit}, offset={offset})")
            print(f"[DB DEBUG] SQL: {sql.strip()[:200]}...")
            cursor.execute(sql, (limit, offset))
            results = cursor.fetchall()
            
            print(f"[DB DEBUG] fetchall() 返回 {len(results)} 筆原始記錄")
            if results:
                print(f"[DB DEBUG] 第一筆: {results[0].get('id', 'N/A')}, status={results[0].get('status', 'N/A')}")
            
            logger.info(f"🔍 執行 SQL 查詢 (limit={limit}, offset={offset})")
            logger.info(f"📝 SQL: {sql.strip()}")
            logger.info(f"📊 fetchall() 返回 {len(results)} 筆原始記錄")
            
            # 將 datetime 轉換為 ISO 字串
            for row in results:
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat()
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
            
            logger.info(f"✓ 查詢歷史記錄: {len(results)} 筆")
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
        軟刪除任務 (設置 is_deleted = TRUE)
        
        Args:
            job_id: 任務 ID
        
        Returns:
            是否成功
        """
        sql = "UPDATE jobs SET is_deleted = TRUE WHERE id = %s"
        
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
    
    def soft_delete_by_output_path(self, output_filename: str) -> bool:
        """
        根據輸出檔名軟刪除任務
        
        Args:
            output_filename: 輸出檔名 (例如: "abc123.png")
        
        Returns:
            是否成功
        """
        sql = "UPDATE jobs SET is_deleted = TRUE WHERE output_path LIKE %s"
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (f"%{output_filename}%",))
            affected_rows = cursor.rowcount
            conn.commit()
            
            if affected_rows > 0:
                logger.info(f"✓ 已軟刪除 {affected_rows} 筆任務 (檔名: {output_filename})")
            return True
        except Error as e:
            logger.error(f"✗ 根據檔名軟刪除失敗: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    
    def get_or_create_user_id(self, ip_address: str) -> int:
        """
        根據 IP 地址獲取或建立用戶 ID
        如果 IP 地址已存在，返回現有的用戶 ID
        如果 IP 地址不存在，建立新的用戶 ID 並返回
        
        Args:
            ip_address: 用戶的 IP 地址
        
        Returns:
            用戶 ID (INT)
        """
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            
            # 查詢現有用戶
            query_sql = "SELECT id FROM user_mapping WHERE ip_address = %s"
            cursor.execute(query_sql, (ip_address,))
            result = cursor.fetchone()
            
            if result:
                # 更新 last_active 時間
                update_sql = "UPDATE user_mapping SET last_active = CURRENT_TIMESTAMP WHERE ip_address = %s"
                cursor.execute(update_sql, (ip_address,))
                conn.commit()
                return result['id']
            else:
                # 建立新用戶
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
        """
        獲取過去 24 小時內活躍的用戶數
        
        Returns:
            活躍用戶數
        """
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
