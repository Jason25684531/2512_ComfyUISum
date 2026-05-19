"""
Managed GPU warmup controller.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    COMFYUI_OUTPUT_DIR,
    DEFAULT_CLIP_MODEL,
    DEFAULT_UNET_MODEL,
    DEFAULT_VAE_MODEL,
    WARMUP_DEFAULT_TIMEOUT,
    WARMUP_MAX_PROFILES,
    WARMUP_MODE,
    WARMUP_PRIORITY_HANDOFF_SECONDS,
    WARMUP_PROFILE_NAMES,
    WARMUP_PROFILE_TIMEOUTS,
    WARMUP_STATUS_KEY,
    WARMUP_STATUS_TTL_SECONDS,
    WARMUP_VIDEO_WORKFLOW_PATH,
)
from shared.config_base import PROJECT_ROOT, WORKFLOW_DIR


TERMINAL_WARMUP_STATES = {"ready", "failed", "skipped", "deferred"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_profile_name(profile_name: str) -> str:
    normalized = [character if character.isalnum() else "_" for character in profile_name.strip()]
    result = "".join(normalized).strip("_")
    return result or "warmup"


def _is_within_directory(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _get_warmup_public_error(error_message: str | None) -> str:
    lowered = (error_message or "").lower()
    if "queued" in lowered or "defer" in lowered:
        return "Warmup deferred for queued job"
    if "timeout" in lowered or "超時" in lowered:
        return "Warmup timeout"
    if "workflow" in lowered or "file" in lowered:
        return "Warmup workflow unavailable"
    if "submit" in lowered or "prompt" in lowered:
        return "Warmup submission failed"
    if "comfyui" in lowered:
        return "Warmup unavailable"
    return "Warmup failed"


@dataclass(frozen=True)
class WarmupProfile:
    name: str
    timeout_seconds: int
    workflow_kind: str = "builtin-image"
    workflow_path: str = ""
    high_cost: bool = False


def build_builtin_image_warmup_workflow(profile_name: str) -> dict[str, Any]:
    safe_profile_name = _safe_profile_name(profile_name)
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": DEFAULT_UNET_MODEL,
                "weight_dtype": "default"
            }
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": DEFAULT_CLIP_MODEL,
                "type": "lumina2",
                "device": "default"
            }
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": f"warmup::{safe_profile_name}",
                "clip": ["2", 0]
            }
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "",
                "clip": ["2", 0]
            }
        },
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": 256,
                "height": 256,
                "batch_size": 1
            }
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "seed": 42,
                "steps": 1,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0
            }
        },
        "7": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": DEFAULT_VAE_MODEL
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],
                "vae": ["7", 0]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": f"_warmup_{safe_profile_name}"
            }
        }
    }


def load_warmup_profiles() -> list[WarmupProfile]:
    default_timeout = max(1, WARMUP_DEFAULT_TIMEOUT)
    profile_timeout_map = dict(WARMUP_PROFILE_TIMEOUTS)

    built_in_profiles = {
        "default-image": WarmupProfile(
            name="default-image",
            timeout_seconds=profile_timeout_map.get("default-image", default_timeout),
            workflow_kind="builtin-image",
            high_cost=False,
        ),
        "video-opt-in": WarmupProfile(
            name="video-opt-in",
            timeout_seconds=profile_timeout_map.get("video-opt-in", max(default_timeout, 300)),
            workflow_kind="json-file",
            workflow_path=WARMUP_VIDEO_WORKFLOW_PATH,
            high_cost=True,
        ),
    }

    selected_profiles: list[WarmupProfile] = []
    for profile_name in WARMUP_PROFILE_NAMES:
        profile = built_in_profiles.get(profile_name)
        if profile:
            selected_profiles.append(profile)

    if not selected_profiles:
        selected_profiles.append(built_in_profiles["default-image"])

    return selected_profiles[: max(1, WARMUP_MAX_PROFILES)]


class WarmupController:
    def __init__(
        self,
        redis_client,
        comfy_client,
        logger,
        queue_name: str,
        mode: str = WARMUP_MODE,
        profiles: list[WarmupProfile] | None = None,
        status_key: str = WARMUP_STATUS_KEY,
        status_ttl_seconds: int = WARMUP_STATUS_TTL_SECONDS,
        priority_handoff_seconds: float = WARMUP_PRIORITY_HANDOFF_SECONDS,
    ):
        self.redis_client = redis_client
        self.comfy_client = comfy_client
        self.logger = logger
        self.queue_name = queue_name
        self.mode = mode
        self.profiles = profiles if profiles is not None else load_warmup_profiles()
        self.status_key = status_key
        self.status_ttl_seconds = status_ttl_seconds
        self.priority_handoff_seconds = priority_handoff_seconds
        self._abort_event = threading.Event()
        self._status_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._last_status: dict[str, str] = {}
        self._last_abort_reason = ""

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict[str, str]:
        with self._status_lock:
            return dict(self._last_status)

    def publish_status(
        self,
        status: str,
        *,
        profile: str = "",
        error: str = "",
        started_at: str = "",
        completed_at: str = "",
        timeout_seconds: int = 0,
        terminal: bool = False,
    ) -> dict[str, str]:
        payload = {
            "status": status,
            "mode": self.mode,
            "profile": profile,
            "last_error": error,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": _utc_now_iso(),
            "timeout_seconds": str(timeout_seconds) if timeout_seconds else "",
            "terminal": "true" if terminal else "false",
            "enabled": "false" if self.mode == "off" else "true",
        }

        with self._status_lock:
            self._last_status = payload

        try:
            self.redis_client.hset(self.status_key, mapping=payload)
            self.redis_client.expire(self.status_key, self.status_ttl_seconds)
        except Exception as exc:
            self.logger.warning(f"⚠️ 暖機狀態寫入失敗，改用本地狀態: {exc.__class__.__name__}")

        return payload

    def start(self) -> None:
        if self.mode == "off":
            self.logger.info("ℹ️ WARMUP_MODE=off，跳過 GPU 暖機")
            self.publish_status("skipped", terminal=True)
            return

        if self.mode == "legacy":
            self.logger.info("ℹ️ WARMUP_MODE=legacy，沿用舊式同步暖機")
            self._run_warmup(managed_mode=False)
            return

        self.publish_status("pending")
        self._thread = threading.Thread(target=self._run_warmup, kwargs={"managed_mode": True}, daemon=True, name="warmup-controller")
        self._thread.start()

    def mark_unavailable(self) -> None:
        if self.mode == "off":
            self.publish_status("skipped", terminal=True)
            return
        self.publish_status("failed", error="Warmup unavailable", terminal=True)

    def request_priority_handoff(self, reason: str = "queued job detected") -> None:
        if self.mode != "managed":
            return

        self._last_abort_reason = reason
        self._abort_event.set()

        wait_deadline = time.time() + max(0.0, self.priority_handoff_seconds)
        while time.time() < wait_deadline:
            status = self.get_status().get("status", "")
            if status in TERMINAL_WARMUP_STATES or status not in {"pending", "running"}:
                break
            time.sleep(0.1)

    def _queue_has_pending_jobs(self) -> bool:
        try:
            return bool((self.redis_client.llen(self.queue_name) or 0) > 0)
        except Exception as exc:
            self.logger.warning(f"⚠️ 無法讀取佇列深度，暖機改用保守模式: {exc.__class__.__name__}")
            return False

    def _should_abort(self) -> str | None:
        if self._abort_event.is_set():
            return self._last_abort_reason or "queued job detected"
        if self._queue_has_pending_jobs():
            return "queued job detected"
        return None

    def _interrupt_current_warmup(self) -> None:
        if not self.comfy_client.interrupt():
            self.logger.warning("⚠️ 暖機中止指令發送失敗")

    def _load_custom_workflow(self, workflow_path: str) -> dict[str, Any] | None:
        if not workflow_path:
            return None

        candidate_path = Path(workflow_path)
        if not candidate_path.is_absolute():
            candidate_path = (PROJECT_ROOT / candidate_path).resolve()

        allowed_roots = [WORKFLOW_DIR, PROJECT_ROOT / "ComfyUIworkflow_api"]
        if not any(_is_within_directory(candidate_path, root) for root in allowed_roots):
            return None
        if not candidate_path.exists() or not candidate_path.is_file():
            return None

        with open(candidate_path, "r", encoding="utf-8") as file:
            workflow = json.load(file)

        if not isinstance(workflow, dict):
            return None
        return workflow

    def _build_workflow(self, profile: WarmupProfile) -> dict[str, Any] | None:
        if profile.workflow_kind == "builtin-image":
            return build_builtin_image_warmup_workflow(profile.name)
        if profile.workflow_kind == "json-file":
            return self._load_custom_workflow(profile.workflow_path)
        return None

    def _cleanup_outputs(self, result: dict[str, Any]) -> None:
        output_dir = COMFYUI_OUTPUT_DIR.resolve()
        temp_dir = (COMFYUI_OUTPUT_DIR.parent / "temp").resolve()
        output_items = []
        for field_name in ("images", "videos", "gifs"):
            output_items.extend(result.get(field_name, []))

        for item in output_items:
            filename = item.get("filename")
            subfolder = item.get("subfolder", "")
            file_type = item.get("type", "output")
            if not filename:
                continue

            root_dir = temp_dir if file_type == "temp" else output_dir
            candidate_path = (root_dir / subfolder / filename).resolve()
            if not (_is_within_directory(candidate_path, root_dir) and candidate_path.exists() and candidate_path.is_file()):
                continue

            try:
                candidate_path.unlink()
                self.logger.info(f"🧹 已清理暖機輸出: {candidate_path.name}")
            except Exception as exc:
                self.logger.warning(f"⚠️ 暖機輸出清理失敗: {candidate_path.name} ({exc.__class__.__name__})")

    def _run_warmup(self, managed_mode: bool = True) -> None:
        selected_profiles = list(self.profiles[: max(1, WARMUP_MAX_PROFILES)])
        if not selected_profiles:
            self.publish_status("skipped", terminal=True)
            return

        if self.mode == "managed" and self._queue_has_pending_jobs():
            self.logger.info("ℹ️ 啟動時偵測到待處理任務，延後暖機")
            self.publish_status("deferred", error="Warmup deferred for queued job", terminal=True)
            return

        for profile in selected_profiles:
            if managed_mode and self._should_abort():
                self.logger.info("ℹ️ 暖機已讓位給真實任務")
                self.publish_status("deferred", error="Warmup deferred for queued job", terminal=True)
                return

            workflow = self._build_workflow(profile)
            if workflow is None:
                self.publish_status(
                    "failed",
                    profile=profile.name,
                    error="Warmup workflow unavailable",
                    timeout_seconds=profile.timeout_seconds,
                    terminal=True,
                )
                return

            started_at = _utc_now_iso()
            self.publish_status(
                "running",
                profile=profile.name,
                started_at=started_at,
                timeout_seconds=profile.timeout_seconds,
                terminal=False,
            )
            self.logger.info(f"🔥 開始受管暖機: {profile.name} (timeout={profile.timeout_seconds}s)")

            prompt_id = self.comfy_client.queue_prompt(workflow)
            if not prompt_id:
                self.publish_status(
                    "failed",
                    profile=profile.name,
                    error="Warmup submission failed",
                    started_at=started_at,
                    completed_at=_utc_now_iso(),
                    timeout_seconds=profile.timeout_seconds,
                    terminal=True,
                )
                return

            result = self.comfy_client.wait_for_completion(
                prompt_id,
                timeout=profile.timeout_seconds,
                should_abort=self._should_abort if managed_mode else None,
                on_abort=self._interrupt_current_warmup if managed_mode else None,
            )
            self._cleanup_outputs(result)

            if result.get("aborted"):
                self.logger.info("ℹ️ 暖機已中止並讓位給真實任務")
                self.publish_status(
                    "deferred",
                    profile=profile.name,
                    error="Warmup deferred for queued job",
                    started_at=started_at,
                    completed_at=_utc_now_iso(),
                    timeout_seconds=profile.timeout_seconds,
                    terminal=True,
                )
                return

            if not result.get("success"):
                self.publish_status(
                    "failed",
                    profile=profile.name,
                    error=_get_warmup_public_error(result.get("error")),
                    started_at=started_at,
                    completed_at=_utc_now_iso(),
                    timeout_seconds=profile.timeout_seconds,
                    terminal=True,
                )
                return

        self.logger.info("✅ GPU 暖機完成")
        self.publish_status(
            "ready",
            profile=selected_profiles[-1].name,
            started_at=self.get_status().get("started_at", ""),
            completed_at=_utc_now_iso(),
            timeout_seconds=selected_profiles[-1].timeout_seconds,
            terminal=True,
        )
