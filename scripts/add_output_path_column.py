"""
資料庫遷移腳本：添加 output_path 欄位到 jobs 表
執行方式: python scripts/add_output_path_column.py
"""

import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.utils import load_env, setup_logger
from shared.config_base import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
import mysql.connector
from mysql.connector import Error
import logging

# 載入環境變數
load_env()

# 設置日誌
logger = setup_logger("migration", log_level=logging.INFO)

def run_migration():
    """執行資料庫遷移"""
    conn = None
    cursor = None
    
    try:
        # 連接資料庫
        logger.info(f"連接資料庫: {DB_HOST}:{DB_PORT}/{DB_NAME}")
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        if not conn.is_connected():
            logger.error("無法連接到資料庫")
            return False
        
        cursor = conn.cursor()
        
        # 檢查 output_path 欄位是否已存在
        check_column_sql = """
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = %s 
        AND TABLE_NAME = 'jobs' 
        AND COLUMN_NAME = 'output_path'
        """
        cursor.execute(check_column_sql, (DB_NAME,))
        column_exists = cursor.fetchone()[0] > 0
        
        if column_exists:
            logger.info("✓ output_path 欄位已存在，跳過遷移")
            return True
        
        # 添加 output_path 欄位
        logger.info("正在添加 output_path 欄位...")
        alter_table_sql = """
        ALTER TABLE jobs 
        ADD COLUMN output_path TEXT DEFAULT NULL 
        AFTER status
        """
        cursor.execute(alter_table_sql)
        conn.commit()
        
        logger.info("✅ 成功添加 output_path 欄位")
        
        # 驗證欄位已添加
        cursor.execute(check_column_sql, (DB_NAME,))
        if cursor.fetchone()[0] > 0:
            logger.info("✓ 驗證成功：output_path 欄位已正確添加")
            return True
        else:
            logger.error("✗ 驗證失敗：output_path 欄位未正確添加")
            return False
        
    except Error as e:
        logger.error(f"❌ 資料庫遷移失敗: {e}")
        return False
    
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            logger.info("資料庫連接已關閉")

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("開始執行資料庫遷移：添加 output_path 欄位")
    logger.info("=" * 60)
    
    success = run_migration()
    
    if success:
        logger.info("=" * 60)
        logger.info("✅ 資料庫遷移完成")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("❌ 資料庫遷移失敗")
        logger.error("=" * 60)
        sys.exit(1)
