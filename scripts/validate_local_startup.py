"""本地啟動驗證腳本（Win ComfyUI + WSL2 Docker 拓撲）

驗證兩個服務是否可達：
  1. ComfyUI  — GET http://<COMFYUI_SERVER_URL>/system_stats
  2. Redis    — PING via redis-py

全部 OK → exit 0
任一 FAIL → exit 1

I2-012 安全規範：密碼值不印到輸出，只顯示可達/不可達結果。
"""

from __future__ import annotations

import os
import sys
import urllib.request
import urllib.error


def _load_env_file(path: str) -> None:
    """讀取 key=value 格式的 env 檔，僅填入 os.environ 中尚未存在的 key。"""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


# 自動載入專案根目錄的 .env.local（shell 未 source 時也能正常讀到密碼）
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_load_env_file(os.path.join(_root, ".env.local"))


def _check_comfyui(server_url: str) -> tuple[bool, str]:
    url = server_url.rstrip("/") + "/system_stats"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                return True, f"HTTP {resp.status}"
            return False, f"HTTP {resp.status}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)
    except Exception as exc:
        return False, str(exc)


def _check_redis(host: str, port: int, password: str) -> tuple[bool, str]:
    try:
        import redis as redis_lib
        client = redis_lib.Redis(host=host, port=port, password=password or None, socket_timeout=5)
        client.ping()
        return True, "PONG"
    except ImportError:
        # redis-py 未安裝時退化為 socket 連線測試
        import socket
        try:
            with socket.create_connection((host, port), timeout=5):
                return True, "TCP OK (redis-py not installed)"
        except Exception as exc:
            return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    comfyui_url = os.environ.get("COMFYUI_SERVER_URL", "http://host.docker.internal:8188")
    redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    redis_pw = os.environ.get("REDIS_PASSWORD", "")

    results = []

    ok, detail = _check_comfyui(comfyui_url)
    results.append(("ComfyUI", comfyui_url, ok, detail))

    ok, detail = _check_redis(redis_host, redis_port, redis_pw)
    results.append(("Redis", f"{redis_host}:{redis_port}", ok, detail))

    col_w = [8, 40, 6, 30]
    header = f"{'Service':<{col_w[0]}}  {'Endpoint':<{col_w[1]}}  {'Status':<{col_w[2]}}  Detail"
    print(header)
    print("-" * (sum(col_w) + 8))
    all_ok = True
    for name, endpoint, ok, detail in results:
        status = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"{name:<{col_w[0]}}  {endpoint:<{col_w[1]}}  {status:<{col_w[2]}}  {detail}")

    print()
    if all_ok:
        print("All services reachable. Local startup OK.")
        return 0
    else:
        print("One or more services unreachable. Check the above output.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
