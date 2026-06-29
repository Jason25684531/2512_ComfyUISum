"""
Shared environment resolution primitives
=========================================
單一來源的環境變數讀取、服務主機解析與 ComfyUI URL 解析。

設計原則：
- 純函式 + 可注入的 ``env: Mapping``（預設為 ``os.environ``），方便測試、無 import 副作用。
- ``shared/config_base.py``（連線層）與 ``shared/runtime_contract.py``（診斷層）
  皆委派至此模組，避免同一條規則被實作兩次。
- 不記錄任何祕密值（密碼、金鑰）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.parse import urlparse


def _source(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return env if env is not None else os.environ


def read_env_str(name: str, default: str = "", *, env: Mapping[str, str] | None = None) -> str:
    """讀取字串環境變數並去除前後空白；變數不存在時回傳 ``default``（不去空白）。"""
    raw_value = _source(env).get(name)
    if raw_value is None:
        return default
    return raw_value.strip() if isinstance(raw_value, str) else str(raw_value)


def read_env_int(name: str, default: int, *, env: Mapping[str, str] | None = None) -> int:
    raw_value = _source(env).get(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    return int(str(raw_value).strip())


def read_env_float(name: str, default: float, *, env: Mapping[str, str] | None = None) -> float:
    raw_value = _source(env).get(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    return float(str(raw_value).strip())


def read_env_bool(name: str, default: bool = False, *, env: Mapping[str, str] | None = None) -> bool:
    raw_value = _source(env).get(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    return str(raw_value).strip().lower() == "true"


@dataclass(frozen=True)
class HostResolution:
    """服務主機解析結果。``port`` 原樣帶出，方便呼叫端自行套用各自的 port 規則。"""

    configured_host: str
    resolved_host: str
    port: int
    alias_applied: bool


def is_windows_platform(platform_name: str) -> bool:
    return platform_name.strip().lower().startswith("win")


def resolve_service_host(
    configured_host: str,
    port: int,
    *,
    platform_name: str,
    aliases: Iterable[str],
) -> HostResolution:
    """單一處編碼「Windows 上 docker 服務別名 → 127.0.0.1」規則。

    僅在 Windows 平台且 ``configured_host`` 命中 ``aliases`` 時改寫為 loopback；
    其餘平台一律原樣保留。port 不在此處變更（呼叫端各自處理，例如 MySQL 的 3306→3307）。
    """
    alias_set = {alias.strip().lower() for alias in aliases}
    alias_applied = is_windows_platform(platform_name) and configured_host.strip().lower() in alias_set
    resolved_host = "127.0.0.1" if alias_applied else configured_host
    return HostResolution(
        configured_host=configured_host,
        resolved_host=resolved_host,
        port=port,
        alias_applied=alias_applied,
    )


@dataclass(frozen=True)
class ParsedEndpoint:
    scheme: str
    host: str
    port: int
    base_path: str


def parse_endpoint_url(
    raw_url: str,
    *,
    default_scheme: str,
    default_host: str,
    default_port: int,
) -> ParsedEndpoint | None:
    """解析服務 URL。空字串或無有效 hostname 時回傳 ``None``，由呼叫端決定 fallback。

    若 ``raw_url`` 缺少 scheme，補上 ``default_scheme`` 再解析。
    """
    candidate = (raw_url or "").strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"{default_scheme}://{candidate}"
    parsed = urlparse(candidate)
    if not parsed.hostname:
        return None
    return ParsedEndpoint(
        scheme=parsed.scheme or default_scheme,
        host=parsed.hostname or default_host,
        port=parsed.port or default_port,
        base_path=parsed.path.rstrip("/"),
    )
