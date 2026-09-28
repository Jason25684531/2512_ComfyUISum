"""Flask composition root for the local Studio runtime."""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config_base import JOB_OBSERVABILITY_ENABLED
from shared.observability_runtime import job_repository, new_request_id
from shared.security import get_flask_debug_mode, sanitize_response_payload
from shared.utils import get_redis_client, load_env, setup_logger

load_env()

from admin_routes import admin_bp
from api_routes import create_blueprint as create_api_blueprint
from config import (
    APP_SECRET_KEY,
    CORS_ALLOWED_ORIGINS,
    FLASK_HOST,
    FLASK_PORT,
    JOB_QUEUE,
    MAX_UPLOAD_SIZE_MB,
    PROJECT_ROOT,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    SESSION_COOKIE_SECURE,
    STORAGE_INPUT_DIR,
    STORAGE_OUTPUT_DIR,
    WARMUP_STATUS_KEY,
)
from job_service import BackendRuntime
from system_routes import create_blueprint as create_system_blueprint


logger = setup_logger("backend", log_level=logging.INFO)
FLASK_DEBUG_MODE = get_flask_debug_mode()
DEFAULT_ALLOWED_CORS_ORIGINS = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
}


def _load_allowed_cors_origins() -> set[str]:
    configured = CORS_ALLOWED_ORIGINS.strip()
    return {origin.strip() for origin in configured.split(",") if origin.strip()} if configured else DEFAULT_ALLOWED_CORS_ORIGINS


ALLOWED_CORS_ORIGINS = _load_allowed_cors_origins()


def _get_cookie_secure_setting() -> bool:
    configured = SESSION_COOKIE_SECURE.strip()
    return configured.lower() == "true" if configured else False


COOKIE_SECURE = _get_cookie_secure_setting()
REDIS_QUEUE_NAME = JOB_QUEUE
UPLOAD_FOLDER = Path(STORAGE_INPUT_DIR)
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
_outbox_last_run = 0.0


try:
    redis_client = get_redis_client(decode_responses=True)
    logger.info("Redis client initialized: %s:%s", REDIS_HOST, REDIS_PORT)
except Exception:
    logger.exception("Redis client initialization failed")
    redis_client = None


class UserIdFilter(logging.Filter):
    def filter(self, record):
        try:
            record.user_id = getattr(g, "user_id", "INIT")
        except (RuntimeError, AttributeError):
            record.user_id = "INIT"
        return True


def _request_origin() -> str | None:
    origin = request.headers.get("Origin")
    return origin if origin in ALLOWED_CORS_ORIGINS else None


def _apply_cors_headers(response):
    origin = _request_origin()
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


def _sanitize_json_response(response):
    if not response.is_json:
        return response
    payload = response.get_json(silent=True)
    if payload is not None:
        response.set_data(json.dumps(sanitize_response_payload(payload), ensure_ascii=False))
    return response


def create_app() -> Flask:
    application = Flask(__name__)
    application.config.update(
        SECRET_KEY=APP_SECRET_KEY,
        MAX_CONTENT_LENGTH=MAX_UPLOAD_SIZE_MB * 1024 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=COOKIE_SECURE,
    )
    application.logger = logger

    limiter = Limiter(
        app=application,
        key_func=get_remote_address,
        storage_uri=None,
        default_limits=["10000 per hour"],
        storage_options={"socket_connect_timeout": 30},
        strategy="fixed-window",
    )
    if REDIS_PASSWORD:
        limiter.storage_uri = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/1"

    runtime = BackendRuntime(
        project_root=PROJECT_ROOT,
        redis_queue_name=REDIS_QUEUE_NAME,
        upload_folder=UPLOAD_FOLDER,
        storage_output_dir=Path(STORAGE_OUTPUT_DIR),
        warmup_status_key=WARMUP_STATUS_KEY,
        logger=logger,
        redis_provider=lambda: redis_client,
        observability_provider=lambda: JOB_OBSERVABILITY_ENABLED,
        repository_provider=job_repository,
    )
    application.extensions["backend_runtime"] = runtime
    application.extensions["limiter"] = limiter

    CORS(
        application,
        origins=sorted(ALLOWED_CORS_ORIGINS),
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        supports_credentials=True,
    )
    application.register_blueprint(admin_bp)
    application.register_blueprint(create_api_blueprint(limiter))
    application.register_blueprint(create_system_blueprint(limiter))

    @application.before_request
    def before_request_handler():
        global _outbox_last_run
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        g.user_id = f"IP#{ip_address}"
        g.request_id = new_request_id(request.headers.get("X-Request-ID"))
        if time.monotonic() - _outbox_last_run > 5:
            _outbox_last_run = time.monotonic()
            runtime.job_service.dispatch_pending_jobs()
        logger.debug("request %s %s", request.method, request.path)

    @application.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            response = application.make_default_options_response()
            return _apply_cors_headers(response)
        return None

    @application.after_request
    def after_request(response):
        response = _sanitize_json_response(response)
        response = _apply_cors_headers(response)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        if hasattr(g, "request_id"):
            response.headers["X-Request-ID"] = g.request_id
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; media-src 'self' data: blob: https:; connect-src 'self' https: ws: wss:; font-src 'self' data:",
        )
        try:
            queue_depth = runtime.redis_client.llen(REDIS_QUEUE_NAME) if runtime.redis_client else 0
            logger.info("%s %s -> %s | queue=%s", request.method, request.path, response.status_code, queue_depth)
        except Exception:
            logger.info("%s %s -> %s", request.method, request.path, response.status_code)
        return response

    @application.errorhandler(413)
    def handle_upload_too_large(_error):
        max_mb = application.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return jsonify({"error": f"File too large. Maximum allowed size is {max_mb}MB"}), 413

    return application


app = create_app()


if __name__ == "__main__":
    logger.info("Backend API starting")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG_MODE, use_reloader=False, threaded=True)
