"""Read-only readiness check for the canonical local Compose + ComfyUI stack."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


def _check_backend(base_url: str) -> list[tuple[str, bool]]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/health", timeout=5) as response:
            payload = json.load(response)
        return [
            ("Backend", payload.get("status") == "ok"),
            ("Redis", payload.get("redis") == "healthy"),
            ("MySQL", payload.get("mysql") == "healthy"),
            ("Worker", payload.get("worker") == "online"),
        ]
    except (OSError, ValueError, AttributeError):
        return [(name, False) for name in ("Backend", "Redis", "MySQL", "Worker")]


def _check_comfyui(server_url: str) -> bool:
    try:
        with urllib.request.urlopen(server_url.rstrip("/") + "/system_stats", timeout=5) as response:
            payload = json.load(response)
        return isinstance(payload, dict) and isinstance(payload.get("system"), dict)
    except (OSError, ValueError):
        return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from shared.utils import load_env

    load_env()
    from shared.config_base import get_env_int, resolve_service_endpoint

    comfyui = resolve_service_endpoint(
        "COMFYUI_SERVER_URL", "COMFYUI_HOST", "COMFYUI_PORT", "127.0.0.1", 8188,
    )
    # Docker's special host name is for container callers; this CLI also runs on Windows.
    if sys.platform == "win32" and comfyui.host == "host.docker.internal":
        from dataclasses import replace

        comfyui = replace(comfyui, host="127.0.0.1")
    results = _check_backend(f"http://127.0.0.1:{get_env_int('FLASK_PORT', 5000)}")
    results.append(("ComfyUI", _check_comfyui(comfyui.http_url)))
    for service, ok in results:
        print(f"{service}: {'OK' if ok else 'FAIL'}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
