"""Worker lifecycle and Redis dequeue loop.

Single-job execution lives in :mod:`job_processor`; this module owns only
startup, signals, heartbeat, maintenance, dequeue, and shutdown.
"""
from __future__ import annotations

import json
import logging
import signal
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import redis

# Allow direct execution from worker/src/main.py to import repository modules.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.utils import get_redis_client, load_env, setup_logger

load_env()

from comfy_client import ComfyClient
from config import (
    COMFYUI_OUTPUT_DIR,
    COMFYUI_INPUT_DIR,
    JOB_QUEUE,
    REDIS_HOST,
    REDIS_PORT,
    WARMUP_MODE,
    BUILD_ID,
)
from job_processor import (
    JobProcessor,
    cleanup_old_output_files,
    cleanup_old_temp_files,
    reconcile_stale_running,
)
from shared.config_base import (
    JOB_RECONCILE_SECONDS,
    WORKER_HEARTBEAT_SECONDS,
    WORKER_HEARTBEAT_TTL_SECONDS,
    WORKER_ID,
    WORKFLOW_MANIFEST_POLICY,
)
from shared.job_tracker import JobTracker
from shared.observability_runtime import job_repository
from warmup import WarmupController
from workflow.runtime import load_workflow_catalog

logger = setup_logger("worker", log_level=logging.INFO)
_shutdown_flag = False
_current_job_id: str | None = None


def _shutdown_handler(signum, _frame) -> None:
    global _shutdown_flag
    _shutdown_flag = True
    logger.info("shutdown signal received: %s", signal.Signals(signum).name)


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)


def worker_heartbeat(redis_client, comfy_client=None) -> None:
    """Publish worker and ComfyUI liveness while the process is running."""
    while not _shutdown_flag:
        try:
            worker_id = WORKER_ID or socket.gethostname()
            current = _current_job_id or ""
            key = f"worker:heartbeat:{worker_id}"
            redis_client.hset(
                key,
                mapping={
                    "worker_id": worker_id,
                    "status": "busy" if current else "idle",
                    "current_job_id": current,
                    "last_seen_at": datetime.utcnow().isoformat() + "Z",
                    "build": BUILD_ID,
                },
            )
            redis_client.expire(key, WORKER_HEARTBEAT_TTL_SECONDS)
            redis_client.sadd("worker:heartbeat:index", worker_id)
            # ponytail: bounded cleanup; a dedicated registry is only needed for very large worker fleets.
            for stale_id in list(redis_client.sscan_iter("worker:heartbeat:index", count=100))[:100]:
                if not redis_client.exists(f"worker:heartbeat:{stale_id}"):
                    redis_client.srem("worker:heartbeat:index", stale_id)
            redis_client.setex("worker:heartbeat", WORKER_HEARTBEAT_TTL_SECONDS, "alive")
            if comfy_client:
                reachable = comfy_client.check_connection(retry=0, initial_delay=0)
                redis_client.hset(
                    "comfyui:health",
                    mapping={
                        "status": "healthy" if reachable else "unavailable",
                        "last_checked_at": datetime.utcnow().isoformat() + "Z",
                    },
                )
                redis_client.expire("comfyui:health", WORKER_HEARTBEAT_TTL_SECONDS * 2)
            time.sleep(WORKER_HEARTBEAT_SECONDS)
        except Exception:
            logger.exception("worker heartbeat failed")
            time.sleep(WORKER_HEARTBEAT_SECONDS)


def _validate_runtime(catalog) -> None:
    errors = catalog.validate()
    for entry in catalog.entries.values():
        if not entry.version:
            errors.append(f"{entry.workflow_id}: version is required")
        if not isinstance(entry.observability.get("output"), dict):
            errors.append(f"{entry.workflow_id}: observability.output is required")
    if errors:
        logger.warning("workflow observability validation: %s", "; ".join(errors))
        if WORKFLOW_MANIFEST_POLICY == "strict":
            raise RuntimeError("workflow manifest validation failed")


def main() -> None:
    global _current_job_id

    logger.info("Worker starting")
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        logger.info("Redis connected: %s:%s", REDIS_HOST, REDIS_PORT)
    except Exception:
        logger.exception("Redis connection failed")
        raise SystemExit(1)

    comfy_client = ComfyClient(logger=logger)
    _validate_runtime(load_workflow_catalog())
    try:
        replayed = JobTracker(job_repository()).replay_output_receipts(Path(COMFYUI_OUTPUT_DIR))
        if replayed:
            logger.info("replayed %s durable output receipts", replayed)
    except Exception:
        logger.exception("output receipt reconciliation failed")

    warmup_controller = WarmupController(
        redis_client=redis_client,
        comfy_client=comfy_client,
        logger=logger,
        queue_name=JOB_QUEUE,
    )
    processor = JobProcessor(redis_client, comfy_client, logger_instance=logger)

    threading.Thread(
        target=worker_heartbeat,
        args=(redis_client, comfy_client),
        daemon=True,
    ).start()

    if comfy_client.check_connection():
        logger.info("ComfyUI connected")
        warmup_controller.start()
    else:
        logger.warning("ComfyUI unavailable; warmup deferred")
        warmup_controller.mark_unavailable()

    cleanup_old_temp_files()
    cleanup_old_output_files()

    processing_queue = f"{JOB_QUEUE}:processing"
    stranded = redis_client.lrange(processing_queue, 0, -1)
    if stranded:
        redis_client.delete(processing_queue)
        redis_client.rpush(JOB_QUEUE, *stranded)
        logger.warning("requeued %s unacknowledged jobs", len(stranded))

    last_cleanup = time.time()
    last_reconcile = 0.0
    cleanup_interval = 3600
    retry_delay = 2.0
    max_retry_delay = 60.0

    logger.info("Worker listening on queue %s (input=%s, warmup=%s)", JOB_QUEUE, COMFYUI_INPUT_DIR, WARMUP_MODE)
    while not _shutdown_flag:
        try:
            now = time.time()
            if now - last_cleanup > cleanup_interval:
                cleanup_old_temp_files()
                cleanup_old_output_files()
                last_cleanup = now
            if now - last_reconcile >= JOB_RECONCILE_SECONDS:
                last_reconcile = now
                reconcile_stale_running(redis_client, comfy_client)

            job_json = redis_client.blmove(JOB_QUEUE, processing_queue, 5, src="LEFT", dest="RIGHT")
            retry_delay = 2.0
            if not job_json:
                continue

            try:
                job_data = json.loads(job_json)
                _current_job_id = job_data.get("job_id", "unknown")
                warmup_controller.request_priority_handoff()
                processor.process(job_data)
            except json.JSONDecodeError:
                logger.exception("invalid job JSON")
            finally:
                _current_job_id = None
                redis_client.lrem(processing_queue, 1, job_json)

        except redis.ConnectionError:
            logger.exception("Redis connection lost; retrying in %.0fs", retry_delay)
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
            try:
                redis_client = get_redis_client()
                processor.redis = redis_client
                warmup_controller.redis_client = redis_client
                logger.info("Redis reconnected")
                retry_delay = 2.0
            except Exception:
                logger.exception("Redis reconnect failed")
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("worker loop failed")
            time.sleep(1)

    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
