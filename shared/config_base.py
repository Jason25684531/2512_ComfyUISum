"""
Shared Configuration Base
=========================
專案共用的配置參數，避免 Backend 和 Worker 配置重複。
各模組可繼承並擴展特定配置。
"""

from dataclasses import dataclass
import os
from pathlib import Path

from shared import env_resolution


# 平台名稱（os.name 在 Windows 為 "nt"，統一映射成 env_resolution 預期的字串）
_PLATFORM_NAME = "windows" if os.name == "nt" else "linux"


def get_env_str(name: str, default: str = "") -> str:
    return env_resolution.read_env_str(name, default)


def get_env_int(name: str, default: int) -> int:
    return env_resolution.read_env_int(name, default)


def get_env_float(name: str, default: float) -> float:
    return env_resolution.read_env_float(name, default)


def get_env_bool(name: str, default: bool = False) -> bool:
    return env_resolution.read_env_bool(name, default)


def _expand_path_value(path_value: str) -> str:
    return os.path.expanduser(os.path.expandvars(path_value.strip()))


def resolve_path_setting(env_name: str, default_path: Path, base_path: Path | None = None) -> Path:
    raw_value = get_env_str(env_name, "")
    path = Path(_expand_path_value(raw_value)) if raw_value else Path(default_path)

    if not path.is_absolute():
        resolved_base = (base_path or PROJECT_ROOT).resolve()
        return (resolved_base / path).resolve()

    return path.resolve()


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


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique_paths: list[Path] = []
    seen: set[str] = set()

    for path in paths:
        normalized = str(path)
        key = normalized.lower() if os.name == "nt" else normalized
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)

    return unique_paths


def _build_comfy_root_candidates(project_root: Path) -> list[Path]:
    studio_env = get_env_str("STUDIO_ENV", "").lower()
    candidates: list[Path] = []

    if os.name == "nt" or studio_env == "local":
        candidates.extend([
            Path("C:/ComfyUI_windows_portable/ComfyUI"),
            Path("C:/ComfyUI"),
        ])

    if os.name != "nt" or studio_env == "twcc":
        candidates.extend([
            Path("/opt/comfyui"),
            Path("/opt/ComfyUI"),
        ])

    candidates.extend([
        project_root / "ComfyUI",
        project_root.parent / "ComfyUI_windows_portable" / "ComfyUI",
    ])

    return _dedupe_paths(candidates)


def _resolve_comfy_root(project_root: Path) -> Path:
    for env_name in ("COMFYUI_ROOT", "COMFYUI_PATH"):
        if get_env_str(env_name, ""):
            return resolve_path_setting(env_name, project_root / "ComfyUI", project_root)

    candidates = _build_comfy_root_candidates(project_root)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return candidates[0].resolve()


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
    configured_host = get_env_str(host_env_name, default_host) or default_host
    configured_port = get_env_int(port_env_name, default_port)
    raw_service_url = get_env_str(url_env_name, "")

    if raw_service_url:
        parsed = env_resolution.parse_endpoint_url(
            raw_service_url,
            default_scheme=default_scheme,
            default_host=configured_host,
            default_port=configured_port,
        )
        if parsed is None:
            raise ValueError(f"Invalid service URL for {url_env_name}: {raw_service_url}")
        return ServiceEndpoint(
            scheme=parsed.scheme,
            host=parsed.host,
            port=parsed.port,
            base_path=parsed.base_path,
        )

    return ServiceEndpoint(
        scheme=default_scheme,
        host=configured_host,
        port=configured_port,
    )


def _resolve_redis_endpoint_for(env=None, platform_name: str = _PLATFORM_NAME) -> tuple[str, int]:
    configured_host = env_resolution.read_env_str("REDIS_HOST", "localhost", env=env) or "localhost"
    configured_port = env_resolution.read_env_int("REDIS_PORT", 6379, env=env)
    resolution = env_resolution.resolve_service_host(
        configured_host, configured_port, platform_name=platform_name, aliases={"redis", "studio-redis"}
    )
    return resolution.resolved_host, resolution.port


def _resolve_redis_endpoint() -> tuple[str, int]:
    return _resolve_redis_endpoint_for()

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
# 本地儲存配置 (共用)
# ==========================================
STORAGE_DIR = resolve_path_setting("STORAGE_DIR", PROJECT_ROOT / "storage", PROJECT_ROOT)
STORAGE_INPUT_DIR = resolve_path_setting("STORAGE_INPUT_DIR", STORAGE_DIR / "inputs", PROJECT_ROOT)
STORAGE_OUTPUT_DIR = resolve_path_setting("STORAGE_OUTPUT_DIR", STORAGE_DIR / "outputs", PROJECT_ROOT)

# 確保儲存目錄存在
STORAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# Workflow 配置 (共用)
# ==========================================
WORKFLOW_DIR = resolve_path_setting("WORKFLOW_DIR", PROJECT_ROOT / "ComfyUIworkflow", PROJECT_ROOT)
WORKFLOW_CONFIG_PATH = WORKFLOW_DIR / "config.json"

# ==========================================
# 任務配置 (共用)
# ==========================================
JOB_STATUS_EXPIRE_SECONDS = int(os.getenv("JOB_STATUS_EXPIRE_SECONDS", "3600"))

# ==========================================
# ComfyUI 配置 (共用)
# ==========================================
COMFYUI_ROOT = _resolve_comfy_root(PROJECT_ROOT)
COMFYUI_MODELS_DIR = resolve_path_setting("MODEL_PATH", COMFYUI_ROOT / "models", PROJECT_ROOT)


def print_base_config():
    """輸出基礎配置 (用於除錯)"""
    print("=" * 50)
    print("[Config] 共用配置")
    print("=" * 50)
    print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"  REDIS: {REDIS_HOST}:{REDIS_PORT}")
    print(f"  STORAGE_DIR: {STORAGE_DIR}")
    print(f"  WORKFLOW_DIR: {WORKFLOW_DIR}")
    print(f"  COMFYUI_ROOT: {COMFYUI_ROOT}")
    print(f"  COMFYUI_MODELS_DIR: {COMFYUI_MODELS_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    print_base_config()
