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


ENV_FILE_MAP = {
    "local": ".env.local",
    "twcc": ".env.twcc",
    "dev-s3": ".env.dev-s3",
    "default": ".env",
}


def _resolve_env_path(base_path: Path) -> tuple[Path, str]:
    explicit_env_file = os.getenv("STUDIO_ENV_FILE", "").strip()
    explicit_env_name = os.getenv("STUDIO_ENV", "").strip().lower()

    if explicit_env_file:
        env_path = Path(explicit_env_file)
        if not env_path.is_absolute():
            env_path = (base_path / env_path).resolve()
        return env_path, f"STUDIO_ENV_FILE={explicit_env_file}"

    if explicit_env_name:
        mapped_file = ENV_FILE_MAP.get(explicit_env_name)
        if mapped_file is None:
            supported = ", ".join(sorted(ENV_FILE_MAP))
            raise ValueError(
                f"Unsupported STUDIO_ENV='{explicit_env_name}'. Supported values: {supported}"
            )
        return (base_path / mapped_file).resolve(), f"STUDIO_ENV={explicit_env_name}"

    local_env_path = (base_path / ".env.local").resolve()
    legacy_env_path = (base_path / ".env").resolve()

    if local_env_path.exists() and legacy_env_path.exists():
        raise RuntimeError(
            "Ambiguous environment selection: both .env.local and .env exist. "
            "Set STUDIO_ENV_FILE or STUDIO_ENV explicitly."
        )

    if local_env_path.exists():
        return local_env_path, "auto-detect .env.local"

    return legacy_env_path, "default .env"


def load_env(base_path: Path = None) -> None:
    """
    自動載入專案根目錄的環境檔案。
    優先順序：STUDIO_ENV_FILE -> STUDIO_ENV -> .env.local -> .env
    
    Args:
        base_path: 基礎路徑，預設為呼叫檔案的上上層目錄
    """
    if base_path is None:
        # 預設使用專案根目錄
        base_path = Path(__file__).parent.parent

    base_path = base_path.resolve()
    env_path, source = _resolve_env_path(base_path)

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"[env] Loaded env file via {source}: {env_path}")
    else:
        if source.startswith("STUDIO_ENV"):
            raise FileNotFoundError(f"[env] Missing explicit env file: {env_path}")
        print(f"[env] Missing env file via {source}: {env_path}")


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
        print("⚠️ colorlog 未安裝，使用標準格式。建議安裝: pip install colorlog")
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


# ==========================================
# Phase 10: Redis Connection Utility
# ==========================================

def get_redis_client(decode_responses: bool = True, max_retries: int = 10,
                     initial_delay: float = 2.0, max_delay: float = 60.0):
    """
    取得 Redis 客戶端連接 (統一介面，帶指數退避重試)
    
    Args:
        decode_responses: 是否自動解碼響應為字串 (預設 True)
        max_retries: 最大重試次數 (預設 10)
        initial_delay: 初始重試延遲秒數 (預設 2.0)
        max_delay: 最大重試延遲秒數 (預設 60.0)
    
    Returns:
        Redis 客戶端實例
        
    Raises:
        Exception: 所有重試都失敗時拋出最後一次的異常
    """
    import time
    from redis import Redis
    from shared.config_base import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

    retry_override = os.getenv("REDIS_CONNECT_RETRIES")
    if retry_override is not None:
        max_retries = max(0, int(retry_override))

    initial_delay_override = os.getenv("REDIS_CONNECT_INITIAL_DELAY")
    if initial_delay_override is not None:
        initial_delay = max(0.0, float(initial_delay_override))

    max_delay_override = os.getenv("REDIS_CONNECT_MAX_DELAY")
    if max_delay_override is not None:
        max_delay = max(0.0, float(max_delay_override))
    
    last_error = None
    delay = initial_delay
    
    for attempt in range(max_retries + 1):
        try:
            client = Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            # 測試連接
            client.ping()
            if attempt > 0:
                logging.getLogger(__name__).info(
                    f"✅ Redis 連接成功 (第 {attempt + 1} 次嘗試，"
                    f"總等待 {initial_delay * (2**attempt - 1):.1f}s)"
                )
            return client
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logging.getLogger(__name__).warning(
                    f"⚠️ Redis 連接失敗 ({attempt + 1}/{max_retries + 1})，"
                    f"{delay:.1f}s 後重試: {e}"
                )
                time.sleep(delay)
                delay = min(delay * 2, max_delay)  # 指數退避，不超過上限
            else:
                logging.getLogger(__name__).error(
                    f"❌ Redis 連接失敗（已重試 {max_retries} 次）: {e}"
                )
    
    raise Exception(f"Redis 連接失敗 ({REDIS_HOST}:{REDIS_PORT})，"
                    f"已重試 {max_retries} 次: {last_error}")
