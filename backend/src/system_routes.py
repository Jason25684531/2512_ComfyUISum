"""System, runtime-config, output, and frontend routes."""
from __future__ import annotations

import html
import mimetypes
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, send_from_directory
from werkzeug.utils import secure_filename

from config import COMFYUI_CHECKPOINTS_DIR, COMFYUI_UNET_DIR
from frontend_compat import resolve_legacy_redirect, resolve_root_document
from shared.path_utils import InvalidStoragePathError, resolve_storage_path
from shared.runtime_services import build_runtime_config_payload, build_runtime_diagnostics


def _runtime():
    return current_app.extensions["backend_runtime"]


def create_blueprint(limiter) -> Blueprint:
    bp = Blueprint("system", __name__)

    @bp.get("/health")
    @bp.get("/api/health")
    def health():
        runtime = _runtime()
        redis_status = "unavailable"
        if runtime.redis_client:
            try:
                redis_status = "healthy" if runtime.redis_client.ping() else "unavailable"
            except Exception:
                redis_status = "unavailable"
        worker_status = "offline"
        warnings = []
        warmup = _get_worker_warmup_snapshot(runtime)
        if runtime.redis_client:
            try:
                worker_status = "online" if runtime.redis_client.get("worker:heartbeat") else "offline"
            except Exception:
                runtime.logger.warning("worker heartbeat unavailable")
        try:
            with runtime.repository_provider().transaction() as cursor:
                cursor.execute("SELECT 1")
            mysql_status = "healthy"
        except Exception:
            mysql_status = "unavailable"
        overall = "ok" if redis_status == "healthy" and mysql_status == "healthy" else "degraded"
        if worker_status == "offline":
            warnings.append("Worker heartbeat unavailable")
        if warmup["warmup_status"] == "running":
            warnings.append("GPU warmup in progress")
        if warmup["warmup_status"] == "failed" and warmup["warmup_last_error"]:
            warnings.append(warmup["warmup_last_error"])
        diagnostics = build_runtime_diagnostics(
            project_root=runtime.project_root,
            redis_status=redis_status,
            mysql_status=mysql_status,
            worker_status=worker_status,
        )
        return jsonify({"status": overall, "redis": redis_status, "mysql": mysql_status, "worker": worker_status, **diagnostics, **warmup, "warnings": warnings}), 200

    @bp.get("/api/runtime-config")
    def runtime_config():
        try:
            return jsonify(build_runtime_config_payload(_runtime().project_root)), 200
        except Exception:
            _runtime().logger.exception("runtime-config failed")
            return jsonify({"error": "Internal server error"}), 500

    @bp.get("/api/models")
    def get_models():
        runtime = _runtime()
        models, unet_models = [], []
        try:
            if COMFYUI_CHECKPOINTS_DIR.exists():
                models = [str(path.relative_to(COMFYUI_CHECKPOINTS_DIR)) for path in COMFYUI_CHECKPOINTS_DIR.rglob("*") if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt"}]
            if COMFYUI_UNET_DIR.exists():
                unet_models = [str(path.relative_to(COMFYUI_UNET_DIR)) for path in COMFYUI_UNET_DIR.rglob("*") if path.is_file() and path.suffix.lower() in {".safetensors", ".ckpt", ".pt"}]
        except Exception:
            runtime.logger.exception("model listing failed")
        if not models and not unet_models:
            models = ["default_model.safetensors"]
            unet_models = ["z-image/z-image-turbo-fp8-e4m3fn.safetensors"]
        return jsonify({"models": sorted(models), "unet_models": sorted(unet_models)}), 200

    @bp.get("/api/metrics")
    @limiter.limit("2 per second")
    def metrics():
        runtime = _runtime()
        redis_client = runtime.redis_client
        if redis_client is None:
            return jsonify({"error": "Redis service unavailable"}), 503
        try:
            queue_length = redis_client.llen(runtime.redis_queue_name)
            worker_status = "online" if redis_client.get("worker:heartbeat") else "offline"
            active_jobs = sum(1 for key in redis_client.keys("job:status:*") if redis_client.hget(key, "status") == "processing")
            diagnostics = build_runtime_diagnostics(
                project_root=runtime.project_root,
                redis_status="healthy",
                mysql_status="n/a",
                worker_status=worker_status,
            )
            return jsonify({"queue_length": queue_length, "worker_status": worker_status, "active_jobs": active_jobs, **diagnostics, **_get_worker_warmup_snapshot(runtime)}), 200
        except Exception:
            runtime.logger.exception("metrics failed")
            return jsonify({"error": "Internal server error"}), 500

    @bp.get("/outputs/<path:filename>")
    def serve_output(filename: str):
        runtime = _runtime()
        safe_filename = secure_filename(filename)
        if not safe_filename:
            return abort(400)
        outputs_dir = str(runtime.storage_output_dir)
        try:
            file_path = resolve_storage_path(outputs_dir, safe_filename)
        except InvalidStoragePathError:
            return abort(403)
        if not file_path.is_file():
            return abort(404)
        mimetype, _ = mimetypes.guess_type(file_path)
        if mimetype is None:
            mimetype = {
                ".mp4": "video/mp4", ".webm": "video/webm", ".avi": "video/x-msvideo", ".mov": "video/quicktime",
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
            }.get(Path(safe_filename).suffix.lower(), "application/octet-stream")
        return send_from_directory(outputs_dir, safe_filename, mimetype=mimetype)

    @bp.get("/")
    def serve_index():
        frontend_dir = _runtime().project_root / "frontend"
        target = resolve_root_document(frontend_dir)
        if (frontend_dir / target).exists():
            return send_from_directory(frontend_dir, target)
        return jsonify({"error": "Frontend not found"}), 404

    @bp.get("/<path:path>")
    def serve_static(path: str):
        runtime = _runtime()
        if path.startswith(("api/", "health", "outputs/")):
            return jsonify({"error": "Not found"}), 404
        frontend_dir = runtime.project_root / "frontend"
        redirect_target = resolve_legacy_redirect(path)
        if redirect_target:
            return redirect(redirect_target, code=302)
        if path == "favicon.ico":
            favicon = frontend_dir / "favicon.ico"
            logo = frontend_dir / "image" / "LOGO.png"
            if favicon.is_file():
                return send_from_directory(frontend_dir, "favicon.ico")
            if logo.is_file():
                return send_from_directory(logo.parent, logo.name, mimetype="image/png")
            return "", 204
        file_path = (frontend_dir / path).resolve()
        if not file_path.is_relative_to(frontend_dir.resolve()):
            return jsonify({"error": "Forbidden"}), 403
        if file_path.is_file():
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "dashboard.html")

    return bp


def _get_worker_warmup_snapshot(runtime) -> dict:
    snapshot = {
        "warmup_status": "unknown", "warmup_profile": "", "warmup_last_error": "", "warmup_mode": "",
        "warmup_started_at": "", "warmup_completed_at": "", "warmup_updated_at": "", "warmup_enabled": False,
        "warmup_terminal": False, "warmup_timeout_seconds": 0,
    }
    if not runtime.redis_client:
        return snapshot
    try:
        raw = runtime.redis_client.hgetall(runtime.warmup_status_key) or {}
    except Exception:
        snapshot["warmup_last_error"] = "Warmup status unavailable"
        return snapshot
    if not raw:
        return snapshot
    snapshot.update({
        "warmup_status": html.escape(str(raw.get("status", "unknown"))),
        "warmup_profile": html.escape(str(raw.get("profile", ""))),
        "warmup_last_error": html.escape(str(raw.get("last_error", ""))),
        "warmup_mode": html.escape(str(raw.get("mode", ""))),
        "warmup_started_at": html.escape(str(raw.get("started_at", ""))),
        "warmup_completed_at": html.escape(str(raw.get("completed_at", ""))),
        "warmup_updated_at": html.escape(str(raw.get("updated_at", ""))),
        "warmup_enabled": _parse_bool(raw.get("enabled", "false")),
        "warmup_terminal": _parse_bool(raw.get("terminal", "false")),
        "warmup_timeout_seconds": _parse_int(raw.get("timeout_seconds", 0)),
    })
    return snapshot


def _parse_bool(value) -> bool:
    return str(value).strip().lower() == "true"


def _parse_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
