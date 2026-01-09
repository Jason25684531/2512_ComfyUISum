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
        """初始化資料庫 Schema - 建立 jobs 表"""
        create_table_sql = """
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
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            conn.commit()
            logger.info("✓ Jobs 表初始化成功")
        except Error as e:
            logger.error(f"✗ 建立 Jobs 表失敗: {e}")
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
               status, output_path, input_audio_path, created_at, updated_at
        FROM jobs
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, (limit, offset))
            results = cursor.fetchall()
            
            # 將 datetime 轉換為 ISO 字串
            for row in results:
                if row.get('created_at'):
                    row['created_at'] = row['created_at'].isoformat()
                if row.get('updated_at'):
                    row['updated_at'] = row['updated_at'].isoformat()
            
            logger.info(f"✓ 查詢歷史記錄: {len(results)} 筆")
            return results
        except Error as e:
            logger.error(f"✗ 查詢歷史失敗: {e}")
            return []
        finally:
            if conn.is_connected():
                cursor.close()
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
