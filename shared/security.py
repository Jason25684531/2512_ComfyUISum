"""
Shared security helpers for API-safe serialization and runtime configuration.
"""

from __future__ import annotations

import os
from typing import Any

from markupsafe import escape

INTERNAL_SERVER_ERROR_MESSAGE = "Internal server error occurred"
INVALID_INPUT_MESSAGE = "Invalid input data"
OPERATION_FAILED_MESSAGE = "Operation failed"


def sanitize_response_payload(payload: Any) -> Any:
    """Recursively HTML-escape string values for JSON responses."""
    if isinstance(payload, dict):
        return {
            key: sanitize_response_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [sanitize_response_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [sanitize_response_payload(item) for item in payload]
    if isinstance(payload, str):
        return str(escape(payload))
    return payload


def get_required_env(name: str) -> str:
    """Return a required environment variable or fail fast."""
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is not set")
    return value.strip()


def get_flask_debug_mode() -> bool:
    """Derive Flask debug mode from explicit flags or development environment."""
    flask_debug = os.getenv("FLASK_DEBUG")
    if flask_debug is not None:
        return flask_debug.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("FLASK_ENV", "").strip().lower() == "development"


def get_public_error_message(message: str | None = None) -> str:
    """Collapse dynamic internal failures into a public-safe static message."""
    return OPERATION_FAILED_MESSAGE if message else ""