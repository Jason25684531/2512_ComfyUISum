import os
import requests
from flask import Blueprint, jsonify, request, send_from_directory
from pathlib import Path

from admin_queries import AdminQueries
from shared.observability_runtime import job_repository

admin_bp = Blueprint("admin_observability", __name__)


def _queries():
    return AdminQueries(job_repository())


@admin_bp.get("/api/admin/jobs")
def jobs():
    try:
        return jsonify(_queries().jobs(request.args))
    except ValueError as exc:
        return jsonify({"error": str(exc), "output_encoded": False}), 400
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/jobs/<job_id>")
def job_detail(job_id):
    try:
        repo = job_repository(); job = repo.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found", "output_encoded": False}), 404
        return jsonify({"job": job, "events": repo.list_events(job_id), "outputs": repo.list_outputs(job_id), "output_encoded": False})
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/metrics/summary")
def summary():
    try:
        return jsonify(_queries().summary(request.args))
    except ValueError as exc:
        return jsonify({"error": str(exc), "output_encoded": False}), 400
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/metrics/timeseries")
def timeseries():
    try:
        return jsonify(_queries().timeseries(request.args))
    except ValueError as exc:
        return jsonify({"error": str(exc), "output_encoded": False}), 400
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/errors")
def errors():
    try:
        return jsonify(_queries().grouped(request.args, "error_code"))
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/workflows")
def workflows():
    try:
        return jsonify(_queries().grouped(request.args, "workflow_id"))
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/workers")
def workers():
    try:
        return jsonify(_queries().grouped(request.args, "worker_id"))
    except Exception:
        return jsonify({"error": "Observability data unavailable", "output_encoded": False}), 503


@admin_bp.get("/api/admin/system/health")
def system_health():
    try:
        with job_repository().transaction() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        mysql = "healthy"
    except Exception:
        mysql = "unavailable"
    try:
        from shared.utils import get_redis_client
        client = get_redis_client(decode_responses=True)
        redis = "healthy" if client.ping() else "unavailable"
        comfy_snapshot = client.hgetall('comfyui:health') or {}
    except Exception:
        redis, comfy_snapshot = "unavailable", {}
    if comfy_snapshot:
        comfyui = comfy_snapshot.get('status', 'unknown')
    else:
        try:
            url = os.getenv("COMFY_HTTP_URL", "http://127.0.0.1:8188").rstrip("/") + "/system_stats"
            comfyui = "healthy" if requests.get(url, timeout=1).status_code == 200 else "unavailable"
        except Exception:
            comfyui = "unavailable"
    return jsonify({"mysql": mysql, "redis": redis, "comfyui": comfyui,
                    "status": "healthy" if all(x == "healthy" for x in (mysql, redis, comfyui)) else "degraded",
                    "output_encoded": False})


@admin_bp.get("/admin")
@admin_bp.get("/admin/jobs")
@admin_bp.get("/admin/jobs/<job_id>")
def dashboard(job_id=None):
    return send_from_directory(Path(__file__).resolve().parents[2] / "frontend" / "admin", "index.html")
