"""Public-safe error summaries. Raw exceptions stay in service logs."""
from __future__ import annotations

import re

MAX_ERROR_MESSAGE_LENGTH = 1000
COMFYUI_OUTPUT_MISSING = "ComfyUI completed but no image output was found."
COMFYUI_TIMEOUT = "ComfyUI history polling timed out."
COMFYUI_UNAVAILABLE = "ComfyUI is temporarily unavailable."
ENGINE_EXECUTION_FAILED = "Job execution failed."
_SECRET = re.compile(r"(?i)(password|token|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+")
_PATH = re.compile(r"(?:(?:[A-Za-z]:)?[\\/][^\s:]+)+")
_URL_QUERY = re.compile(r"https?://[^\s?]+\?[^\s]+")
_TRACEBACK = re.compile(r"(?is)traceback \(most recent call last\):.*")
_SQL = re.compile(r"(?is)\b(select|insert|update|delete)\b.{0,500}\b(from|into|where)\b")
_BASE64 = re.compile(r"(?<!\w)[A-Za-z0-9+/]{80,}={0,2}")
_PROMPT = re.compile(r"(?i)(negative_?prompt|prompt)\s*[=:]\s*[^,;]+")


def sanitize_error(value: object, fallback: str = "Operation failed") -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = _TRACEBACK.sub("internal error", text)
    text = _SECRET.sub("[redacted]", text)
    text = _URL_QUERY.sub("[redacted-url]", text)
    text = _PATH.sub("[redacted-path]", text)
    text = _SQL.sub("[redacted-query]", text)
    text = _BASE64.sub("[redacted-base64]", text)
    text = _PROMPT.sub("[redacted-prompt]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return (text or fallback)[:MAX_ERROR_MESSAGE_LENGTH]


def classify_comfy_error(value: object) -> str:
    text = str(value or "").lower()
    if "out of memory" in text or "cuda oom" in text:
        return "GPU_OUT_OF_MEMORY"
    if "timeout" in text:
        return "COMFYUI_TIMEOUT"
    if "node" in text:
        return "COMFYUI_NODE_ERROR"
    return "UNKNOWN_ERROR"
