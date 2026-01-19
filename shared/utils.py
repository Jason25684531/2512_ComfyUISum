"""
Shared Utilities
================
專案共用的工具函式，供 Backend 和 Worker 使用。
避免代碼重複，提高維護性。
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


def load_env(base_path: Path = None) -> None:
    """
    自動載入專案根目錄的 .env 檔案
    
    Args:
        base_path: 基礎路徑，預設為呼叫檔案的上上層目錄
    """
    if base_path is None:
        # 預設使用專案根目錄
        base_path = Path(__file__).parent.parent
    
    env_path = base_path / ".env"
    
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"✓ 已載入 .env 檔案: {env_path}")
    else:
        print(f"⚠️ .env 檔案不存在: {env_path}")


def get_project_root() -> Path:
    """
    取得專案根目錄的絕對路徑
    
    Returns:
        專案根目錄 Path 物件
    """
    return Path(__file__).parent.parent.resolve()


# ==========================================
# Phase 2: Structured Logging System
# ==========================================

class JSONFormatter(logging.Formatter):
    """
    JSON Lines 格式化器
    將日誌記錄轉換為 JSON 格式，方便後續解析與分析
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "ts": datetime.utcnow().isoformat() + "Z",  # ISO8601 UTC 時間
            "lvl": record.levelname,
            "svc": record.name,
            "msg": record.getMessage(),
            "module": record.module
        }
        
        # 注入 job_id (如果存在)
        if hasattr(record, 'job_id'):
            log_data["job_id"] = record.job_id
        
        # 注入異常資訊 (如果存在)
        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class JobLogAdapter(logging.LoggerAdapter):
    """
    日誌適配器 - 自動注入 job_id 到日誌記錄
    
    使用範例:
        base_logger = logging.getLogger("worker")
        job_logger = JobLogAdapter(base_logger, {'job_id': 'task-123'})
        job_logger.info("Processing task")  # 輸出會自動包含 [Job: task-123]
    """
    def process(self, msg, kwargs):
        # 修改 Console 輸出訊息（前綴 job_id）
        job_id = self.extra.get('job_id', 'N/A')
        modified_msg = f"[Job: {job_id}] {msg}"
        
        # 將 job_id 注入到 extra，供 JSON 格式化器使用
        if 'extra' not in kwargs:
            kwargs['extra'] = {}
        kwargs['extra']['job_id'] = job_id
        
        return modified_msg, kwargs


def setup_logger(service_name: str, log_level: int = logging.INFO) -> logging.Logger:
    """
    設置 Dual-Channel Structured Logger
    
    Channel 1: Console - 彩色輸出 (人類可讀)
    Channel 2: File - JSON Lines (機器可讀)
    
    Args:
        service_name: 服務名稱 (如 "worker", "backend")
        log_level: 日誌級別 (預設 INFO)
    
    Returns:
        配置好的 Logger 實例
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    logger.handlers.clear()  # 清除現有的 handlers
    
    # ==========================================
    # Channel 1: Console Handler (彩色輸出)
    # ==========================================
    try:
        from colorlog import ColoredFormatter
        
        console_formatter = ColoredFormatter(
            "%(log_color)s[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    except ImportError:
        # Fallback: 如果沒有 colorlog，使用標準格式
        console_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S"
        )
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)
    
    # ==========================================
    # Channel 2: File Handler (JSON Lines)
    # ==========================================
    log_dir = get_project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{service_name}.json.log"
    
    # TimedRotatingFileHandler: 每天午夜輪換日誌檔案
    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=7,  # 保留 7 天
        encoding="utf-8"
    )
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)
    
    logger.info(f"✓ Structured Logger 已啟動: {service_name}")
    logger.info(f"  - Console: 彩色輸出 (Level: {logging.getLevelName(log_level)})")
    logger.info(f"  - File: {log_file} (JSON Lines, 午夜輪換)")
    
    return logger
