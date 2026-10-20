"""HTTP routes for upload and job lifecycle operations."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from shared.security import INTERNAL_SERVER_ERROR_MESSAGE


def _runtime():
    return current_app.extensions["backend_runtime"]


def create_blueprint(limiter) -> Blueprint:
    bp = Blueprint("api", __name__)

    @bp.get('/api/queue/me')
    def my_queue():
        payload, code = _runtime().job_service.my_queue(g.user_id)
        if code == 200:
            payload['tempcode'] = g.tempcode
        return jsonify(payload), code

    @bp.get("/api/history")
    def history():
        service = _runtime().job_service
        try:
            offset = int(request.args.get("offset", 0))
            limit = int(request.args.get("limit", service.HISTORY_DEFAULT_LIMIT))
            status = request.args.get("status", "completed")
            if offset < 0 or limit < 1:
                raise ValueError
            elif limit > service.HISTORY_MAX_LIMIT:
                limit = service.HISTORY_MAX_LIMIT
            if status not in {"all", "completed", "running", "failed"}:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid history query"}), 400
        payload, code = service.history(offset, limit, status, getattr(g, "user_id", "") or "")
        return jsonify(payload), code

    @bp.delete("/api/history/<job_id>")
    @limiter.limit("30 per minute")
    def delete_history(job_id: str):
        payload, code = _runtime().job_service.delete_history(job_id, getattr(g, "user_id", "") or "")
        return jsonify(payload), code

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
    @limiter.limit("6 per second")
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
            payload, code = _runtime().job_service.cancel(job_id, g.user_id)
            return jsonify(payload), code
        except Exception:
            _runtime().logger.exception("cancel failed")
            return jsonify({"error": INTERNAL_SERVER_ERROR_MESSAGE}), 500

    return bp
