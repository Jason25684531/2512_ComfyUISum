"""
Shared Configuration Base
=========================
專案共用的配置參數，避免 Backend 和 Worker 配置重複。
各模組可繼承並擴展特定配置。
"""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse

from shared.security import get_required_env


def get_env_str(name: str, default: str = "") -> str:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip()


def get_env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return int(raw_value)


def get_env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return float(raw_value)


def get_env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value.strip().lower() == "true"


def parse_csv_env(name: str, default: str = "") -> list[str]:
    raw_value = get_env_str(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def parse_key_int_map(name: str) -> dict[str, int]:
    raw_value = get_env_str(name, "")
    timeout_map: dict[str, int] = {}
    if not raw_value:
        return timeout_map

    for item in raw_value.split(","):
        chunk = item.strip()
        if not chunk or "=" not in chunk:
            continue
        key_name, value = chunk.split("=", 1)
        key_name = key_name.strip()
        value = value.strip()
        if not key_name or not value:
            continue
        timeout_map[key_name] = int(value)

    return timeout_map


@dataclass(frozen=True)
class ServiceEndpoint:
    scheme: str
    host: str
    port: int
    base_path: str = ""

    @property
    def http_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.base_path}"

    @property
    def ws_url(self) -> str:
        ws_scheme = "wss" if self.scheme == "https" else "ws"
        return f"{ws_scheme}://{self.host}:{self.port}{self.base_path}/ws"


def resolve_service_endpoint(
    url_env_name: str,
    host_env_name: str,
    port_env_name: str,
    default_host: str,
    default_port: int,
    default_scheme: str = "http",
) -> ServiceEndpoint:
    raw_service_url = get_env_str(url_env_name, "")
    if raw_service_url and "://" not in raw_service_url:
        raw_service_url = f"{default_scheme}://{raw_service_url}"

    configured_host = get_env_str(host_env_name, default_host) or default_host
    configured_port = get_env_int(port_env_name, default_port)

    if raw_service_url:
        parsed_service_url = urlparse(raw_service_url)
        if not parsed_service_url.hostname:
            raise ValueError(f"Invalid service URL for {url_env_name}: {raw_service_url}")
        return ServiceEndpoint(
            scheme=parsed_service_url.scheme or default_scheme,
            host=parsed_service_url.hostname or configured_host,
            port=parsed_service_url.port or configured_port,
            base_path=parsed_service_url.path.rstrip("/"),
        )

    return ServiceEndpoint(
        scheme=default_scheme,
        host=configured_host,
        port=configured_port,
    )


def _should_use_localhost(configured_host: str, docker_service_names: set[str]) -> bool:
    if os.name != "nt":
        return False
    return configured_host.strip().lower() in docker_service_names


def _resolve_redis_endpoint() -> tuple[str, int]:
    configured_host = get_env_str("REDIS_HOST", "localhost") or "localhost"
    configured_port = get_env_int("REDIS_PORT", 6379)

    if _should_use_localhost(configured_host, {"redis", "studio-redis"}):
        return "127.0.0.1", configured_port

    return configured_host, configured_port


def _resolve_db_endpoint() -> tuple[str, int]:
    configured_host = get_env_str("DB_HOST", "localhost") or "localhost"
    configured_port = get_env_int("DB_PORT", 3306)

    if _should_use_localhost(configured_host, {"mysql", "studio-mysql"}):
        if configured_port == 3306:
            configured_port = get_env_int("MYSQL_PORT", 3307)
        return "127.0.0.1", configured_port

    return configured_host, configured_port

# ==========================================
# 專案根目錄
# ==========================================
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ==========================================
# Redis 配置 (共用)
# ==========================================
REDIS_HOST, REDIS_PORT = _resolve_redis_endpoint()
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
JOB_QUEUE = os.getenv("JOB_QUEUE", "job_queue")

# ==========================================
# 資料庫配置 (共用)
# ==========================================
DB_HOST, DB_PORT = _resolve_db_endpoint()
DB_USER = os.getenv("DB_USER", "studio_user")
DB_PASSWORD = get_required_env("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "studio_db")

# ==========================================
# 本地儲存配置 (共用)
# ==========================================
STORAGE_DIR = PROJECT_ROOT / "storage"
STORAGE_INPUT_DIR = STORAGE_DIR / "inputs"
STORAGE_OUTPUT_DIR = STORAGE_DIR / "outputs"

# 確保儲存目錄存在
STORAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Workflow 配置 (共用)
# ==========================================
WORKFLOW_DIR = PROJECT_ROOT / "ComfyUIworkflow"
WORKFLOW_CONFIG_PATH = WORKFLOW_DIR / "config.json"

# ==========================================
# 任務配置 (共用)
# ==========================================
JOB_STATUS_EXPIRE_SECONDS = int(os.getenv("JOB_STATUS_EXPIRE_SECONDS", "3600"))

# ==========================================
# ComfyUI 配置 (共用)
# ==========================================
_default_comfy_root = PROJECT_ROOT.parent / "ComfyUI_windows_portable" / "ComfyUI"
COMFYUI_ROOT = Path(os.getenv("COMFYUI_ROOT", str(_default_comfy_root)))
COMFYUI_MODELS_DIR = COMFYUI_ROOT / "models"


def print_base_config():
    """輸出基礎配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] 共用配置")
    print("=" * 50)
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  REDIS: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  DB: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"  STORAGE_DIR: {STORAGE_DIR}")
    print(f"  WORKFLOW_DIR: {WORKFLOW_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_base_config()
