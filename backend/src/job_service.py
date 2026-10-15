"""Backend job orchestration without Flask route ownership."""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from markupsafe import escape
from redis import RedisError
from werkzeug.utils import secure_filename

from shared.elements_data_validator import ElementsDataValidator
from shared.job_contracts import JobStatus, iso_utc, public_status
from shared.job_tracker import JobTracker
from shared.observability_runtime import job_repository
from shared.runtime_services import build_job_data, resolve_workflow_request


class BackendRuntime:
    """Composition-owned runtime dependencies shared by route modules."""

    def __init__(
        self,
        *,
        project_root: Path,
        redis_queue_name: str,
        upload_folder: Path,
        storage_output_dir: Path,
        warmup_status_key: str,
        logger: logging.Logger,
        redis_provider: Callable[[], Any],
        observability_provider: Callable[[], bool],
        repository_provider: Callable[[], Any] = job_repository,
    ) -> None:
        self.project_root = project_root
        self.redis_queue_name = redis_queue_name
        self.upload_folder = upload_folder
        self.storage_output_dir = storage_output_dir
        self.warmup_status_key = warmup_status_key
        self.logger = logger
        self._redis_provider = redis_provider
        self._observability_provider = observability_provider
        self.repository_provider = repository_provider
        self.outbox_lock = threading.Lock()
        self.job_service = JobService(self)

    @property
    def redis_client(self):
        return self._redis_provider()

    @property
    def job_observability_enabled(self) -> bool:
        return bool(self._observability_provider())


def _normalize_catalog_inputs(entry, data: dict[str, Any], prompt: str) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    extra = data.get("extra_params") or {}
    if not isinstance(extra, dict):
        return {}, {}, "extra_params must be an object"
    raw_images = data.get("images") or {}
    if isinstance(raw_images, list) and entry.input_types.get("images") == "multi-image":
        images = {"images": raw_images}
    elif isinstance(raw_images, dict):
        images = raw_images
    else:
        return {}, {}, "invalid images"
    normalized_images = {
        key: value for key, value in images.items()
        if key in getattr(entry, "image_map", {}) and value
    }

    normalized: dict[str, Any] = {}
    required = set(entry.required_inputs)
    fields = required | set(entry.optional_inputs)
    for name in fields:
        input_type = entry.input_types.get(name, "text")
        if input_type in {"image", "multi-image"}:
            value = images.get(name)
        elif name == "prompt":
            value = prompt
        else:
            value = extra.get(name, data.get(name, entry.defaults.get(name)))

        if name in required and value in (None, "", []):
            return {}, {}, f"{name} is required"
        if input_type == "multi-image":
            value = value or []
            if not isinstance(value, list) or any(not isinstance(image, str) or not image for image in value):
                return {}, {}, f"invalid {name}"
            if len(value) > entry.max_items[name]:
                return {}, {}, f"too many {name} (max {entry.max_items[name]})"
            normalized_images.update({f"{name}.{index}": image for index, image in enumerate(value)})
            continue
        if value is None or value == "":
            continue
        if input_type == "image" and not isinstance(value, str):
            return {}, {}, f"invalid {name}"

        choices = entry.choices.get(name)
        if choices:
            matched = next((choice for choice in choices if value == choice or str(value) == str(choice)), None)
            if matched is None:
                return {}, {}, f"invalid {name}"
            value = matched
        elif input_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return {}, {}, f"invalid {name}"
            if name == "seed" and (not isinstance(value, int) or not -1 <= value <= 2**64 - 1):
                return {}, {}, "invalid seed"

        if name != "prompt" and input_type not in {"image", "multi-image"}:
            normalized[name] = value

    return normalized, normalized_images, None


class JobService:
    def __init__(self, runtime: BackendRuntime) -> None:
        self.runtime = runtime

    @property
    def logger(self):
        return self.runtime.logger

    def dispatch_pending_jobs(self) -> None:
        """Replay committed dispatch intents; worker CAS stops duplicate delivery."""
        redis_client = self.runtime.redis_client
        if not redis_client or not self.runtime.outbox_lock.acquire(blocking=False):
            return
        try:
            repo = self.runtime.repository_provider()
            tracker = JobTracker(self.runtime.repository_provider())
            for dispatch in repo.pending_dispatches(20):
                try:
                    job = repo.get_job(dispatch["job_id"]) or {}
                    if job.get("status") == JobStatus.CREATED.value:
                        if not tracker.transition(dispatch["job_id"], JobStatus.CREATED, JobStatus.QUEUED):
                            continue
                    elif job.get("status") != JobStatus.QUEUED.value:
                        repo.mark_dispatched(dispatch["job_id"], iso_utc())
                        continue
                    tracker.event(dispatch["job_id"], "job_queued", resulting_status="queued")
                    redis_client.rpush(self.runtime.redis_queue_name, json.dumps(dispatch["payload"], ensure_ascii=False))
                    repo.mark_dispatched(dispatch["job_id"], iso_utc())
                except Exception as exc:
                    repo.mark_dispatched(dispatch["job_id"], iso_utc(), str(exc)[:500])
        finally:
            self.runtime.outbox_lock.release()

    def save_upload(self, file_storage) -> tuple[dict[str, Any], int]:
        if file_storage is None:
            return {"error": "No file provided"}, 400
        if file_storage.filename == "":
            return {"error": "No file selected"}, 400

        original_filename = secure_filename(file_storage.filename)
        file_ext = os.path.splitext(original_filename)[1].lower()
        allowed_audio = {".wav", ".mp3"}
        allowed_video = {".mp4", ".mov"}
        allowed = allowed_audio | allowed_video
        if file_ext not in allowed:
            return {"error": f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}"}, 400

        unique_id = str(uuid.uuid4())[:12]
        prefix = "video" if file_ext in allowed_video else "audio"
        safe_filename = secure_filename(f"{prefix}_{unique_id}{file_ext}")
        file_path = self.runtime.upload_folder / safe_filename
        try:
            file_storage.save(str(file_path))
        except PermissionError:
            return {"error": "Permission denied when saving file"}, 500
        except FileNotFoundError:
            return {"error": "Upload directory not found"}, 500
        return {"filename": safe_filename, "original_name": escape(str(file_storage.filename))}, 200

    def submit(self, data: dict[str, Any], *, request_id: str, user_label: str) -> tuple[dict[str, Any], int]:
        if not isinstance(data.get("prompt", ""), str):
            return {"error": "prompt must be a string"}, 400
        prompt = data.get("prompt", "").strip()
        prompts = data.get("prompts", [])
        try:
            workflow_resolution = resolve_workflow_request(self.runtime.project_root, data.get("workflow", "text_to_image"))
        except KeyError:
            return {"error": "Unsupported workflow"}, 400

        workflow = workflow_resolution.workflow_id
        catalog_extra_params, catalog_images, catalog_input_error = _normalize_catalog_inputs(
            workflow_resolution.entry, data, prompt
        )
        if catalog_input_error:
            return {"error": catalog_input_error}, 400
        data = {**data, "images": catalog_images}
        if "seed" in catalog_extra_params:
            data["seed"] = catalog_extra_params.pop("seed")
        if workflow_resolution.alias_hit:
            self.logger.info(
                "workflow alias normalized: requested=%s canonical=%s source=%s",
                workflow_resolution.requested_id,
                workflow_resolution.workflow_id,
                workflow_resolution.source,
            )
        if len(prompt) > 1000:
            return {"error": "Prompt exceeds maximum length of 1000 characters"}, 400
        if prompts:
            if not isinstance(prompts, list):
                return {"error": "prompts must be a list"}, 400
            if len(prompts) > 10:
                return {"error": "Too many prompts (max 10)"}, 400
            if any(len(str(item)) > 1000 for item in prompts):
                return {"error": "Individual prompt exceeds maximum length"}, 400
        if workflow == "text_to_image" and not prompt:
            return {"error": "prompt is required for text_to_image"}, 400

        retake_start = data.get("retake_start", 0)
        retake_end = data.get("retake_end", 0)
        video_filename = data.get("video", "")
        if workflow == "ltx_retake_v2v":
            if not video_filename:
                return {"error": "video is required for ltx_retake_v2v"}, 400
            video_path = self.runtime.upload_folder / secure_filename(str(video_filename))
            if not video_path.exists():
                return {"error": "uploaded video not found, please re-upload"}, 400
            if not prompt:
                return {"error": "prompt is required for ltx_retake_v2v"}, 400
            try:
                retake_start = float(retake_start)
                retake_end = float(retake_end)
            except (TypeError, ValueError):
                return {"error": "retake_start/retake_end must be numbers"}, 400
            if retake_start < 0 or retake_end <= retake_start:
                return {"error": "retake_start must be >= 0 and less than retake_end"}, 400

        extra_params: dict[str, Any] = {}
        video_mode = str(data.get("video_mode") or "").strip().lower()
        entry = workflow_resolution.entry
        if {"first_frame", "last_frame"}.issubset(entry.input_types):
            first = bool(catalog_images.get("first_frame"))
            last = bool(catalog_images.get("last_frame"))
            video_mode = "fl2v" if first and last else "i2v" if first else "l2v" if last else "t2v"
            if video_mode not in entry.video_mode_map:
                return {"error": "Unsupported frame combination"}, 400
        if workflow == "ltx_retake_v2v":
            extra_params = {"retake_start": retake_start, "retake_end": retake_end}

        if workflow == "ideogram4_regional_t2i":
            if not prompt:
                return {"error": "prompt is required for ideogram4_regional_t2i"}, 400
            try:
                elements_data = ElementsDataValidator.validate(data.get("elements_data") or "[]")
            except ValueError:
                return {"error": "invalid elements_data"}, 400
            try:
                width = int(data.get("width", 1080))
                height = int(data.get("height", 1920))
            except (TypeError, ValueError):
                return {"error": "width and height must be integers"}, 400
            if not (256 <= width <= 4096) or not (256 <= height <= 4096):
                return {"error": "width and height must be between 256 and 4096"}, 400
            extra_params = {"elements_data": elements_data, "width": width, "height": height}
            for field in ("background", "style", "aesthetics", "lighting", "medium", "style_palette_data"):
                value = data.get(field)
                if value is None:
                    continue
                if not isinstance(value, str) or len(value) > 2000:
                    return {"error": f"{field} must be a string up to 2000 characters"}, 400
                extra_params[field] = value

        if workflow == "multi_angle":
            input_filename = (data.get("images") or {}).get("input")
            if not input_filename:
                return {"error": "input image is required for multi_angle"}, 400
            for field, minimum, maximum, integer_only in (
                ("horizontal_angle", 0, 360, True),
                ("vertical_angle", -30, 60, True),
                ("zoom", 0.0, 10.0, False),
            ):
                if field not in data:
                    continue
                raw = data[field]
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    return {"error": f"{field} must be a number within range"}, 400
                if integer_only and not isinstance(raw, int):
                    return {"error": f"{field} must be a number within range"}, 400
                value = raw if integer_only else float(raw)
                if value < minimum or value > maximum:
                    return {"error": f"{field} must be within range"}, 400
                extra_params[field] = value

        if workflow in {"ltx_i2v", "ltx_flf"}:
            images = data.get("images") or {}
            if workflow == "ltx_i2v":
                video_mode = video_mode or ("i2v" if images.get("input") else "t2v")
                if video_mode not in {"t2v", "i2v"}:
                    return {"error": "video_mode must be t2v or i2v"}, 400
                if video_mode == "i2v" and not images.get("input"):
                    return {"error": "input image is required for i2v"}, 400
                if video_mode == "t2v" and images.get("input"):
                    return {"error": "t2v does not accept an image"}, 400
            else:
                video_mode = ""
                for field in ("first_frame", "last_frame"):
                    if not images.get(field):
                        return {"error": f"{field} image is required"}, 400
            for field, minimum, maximum in (("video_width", 512, 1920), ("video_height", 512, 1920), ("video_duration", 1, 10)):
                if field not in data:
                    continue
                raw = data[field]
                if isinstance(raw, bool) or isinstance(raw, float):
                    return {"error": f"{field} must be an integer between {minimum} and {maximum}"}, 400
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    return {"error": f"{field} must be an integer between {minimum} and {maximum}"}, 400
                if not minimum <= value <= maximum:
                    return {"error": f"{field} must be between {minimum} and {maximum}"}, 400
                extra_params[field] = value

        extra_params.update(catalog_extra_params)

        audio_value = data.get("audio", "")
        if audio_value and isinstance(audio_value, str) and audio_value.startswith("data:audio"):
            try:
                header, encoded = audio_value.split(",", 1)
                extension = ".mp3" if "audio/mpeg" in header else ".wav"
                audio_filename = f"audio_{uuid.uuid4().hex[:12]}{extension}"
                (self.runtime.upload_folder / audio_filename).write_bytes(base64.b64decode(encoded))
                data = dict(data)
                data["audio"] = audio_filename
            except Exception:
                return {"error": "Invalid base64 audio data"}, 400

        job_id = str(uuid.uuid4())
        builder_data = dict(data)
        builder_data.update(video=video_filename, video_mode=video_mode, retake_start=retake_start, retake_end=retake_end, extra_params=extra_params)
        created_at = datetime.now(timezone.utc)
        submitted_at = iso_utc()
        try:
            resolution, job_data = build_job_data(
                project_root=self.runtime.project_root,
                data=builder_data,
                job_id=job_id,
                user_id=None,
                user_label=user_label,
                created_at=created_at,
                request_id=request_id,
                submitted_at=submitted_at,
            )
        except KeyError:
            return {"error": "Unsupported workflow"}, 400

        tracker = None
        if self.runtime.job_observability_enabled:
            try:
                tracker = JobTracker(self.runtime.repository_provider())
                tracker.create(
                    job_id,
                    request_id,
                    workflow_id=resolution.workflow_id,
                    workflow_version=resolution.entry.version,
                    workflow_category=resolution.entry.category,
                    model_name=str(job_data["model"]),
                    dispatch_payload=job_data,
                )
                tracker.event(job_id, "validation_passed", resulting_status="created")
            except Exception:
                self.logger.exception("job observability create failed", extra={"job_id": job_id, "request_id": request_id})
                return {"error": "Job persistence unavailable"}, 503

        redis_client = self.runtime.redis_client
        if redis_client is None:
            if tracker:
                tracker.fail(job_id, JobStatus.CREATED, stage="redis_enqueue", code="QUEUE_WRITE_ERROR", message="Queue unavailable")
            return {"error": "Redis service unavailable"}, 503

        try:
            if tracker and not tracker.transition(job_id, JobStatus.CREATED, JobStatus.QUEUED):
                raise RedisError("durable job enqueue transition failed")
            if tracker:
                tracker.event(job_id, "job_queued", resulting_status="queued")
            redis_client.rpush(self.runtime.redis_queue_name, json.dumps(job_data))
            if tracker:
                tracker.repository.mark_dispatched(job_id, iso_utc())
            status_key = f"job:status:{job_id}"
            redis_client.hset(status_key, mapping={
                "job_id": job_id,
                "status": "queued",
                "progress": 0,
                "image_url": "",
                "error": "",
                "updated_at": datetime.now().isoformat(),
            })
            redis_client.expire(status_key, 86400)
            return {
                "job_id": job_id,
                "status": "queued",
                "message": "Job queued",
            }, 202 if resolution.workflow_id in {"ltx_i2v", "ltx_flf"} else 200
        except RedisError:
            if tracker:
                current = (tracker.repository.get_job(job_id) or {}).get("status")
                tracker.fail(
                    job_id,
                    JobStatus(current) if current in {JobStatus.CREATED.value, JobStatus.QUEUED.value} else JobStatus.CREATED,
                    stage="redis_enqueue",
                    code="QUEUE_WRITE_ERROR",
                    message="Queue write failed",
                )
            self.logger.exception("Redis enqueue failed")
            return {"error": "Operation failed"}, 500

    def status(self, job_id: str) -> tuple[dict[str, Any], int]:
        redis_client = self.runtime.redis_client
        if redis_client:
            job_status = redis_client.hgetall(f"job:status:{job_id}")
            if job_status:
                return {
                    "job_id": str(escape(job_status.get("job_id", job_id))),
                    "status": str(escape(job_status.get("status", "unknown"))),
                    "progress": int(job_status.get("progress", 0)),
                    "image_url": str(escape(job_status.get("image_url", ""))),
                    "error": str(escape(job_status.get("error", ""))),
                    "source": "redis",
                }, 200
        job = self.runtime.repository_provider().get_job(job_id)
        if job:
            return {
                "job_id": job_id,
                "status": public_status(job["status"]),
                "progress": job.get("progress") or 0,
                "image_url": "",
                "error": job.get("sanitized_error_message") or "",
                "source": "mysql",
            }, 200
        return {"error": "Job not found", "job_id": job_id}, 404

    def cancel(self, job_id: str) -> tuple[dict[str, Any], int]:
        job = self.runtime.repository_provider().get_job(job_id)
        if not job:
            return {"error": "Job not found"}, 404
        current = job["status"]
        if current in {"completed", "failed", "cancelled"}:
            return {"success": False, "message": "Job cannot be cancelled in its current state"}, 400
        tracker = JobTracker(self.runtime.repository_provider())
        state = JobStatus.QUEUED if current == "queued" else JobStatus.RUNNING
        if not tracker.request_cancel(job_id, state):
            return {"success": False, "message": "Job state changed"}, 409
        redis_client = self.runtime.redis_client
        if redis_client is not None:
            key = f"job:status:{job_id}"
            if state is JobStatus.QUEUED:
                redis_client.hset(key, mapping={"status": "cancelled", "canonical_status": "cancelled", "error": "Task cancelled by user"})
            else:
                redis_client.hset(key, "cancel_requested", "true")
        return {
            "success": True,
            "message": "Task cancelled" if state is JobStatus.QUEUED else "Cancellation requested",
        }, 200 if state is JobStatus.QUEUED else 202
