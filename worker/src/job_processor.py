"""Single-job Worker execution pipeline.

This module owns claim → workflow → input → ComfyUI → output → status → cleanup.
The queue/lifecycle loop stays in ``main.py``.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path

import redis
from PIL import Image

from comfy_client import ComfyClient
from config import (
    COMFYUI_INPUT_DIR,
    COMFYUI_OUTPUT_DIR,
    COMFY_SUBMIT_TIMEOUT_SECONDS,
    COMFY_HISTORY_TIMEOUT_SECONDS,
    COMFY_WS_WAIT_TIMEOUT_SECONDS,
    DEFAULT_CLIP_MODEL,
    DEFAULT_UNET_MODEL,
    DEFAULT_VAE_MODEL,
    JOB_QUEUE,
    JOB_STATUS_EXPIRE_SECONDS,
    OUTPUT_COPY_RETRY_COUNT,
    OUTPUT_COPY_RETRY_DELAY_SECONDS,
    OUTPUT_COPY_WAIT_SECONDS,
    STORAGE_INPUT_DIR,
    TEMP_FILE_MAX_AGE_HOURS,
    WORKFLOW_CONFIG_PATH,
    WORKFLOW_DIR,
)
from shared.config_base import (
    JOB_OBSERVABILITY_ENABLED,
    JOB_STALE_GRACE_SECONDS,
    STORAGE_OUTPUT_DIR,
    WORKER_ID,
)
from shared.error_sanitizer import COMFYUI_OUTPUT_MISSING, COMFYUI_UNAVAILABLE, ENGINE_EXECUTION_FAILED
from shared.job_contracts import JobStatus, canonical_status, validate_job_payload
from shared.job_tracker import JobTracker
from shared.observability_runtime import job_repository
from shared.security import get_public_error_message
from shared.utils import JobLogAdapter
from workflow.observability import WorkflowAdapter
from workflow.runtime import load_workflow_catalog, parse_workflow

logger = logging.getLogger("worker")
WORKER_TIMEOUT = COMFY_WS_WAIT_TIMEOUT_SECONDS
GPU_SYNC_WARNING = "GPU input sync failed"


def save_base64_image(base64_data: str, job_id: str, field_name: str, job_logger=None) -> str:
    log = job_logger or logger
    if isinstance(base64_data, str) and "," in base64_data:
        base64_data = base64_data.split(",", 1)[1].strip()
    try:
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        image_bytes = buffer.getvalue()
    except Exception as exc:
        raise ValueError(f"invalid image data: {exc}") from exc

    filename = f"upload_{job_id}_{field_name}.png"
    filepath = Path(COMFYUI_INPUT_DIR) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open("wb") as output:
        output.write(image_bytes)
        output.flush()
        os.fsync(output.fileno())
    if not filepath.exists() or filepath.stat().st_size != len(image_bytes):
        raise IOError(f"image staging failed: {filepath}")
    try:
        with Image.open(filepath) as check:
            check.verify()
    except Exception as exc:
        log.warning("staged image verification failed: %s", exc)
    return filename


def sync_image_to_comfyui_input(client: ComfyClient, filepath: Path, job_logger=None) -> None:
    log = job_logger or logger
    log.info("Syncing input image to ComfyUI: %s", filepath.name)
    if client.upload_image(str(filepath)):
        return
    raise RuntimeError(f"{GPU_SYNC_WARNING}: {filepath.name}")


def copy_audio_to_comfyui(audio_filename: str, job_id: str, client: ComfyClient | None = None, job_logger=None) -> str:
    source_path = Path(STORAGE_INPUT_DIR) / audio_filename
    if not source_path.exists():
        raise FileNotFoundError(f"audio input missing: {source_path}")
    destination = Path(COMFYUI_INPUT_DIR) / f"audio_{job_id}{source_path.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    if client is not None:
        sync_image_to_comfyui_input(client, destination, job_logger)
    return destination.name


def copy_video_to_comfyui(video_filename: str, job_id: str, client: ComfyClient | None = None, job_logger=None) -> str:
    source_path = Path(STORAGE_INPUT_DIR) / video_filename
    if not source_path.exists():
        raise FileNotFoundError(f"video input missing: {source_path}")
    destination = Path(COMFYUI_INPUT_DIR) / f"video_{job_id}{source_path.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    if client is not None:
        sync_image_to_comfyui_input(client, destination, job_logger)
    return destination.name


def cleanup_old_temp_files() -> None:
    input_dir = Path(COMFYUI_INPUT_DIR)
    if not input_dir.exists():
        return
    cutoff = datetime.now() - timedelta(hours=TEMP_FILE_MAX_AGE_HOURS)
    for filepath in input_dir.glob("upload_*.png"):
        try:
            if datetime.fromtimestamp(filepath.stat().st_mtime) < cutoff:
                filepath.unlink()
        except OSError as exc:
            logger.warning("temp cleanup failed for %s: %s", filepath, exc)


def resolve_output_path(filename: str) -> Path:
    root = Path(COMFYUI_OUTPUT_DIR).resolve()
    path = (root / Path(filename).name).resolve()
    path.relative_to(root)
    return path


def validate_local_output_file(filename: str, job_logger=None) -> tuple[Path, int]:
    path = resolve_output_path(filename)
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"output file unavailable: {path}")
    if job_logger:
        job_logger.info("local output ready: %s (%s bytes)", path, path.stat().st_size)
    return path, path.stat().st_size


def cleanup_old_output_files() -> None:
    output_dir = Path(COMFYUI_OUTPUT_DIR)
    if not output_dir.exists():
        return
    cutoff = datetime.now() - timedelta(days=30)
    for filepath in output_dir.iterdir():
        try:
            if filepath.is_file() and datetime.fromtimestamp(filepath.stat().st_mtime) < cutoff:
                filepath.unlink()
        except OSError as exc:
            logger.warning("output cleanup failed for %s: %s", filepath, exc)


def update_job_status(
    redis_client: redis.Redis,
    job_id: str,
    status: str,
    progress: int = 0,
    image_url: str | None = None,
    error: str | None = None,
    public_error: bool = False,
    **extra,
) -> None:
    data = {
        "status": status,
        "progress": progress,
        "canonical_status": canonical_status(status),
        "worker_id": WORKER_ID or socket.gethostname(),
    }
    if image_url:
        data["image_url"] = image_url
    if error:
        data["error"] = error if public_error else get_public_error_message(error)
    data.update({key: value for key, value in extra.items() if value is not None})
    redis_client.hset(f"job:status:{job_id}", mapping=data)
    redis_client.expire(f"job:status:{job_id}", JOB_STATUS_EXPIRE_SECONDS)


def reconcile_stale_running(redis_client: redis.Redis, client: ComfyClient) -> int:
    if not JOB_OBSERVABILITY_ENABLED:
        return 0
    tracker = JobTracker(job_repository())
    resolved = tracker.replay_output_receipts(Path(STORAGE_OUTPUT_DIR))
    now = datetime.utcnow()
    catalog = load_workflow_catalog()
    for job in job_repository().list_running_jobs():
        started = job.get("started_at") or job.get("updated_at")
        if not started:
            continue
        if getattr(started, "tzinfo", None):
            started = started.replace(tzinfo=None)
        try:
            timeout = catalog.resolve(job.get("workflow_id") or "").entry.observability.get("timeout_seconds", WORKER_TIMEOUT)
        except Exception:
            timeout = WORKER_TIMEOUT
        if now < started + timedelta(seconds=int(timeout) + JOB_STALE_GRACE_SECONDS):
            continue
        prompt_id = job.get("comfyui_prompt_id")
        outputs = client.get_outputs_from_history(prompt_id) if prompt_id else {}
        candidates = [("video", item) for item in outputs.get("videos", []) + outputs.get("gifs", [])]
        candidates += [("image", item) for item in outputs.get("images", [])]
        if candidates:
            output_type, item = candidates[-1]
            filename = client.copy_output_file(item.get("filename", ""), item.get("subfolder", ""), item.get("type", "output"), job["job_id"])
            if filename:
                try:
                    path, _ = validate_local_output_file(filename)
                    if tracker.complete_with_output(job["job_id"], path=path, storage_uri=f"/outputs/{filename}", filename=filename, output_type=output_type, source_node_id=item.get("node_id"), metadata={"recovered_from": "history"}):
                        update_job_status(redis_client, job["job_id"], "finished", progress=100, image_url=f"/outputs/{filename}")
                        resolved += 1
                        continue
                except Exception:
                    logger.exception("stale output recovery failed: %s", job["job_id"])
        if tracker.fail(job["job_id"], JobStatus.RUNNING, stage="timeout", code="JOB_TIMEOUT", message="worker execution timed out"):
            tracker.event(job["job_id"], "job_timed_out", resulting_status="failed", stage="timeout", error_code="JOB_TIMEOUT")
            update_job_status(redis_client, job["job_id"], "failed", error="Job timed out", public_error=True)
            resolved += 1
    return resolved


class JobProcessor:
    """Execute one already-dequeued job with injected runtime dependencies."""

    def __init__(self, redis_client: redis.Redis, comfy_client: ComfyClient, *, logger_instance=None) -> None:
        self.redis = redis_client
        self.comfy = comfy_client
        self.logger = logger_instance or logger

    def process(self, job_data: dict) -> None:
        valid_payload, payload_error = validate_job_payload(job_data)
        if not valid_payload:
            self.logger.error("refusing payload: %s", payload_error)
            self.redis.rpush(f"{JOB_QUEUE}:dead", json.dumps({"error": payload_error, "payload": {"job_id": job_data.get("job_id") if isinstance(job_data, dict) else None}}))
            return

        job_id = job_data["job_id"]
        tracker = None
        if JOB_OBSERVABILITY_ENABLED:
            try:
                tracker = JobTracker(job_repository())
                if not tracker.transition(job_id, JobStatus.QUEUED, JobStatus.RUNNING, worker_id=WORKER_ID or socket.gethostname()):
                    self.logger.warning("job claim rejected: %s", job_id)
                    return
                tracker.event(job_id, "worker_claimed", resulting_status="running")
            except Exception:
                self.logger.exception("durable worker claim failed: %s", job_id)
                return

        requested_workflow = job_data.get("workflow", "text_to_image")
        try:
            resolution = load_workflow_catalog().resolve(requested_workflow)
            workflow_name = resolution.workflow_id
            workflow_entry = resolution.entry
            if not workflow_entry.enabled:
                raise ValueError(f"workflow disabled: {workflow_name}")
            workflow_adapter = WorkflowAdapter(workflow_entry)
        except Exception as exc:
            if tracker:
                tracker.fail(job_id, JobStatus.RUNNING, stage="workflow_resolve", code="UNSUPPORTED_WORKFLOW", message=exc)
            update_job_status(self.redis, job_id, "failed", error="Unsupported workflow")
            return

        job_data["workflow"] = workflow_name
        job_data.setdefault("workflow_requested", requested_workflow)
        if tracker:
            tracker.event(job_id, "workflow_resolved", resulting_status="running", metadata={"workflow_id": workflow_entry.workflow_id, "version": workflow_entry.version})

        user_id = job_data.get("user_id")
        user_label = job_data.get("user_label") or ("anonymous" if not user_id else f"user:{user_id}")
        job_logger = JobLogAdapter(self.logger, {"job_id": job_id, "workflow": workflow_name, "user_id": user_id, "user_label": user_label})
        try:
            self._execute(job_data, job_id, workflow_name, workflow_entry, workflow_adapter, tracker, job_logger)
        except Exception as exc:
            job_logger.exception("job execution failed")
            update_job_status(self.redis, job_id, "failed", progress=0, error=ENGINE_EXECUTION_FAILED)
            if tracker:
                tracker.fail(job_id, JobStatus.RUNNING, stage="comfyui_submit", code="COMFYUI_SUBMIT_ERROR", message=exc)

    def _execute(self, job_data, job_id, workflow_name, workflow_entry, workflow_adapter, tracker, job_logger) -> None:
        update_job_status(self.redis, job_id, "processing", progress=10)
        if not self.comfy.check_connection():
            raise RuntimeError(COMFYUI_UNAVAILABLE)

        prompt = job_data.get("prompt", "")
        prompts = job_data.get("prompts", [])
        seed = job_data.get("seed", -1)
        aspect_ratio = job_data.get("aspect_ratio", "1:1")
        model = job_data.get("model", "turbo_fp8")
        batch_size = job_data.get("batch_size", 1)
        images = job_data.get("images", {})
        image_files = {}

        job_logger.info("workflow=%s prompt=%s", workflow_name, prompt[:50] if prompt else "(empty)")
        job_logger.info(
            "timeout config: submit=%ss ws_wait=%ss history=%ss copy_retries=%s copy_delay=%ss copy_wait=%ss",
            COMFY_SUBMIT_TIMEOUT_SECONDS, COMFY_WS_WAIT_TIMEOUT_SECONDS, COMFY_HISTORY_TIMEOUT_SECONDS,
            OUTPUT_COPY_RETRY_COUNT, OUTPUT_COPY_RETRY_DELAY_SECONDS, OUTPUT_COPY_WAIT_SECONDS,
        )
        update_job_status(self.redis, job_id, "processing", progress=15)
        for field_name, base64_data in (images or {}).items():
            if not base64_data:
                continue
            try:
                filename = save_base64_image(base64_data, job_id, field_name, job_logger)
                sync_image_to_comfyui_input(self.comfy, Path(COMFYUI_INPUT_DIR) / filename, job_logger)
                image_files[field_name] = filename
            except Exception as exc:
                job_logger.warning("image staging failed for %s: %s", field_name, exc)
                raise RuntimeError(f"Input image upload failed for {field_name}") from exc

        audio_file = job_data.get("audio", "")
        comfyui_audio_file = ""
        if audio_file:
            try:
                comfyui_audio_file = copy_audio_to_comfyui(audio_file, job_id, self.comfy, job_logger)
            except Exception as exc:
                job_logger.warning("audio staging failed for %s: %s", audio_file, exc)
                raise RuntimeError("Input audio upload failed") from exc

        video_file = job_data.get("video", "")
        video_mode = job_data.get("video_mode", "")
        comfyui_video_file = ""
        if video_file:
            try:
                comfyui_video_file = copy_video_to_comfyui(video_file, job_id, self.comfy, job_logger)
            except Exception as exc:
                job_logger.warning("video staging failed for %s: %s", video_file, exc)
                raise RuntimeError("Input video upload failed") from exc
        update_job_status(self.redis, job_id, "processing", progress=20)

        job_logger.info("parse start")
        workflow = parse_workflow(
            workflow_name=workflow_name,
            prompt=prompt,
            seed=seed,
            aspect_ratio=aspect_ratio,
            model=model,
            batch_size=batch_size,
            image_files=image_files,
            audio_file=comfyui_audio_file,
            video_file=comfyui_video_file,
            video_mode=video_mode,
            retake_start=job_data.get("retake_start"),
            retake_end=job_data.get("retake_end"),
            extra_params=job_data.get("extra_params") or {},
            prompts=prompts,
        )
        job_logger.info("parse end")
        if tracker:
            tracker.event(job_id, "workflow_loaded", resulting_status="running")

        update_job_status(self.redis, job_id, "processing", progress=30)
        if workflow_name == "ideogram4_regional_t2i":
            self.comfy.verify_regional_caption_contract(workflow)
        prompt_id = self.comfy.queue_prompt(workflow)
        if not prompt_id:
            raise RuntimeError(ENGINE_EXECUTION_FAILED)
        if tracker:
            tracker.set_prompt_id(job_id, prompt_id)
            tracker.event(job_id, "comfyui_submitted", resulting_status="running")
        update_job_status(self.redis, job_id, "processing", progress=30, comfyui_prompt_id=prompt_id)

        last_db_progress = -10

        def on_progress(progress):
            nonlocal last_db_progress
            mapped = 30 + int(progress * 0.65)
            update_job_status(self.redis, job_id, "processing", progress=mapped)
            if tracker and mapped - last_db_progress >= 10:
                last_db_progress = mapped
                tracker.progress(job_id, mapped)
            job_logger.info("progress heartbeat: progress=%s mapped_progress=%s", progress, mapped)

        comfy_started = False

        def on_event(event_type, event):
            nonlocal comfy_started
            if not tracker:
                return
            node_info = workflow_adapter.node(workflow, event.get("node"))
            node_id, node_type = node_info["node_id"], node_info["node_type"]
            if event_type == "node_started":
                if not comfy_started:
                    comfy_started = True
                    tracker.event(job_id, "comfyui_started", resulting_status="running")
                tracker.update_node(job_id, node_id=node_id, node_type=node_type)
                tracker.event(job_id, "node_started", resulting_status="running", stage=node_info["stage"], node_id=node_id, node_type=node_type)
            elif event_type == "node_completed":
                tracker.update_node(job_id, node_id=node_id, node_type=node_type, completed=True)
                tracker.event(job_id, "node_completed", resulting_status="running", stage=node_info["stage"], node_id=node_id, node_type=node_type)
            elif event_type == "execution_error":
                tracker.event(job_id, "job_failed", resulting_status="running", stage="comfyui_execution", error_code="COMFYUI_NODE_ERROR", message=event.get("exception_message"))
            elif event_type == "execution_interrupted":
                current = tracker.repository.get_job(job_id) or {}
                if current.get("cancel_requested_at") and tracker.transition(job_id, JobStatus.RUNNING, JobStatus.CANCELLED, error_stage="cancellation", error_code="CANCELLED_BY_CLIENT"):
                    tracker.event(job_id, "job_cancelled", resulting_status="cancelled", stage="cancellation", error_code="CANCELLED_BY_CLIENT")

        def should_abort():
            current = tracker.repository.get_job(job_id) if tracker else None
            return "client_cancel_requested" if current and current.get("cancel_requested_at") else None

        result = self.comfy.wait_for_completion(
            prompt_id=prompt_id,
            timeout=WORKER_TIMEOUT,
            on_progress=on_progress,
            on_event=on_event,
            should_abort=should_abort,
            on_abort=lambda: job_logger.info("cancellation request observed"),
        )
        if result.get("interrupted"):
            current = tracker.repository.get_job(job_id) if tracker else None
            if current and current.get("status") == JobStatus.CANCELLED.value:
                update_job_status(self.redis, job_id, "cancelled", error="Task cancelled by user", public_error=True)
                return
        if result.get("success"):
            self._persist_result(result, job_id, workflow_adapter, workflow, tracker, job_logger)
            return

        error = result.get("error", "workflow execution failed")
        if "timeout" in error.lower():
            partial = self.comfy.get_outputs_from_history(prompt_id)
            all_partial = partial.get("videos", []) + partial.get("gifs", []) + partial.get("images", [])
            if all_partial:
                filename = self.comfy.copy_output_file(filename=all_partial[-1].get("filename"), subfolder=all_partial[-1].get("subfolder", ""), job_id=job_id)
                if filename:
                    validate_local_output_file(filename, job_logger)
                    update_job_status(self.redis, job_id, "failed", error=f"{error} (partial output saved)", image_url=f"/outputs/{filename}")
                    return
        update_job_status(self.redis, job_id, "failed", error=error)
        if tracker:
            tracker.fail(job_id, JobStatus.RUNNING, stage="comfyui_execution", code="UNKNOWN_ERROR", message=error)

    def _persist_result(self, result, job_id, workflow_adapter, workflow, tracker, job_logger) -> None:
        videos = result.get("videos", [])
        gifs = result.get("gifs", [])
        images = result.get("images", [])
        candidates = [(item, "video") for item in videos + gifs] or [(item, "image") for item in images]
        if not candidates:
            raise RuntimeError("expected output not found")
        real = [item for item in candidates if item[0].get("type") != "temp"] or candidates
        selected, output_type = next(((item, kind) for item, kind in real if "Combined" in item.get("filename", "") or "Full" in item.get("filename", "")), real[-1])
        file_type = selected.get("type", "output")
        filename = self.comfy.copy_output_file(selected.get("filename"), selected.get("subfolder", ""), file_type, job_id)
        if not filename and len(real) > 1:
            for item, _kind in real:
                if item == selected:
                    continue
                filename = self.comfy.copy_output_file(item.get("filename"), item.get("subfolder", ""), item.get("type", "output"), job_id)
                if filename:
                    break
        if not filename:
            raise RuntimeError("output persistence failed")
        path, _size = validate_local_output_file(filename, job_logger)
        file_url = f"/outputs/{filename}"
        if tracker:
            output_nodes = workflow_adapter.expected_output_nodes()
            source_node = str(selected.get("node_id") or "") or (output_nodes or (None,))[0]
            if not tracker.complete_with_output(job_id, path=path, storage_uri=file_url, filename=filename, output_type=output_type, source_node_id=source_node, metadata={"source_type": file_type}):
                raise RuntimeError("durable output finalize rejected")
        update_job_status(self.redis, job_id, "finished", progress=100, image_url=file_url)
        job_logger.info("job completed: %s", file_url)
