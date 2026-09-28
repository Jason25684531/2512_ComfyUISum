"""HTTP routes for upload and job lifecycle operations."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from shared.security import INTERNAL_SERVER_ERROR_MESSAGE


def _runtime():
    return current_app.extensions["backend_runtime"]


def create_blueprint(limiter) -> Blueprint:
    bp = Blueprint("api", __name__)

    @bp.post("/api/upload")
    @limiter.limit("30 per minute")
    def upload_audio():
        try:
            payload, status = _runtime().job_service.save_upload(request.files.get("file"))
            return jsonify(payload), status
        except Exception:
            _runtime().logger.exception("upload failed")
            return jsonify({"error": INTERNAL_SERVER_ERROR_MESSAGE}), 500

    @bp.route("/api/generate", methods=["POST", "OPTIONS"])
    @limiter.limit("10 per minute")
    def generate():
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Missing JSON data"}), 400
            payload, status = _runtime().job_service.submit(
                data,
                request_id=getattr(g, "request_id", ""),
                user_label=getattr(g, "user_id", "anonymous") or "anonymous",
            )
            return jsonify(payload), status
        except Exception:
            _runtime().logger.exception("generate failed")
            return jsonify({"error": INTERNAL_SERVER_ERROR_MESSAGE}), 500

    @bp.get("/api/status/<job_id>")
    @limiter.limit("2 per second")
    def status(job_id: str):
        try:
            payload, code = _runtime().job_service.status(job_id)
            return jsonify(payload), code
        except Exception:
            _runtime().logger.exception("status failed")
            return jsonify({"error": INTERNAL_SERVER_ERROR_MESSAGE}), 500

    @bp.post("/api/cancel/<job_id>")
    def cancel_job(job_id: str):
        try:
            payload, code = _runtime().job_service.cancel(job_id)
            return jsonify(payload), code
        except Exception:
            _runtime().logger.exception("cancel failed")
            return jsonify({"error": INTERNAL_SERVER_ERROR_MESSAGE}), 500

    return bp
