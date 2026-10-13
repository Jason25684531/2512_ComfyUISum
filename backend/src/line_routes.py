"""LINE input/output adapter for the existing VWE runtime."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import mimetypes
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, jsonify, request, send_file

from config import (
    LINE_API_TIMEOUT_SECONDS,
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
    LINE_DOWNLOAD_TOKEN_TTL,
    LINE_JOB_MAPPING_TTL,
    LINE_MAX_IMAGE_BYTES,
    LINE_MAX_PREVIEW_BYTES,
    LINE_MAX_VIDEO_BYTES,
    LINE_MAX_WEBHOOK_BYTES,
    LINE_NOTIFICATION_RETRY_LIMIT,
    LINE_PENDING_IMAGE_TTL,
    LINE_PUBLIC_BASE_URL,
    LINE_VIDEO_WORKFLOW_ID,
)
from shared.job_contracts import canonical_status
from shared.runtime_services import resolve_workflow_request


LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
PREVIEW_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}\.jpg$")

REPLY_GENERATING = "影片生成中。"
REPLY_QUEUED = "目前有影片正在生成，這次請求已排入佇列，會在前一個完成後執行。"
REPLY_IMAGE_RECEIVED = "圖片已收到，請輸入影片動作描述。"
REPLY_GENERATION_FAILED = "影片生成失敗，請重新嘗試。"
REPLY_IMAGE_FAILED = "圖片接收失敗，請重新傳送。"
REPLY_UNAVAILABLE = "目前無法生成影片，請稍後再試。"


def verify_line_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not body or not signature or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature.strip())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _safe_identifier(value: Any) -> str | None:
    value = str(value or "")
    return value if USER_ID_RE.fullmatch(value) else None


def _decode_redis(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _normalize_hash(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(_decode_redis(key)): _decode_redis(item) for key, item in value.items()}


def _parse_created_at(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class LineAdapter:
    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def redis(self):
        return self.runtime.redis_client

    @property
    def logger(self):
        return self.runtime.logger

    def configured(self, *, require_public_url: bool = True) -> bool:
        if not (LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN and LINE_VIDEO_WORKFLOW_ID):
            return False
        if require_public_url and not LINE_PUBLIC_BASE_URL.startswith(("http://", "https://")):
            return False
        return True

    def _redis_json(self, key: str) -> dict[str, Any] | None:
        client = self.redis
        if client is None:
            return None
        raw = _decode_redis(client.get(key))
        if not raw:
            return None
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _input_path(self, relative_path: Any) -> Path | None:
        if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
            return None
        if "\\" in relative_path or ":" in relative_path:
            return None
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        root = Path(self.runtime.upload_folder).resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _output_path(self, relative_path: Any) -> Path | None:
        if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
            return None
        if "\\" in relative_path or ":" in relative_path:
            return None
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".mp4":
            return None
        root = Path(self.runtime.storage_output_dir).resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _delete_pending(self, user_id: str, state: dict[str, Any] | None = None) -> None:
        if self.redis is None:
            return
        self.redis.delete(f"line:user:{user_id}")
        if state:
            path = self._input_path(state.get("image_path"))
            if path and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    self.logger.warning("LINE pending image cleanup failed")

    def pending_image(self, user_id: str) -> tuple[dict[str, Any], Path] | None:
        state = self._redis_json(f"line:user:{user_id}")
        if not state or state.get("state") != "i2v_wait_prompt":
            return None
        created_at = _parse_created_at(state.get("created_at"))
        if not created_at or (_now() - created_at).total_seconds() > LINE_PENDING_IMAGE_TTL:
            self._delete_pending(user_id, state)
            return None
        path = self._input_path(state.get("image_path"))
        if not path or not path.is_file() or path.stat().st_size <= 0:
            self._delete_pending(user_id, state)
            return None
        return state, path

    def _line_request(self, method: str, url: str, payload: dict[str, Any]) -> bool:
        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                json=payload,
                timeout=LINE_API_TIMEOUT_SECONDS,
            )
            return 200 <= response.status_code < 300
        except requests.RequestException:
            return False

    def reply(self, reply_token: Any, text: str) -> bool:
        if not isinstance(reply_token, str) or not (1 <= len(reply_token) <= 2048):
            return False
        return self._line_request(
            "POST",
            LINE_REPLY_URL,
            {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]},
        )

    def push(self, user_id: str, text: str) -> bool:
        return self._line_request(
            "POST",
            LINE_PUSH_URL,
            {"to": user_id, "messages": [{"type": "text", "text": text}]},
        )

    def push_video(self, user_id: str, video_url: str, preview_url: str) -> bool:
        if not user_id or not video_url.startswith("https://") or not preview_url.startswith("https://"):
            return False
        return self._line_request(
            "POST",
            LINE_PUSH_URL,
            {
                "to": user_id,
                "messages": [{
                    "type": "video",
                    "originalContentUrl": video_url,
                    "previewImageUrl": preview_url,
                }],
            },
        )

    def _resolve_workflow(self, mode: str):
        if mode not in {"t2v", "i2v"} or not LINE_VIDEO_WORKFLOW_ID:
            return None
        try:
            resolution = resolve_workflow_request(self.runtime.project_root, LINE_VIDEO_WORKFLOW_ID)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            return None
        if not resolution.entry.enabled or not resolution.entry.path.is_file():
            return None
        if mode not in (resolution.entry.video_mode_map or {}):
            return None
        return resolution

    def _image_data_uri(self, path: Path) -> str:
        data = path.read_bytes()
        if not data or len(data) > LINE_MAX_IMAGE_BYTES:
            raise ValueError("image size is invalid")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    def _store_job_mapping(self, job_id: str, user_id: str, mode: str, workflow_id: str) -> None:
        if self.redis is None:
            raise RuntimeError("Redis unavailable")
        self.redis.hset(
            f"line:job:{job_id}",
            mapping={
                "job_id": job_id,
                "user_id": user_id,
                "mode": mode,
                "workflow_id": workflow_id,
                "created_at": _iso_now(),
                "notification_state": "pending",
                "notification_attempts": "0",
            },
        )
        self.redis.expire(f"line:job:{job_id}", LINE_JOB_MAPPING_TTL)

    def has_active_job(self, user_id: str) -> bool:
        if self.redis is None:
            return False
        keys = self.redis.scan_iter(match="line:job:*") if hasattr(self.redis, "scan_iter") else self.redis.keys("line:job:*")
        for raw_key in keys:
            key = str(_decode_redis(raw_key))
            mapping = _normalize_hash(self.redis.hgetall(key))
            if _safe_identifier(mapping.get("user_id")) != user_id:
                continue
            job_id = str(mapping.get("job_id") or key.removeprefix("line:job:"))
            status = canonical_status(self._status_record(job_id).get("status", ""))
            if status in {"created", "queued", "running"}:
                return True
        return False

    def submit_video(self, user_id: str, text: str, mode: str, image_path: Path | None = None) -> bool:
        resolution = self._resolve_workflow(mode)
        if resolution is None:
            return False
        if mode == "i2v" and image_path is None:
            return False
        try:
            images = {"input": self._image_data_uri(image_path)} if image_path else {}
            payload, status = self.runtime.job_service.submit(
                {
                    "workflow": resolution.workflow_id,
                    "prompt": text,
                    "video_mode": mode,
                    "images": images,
                },
                request_id=str(uuid.uuid4()),
                user_label="line",
            )
        except Exception:
            self.logger.exception("LINE job submission failed")
            return False
        job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if status >= 400 or not isinstance(job_id, str) or not job_id:
            return False
        try:
            self._store_job_mapping(job_id, user_id, mode, resolution.workflow_id)
        except Exception:
            self.logger.exception("LINE job mapping failed")
            return False
        return True

    def _download_image(self, message_id: str) -> tuple[bytes, str] | None:
        headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
        response = None
        try:
            response = requests.get(
                LINE_CONTENT_URL.format(message_id=message_id),
                headers=headers,
                timeout=LINE_API_TIMEOUT_SECONDS,
                stream=True,
            )
            if response.status_code != 200:
                return None
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                return None
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > LINE_MAX_IMAGE_BYTES:
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > LINE_MAX_IMAGE_BYTES:
                    return None
                chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                return None
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/gif": ".gif",
            }.get(content_type, ".img")
            return data, extension
        except (ValueError, TypeError, OSError, requests.RequestException):
            return None
        finally:
            if response is not None:
                response.close()

    def stage_image(self, user_id: str, message_id: str) -> bool:
        downloaded = self._download_image(message_id)
        if downloaded is None or self.redis is None:
            return False
        data, extension = downloaded
        root = Path(self.runtime.upload_folder).resolve()
        root.mkdir(parents=True, exist_ok=True)
        filename = f"line_{uuid.uuid4().hex}{extension}"
        path = root / filename
        try:
            path.write_bytes(data)
            relative = path.relative_to(root).as_posix()
            state = {"state": "i2v_wait_prompt", "image_path": relative, "created_at": _iso_now()}
            self.redis.setex(f"line:user:{user_id}", LINE_PENDING_IMAGE_TTL, json.dumps(state))
            return True
        except (OSError, ValueError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def _event_user_id(self, event: dict[str, Any]) -> str | None:
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        return _safe_identifier(source.get("userId"))

    def handle_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict) or event.get("type") != "message":
            return
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        user_id = self._event_user_id(event)
        if not user_id:
            return
        message_type = message.get("type")
        reply_token = event.get("replyToken")
        if message_type == "image":
            message_id = _safe_identifier(message.get("id"))
            if message_id and self.stage_image(user_id, message_id):
                self.reply(reply_token, REPLY_IMAGE_RECEIVED)
            else:
                self.reply(reply_token, REPLY_IMAGE_FAILED)
            return
        if message_type != "text":
            return
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        text = text.strip()
        busy = self.has_active_job(user_id)
        pending = self.pending_image(user_id)
        if pending:
            _state, image_path = pending
            if self.submit_video(user_id, text, "i2v", image_path):
                self._delete_pending(user_id)
                self.reply(reply_token, REPLY_QUEUED if busy else REPLY_GENERATING)
            else:
                self.reply(reply_token, REPLY_GENERATION_FAILED)
            return
        if self.submit_video(user_id, text, "t2v"):
            self.reply(reply_token, REPLY_QUEUED if busy else REPLY_GENERATING)
        else:
            self.reply(reply_token, REPLY_UNAVAILABLE)

    def process_webhook(self, raw_body: bytes, signature: str | None) -> tuple[dict[str, Any], int]:
        if len(raw_body) > LINE_MAX_WEBHOOK_BYTES:
            return {"error": "Request too large"}, 413
        if not verify_line_signature(raw_body, signature, LINE_CHANNEL_SECRET):
            return {"error": "Invalid signature"}, 401
        if not self.configured(require_public_url=True) or self.redis is None:
            return {"error": REPLY_UNAVAILABLE}, 503
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"error": "Invalid request"}, 400
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return {"ok": True}, 200
        for event in events[:20]:
            try:
                self.handle_event(event)
            except Exception:
                self.logger.exception("LINE event handling failed")
        return {"ok": True}, 200

    def _status_record(self, job_id: str) -> dict[str, Any]:
        if self.redis is not None:
            record = _normalize_hash(self.redis.hgetall(f"job:status:{job_id}"))
            if record:
                return record
        try:
            return self.runtime.repository_provider().get_job(job_id) or {}
        except Exception:
            return {}

    def _output_name(self, status_record: dict[str, Any], job_id: str) -> str | None:
        image_url = str(status_record.get("image_url") or "")
        prefix = "/outputs/"
        if image_url.startswith(prefix):
            return image_url[len(prefix):]
        try:
            outputs = self.runtime.repository_provider().list_outputs(job_id)
        except Exception:
            outputs = []
        if outputs:
            filename = outputs[-1].get("filename")
            return filename if isinstance(filename, str) else None
        return None

    def _preview_path(self, relative_path: Any) -> Path | None:
        if not isinstance(relative_path, str) or not PREVIEW_RE.fullmatch(relative_path):
            return None
        root = Path(self.runtime.storage_output_dir).resolve()
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _create_preview(self, preview_path: Path) -> bool:
        """Create a small fixed-ratio LINE preview without adding a video stack."""
        try:
            from PIL import Image, ImageDraw

            preview_path.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (1280, 704), (15, 23, 42))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 1279, 703), outline=(96, 165, 250), width=8)
            draw.polygon(((560, 272), (560, 432), (720, 352)), fill=(255, 255, 255))
            image.save(preview_path, format="JPEG", quality=88, optimize=True)
            return preview_path.is_file() and preview_path.stat().st_size <= LINE_MAX_PREVIEW_BYTES
        except (OSError, ValueError):
            return False

    def _claim(self, job_id: str) -> bool:
        if self.redis is None:
            return False
        return bool(self.redis.set(f"line:claim:{job_id}", "1", ex=LINE_JOB_MAPPING_TTL, nx=True))

    def _release_claim(self, job_id: str) -> None:
        if self.redis is not None:
            self.redis.delete(f"line:claim:{job_id}")

    def _mark_terminal_notification(self, key: str, state: str) -> None:
        self.redis.hset(key, mapping={"notification_state": state, "notified_at": _iso_now()})

    def _record_push_failure(self, key: str) -> None:
        mapping = _normalize_hash(self.redis.hgetall(key))
        attempts = int(mapping.get("notification_attempts", "0") or 0) + 1
        state = "failed" if attempts >= LINE_NOTIFICATION_RETRY_LIMIT else "retry"
        self.redis.hset(key, mapping={"notification_attempts": str(attempts), "notification_state": state})

    def _notify_failure(self, key: str, user_id: str) -> None:
        if self.push(user_id, REPLY_GENERATION_FAILED):
            self._mark_terminal_notification(key, "notified_failure")
            return
        self._record_push_failure(key)

    def poll_once(self) -> int:
        if self.redis is None or not self.configured(require_public_url=True):
            return 0
        keys = self.redis.scan_iter(match="line:job:*") if hasattr(self.redis, "scan_iter") else self.redis.keys("line:job:*")
        processed = 0
        for raw_key in keys:
            key = str(_decode_redis(raw_key))
            mapping = _normalize_hash(self.redis.hgetall(key))
            if not mapping:
                continue
            state = str(mapping.get("notification_state", "pending"))
            if state in {"delivered", "notified_failure", "failed"}:
                continue
            job_id = str(mapping.get("job_id") or key.removeprefix("line:job:"))
            user_id = _safe_identifier(mapping.get("user_id"))
            if not user_id or not self._claim(job_id):
                continue
            status_record = self._status_record(job_id)
            status = canonical_status(status_record.get("status", ""))
            if status not in {"completed", "failed", "cancelled"}:
                self._release_claim(job_id)
                continue
            try:
                if status == "completed":
                    output_name = self._output_name(status_record, job_id)
                    output_path = self._output_path(output_name)
                    if (
                        output_path
                        and output_path.is_file()
                        and 0 < output_path.stat().st_size <= LINE_MAX_VIDEO_BYTES
                    ):
                        token = secrets.token_urlsafe(32)
                        preview_name = f"line_preview_{token}.jpg"
                        preview_path = self._preview_path(preview_name)
                        if preview_path is None or not self._create_preview(preview_path):
                            self._notify_failure(key, user_id)
                            continue
                        token_record = {
                            "job_id": job_id,
                            "output_name": output_name,
                            "preview_name": preview_name,
                            "created_at": _iso_now(),
                        }
                        self.redis.setex(
                            f"line:download:{token}",
                            LINE_DOWNLOAD_TOKEN_TTL,
                            json.dumps(token_record),
                        )
                        public_url = f"{LINE_PUBLIC_BASE_URL}/line/download/{token}"
                        preview_url = f"{LINE_PUBLIC_BASE_URL}/line/preview/{token}"
                        if self.push_video(user_id, public_url, preview_url):
                            self._mark_terminal_notification(key, "delivered")
                        else:
                            self.redis.delete(f"line:download:{token}")
                            preview_path.unlink(missing_ok=True)
                            self._record_push_failure(key)
                    else:
                        self._notify_failure(key, user_id)
                else:
                    self._notify_failure(key, user_id)
                processed += 1
            finally:
                self._release_claim(job_id)
        return processed

    def download(self, token: str):
        if not TOKEN_RE.fullmatch(token or "") or self.redis is None:
            return jsonify({"error": "Not found"}), 404
        record = self._redis_json(f"line:download:{token}")
        if not record:
            return jsonify({"error": "Not found"}), 404
        job_id = str(record.get("job_id") or "")
        output_name = record.get("output_name")
        status = canonical_status(self._status_record(job_id).get("status", ""))
        path = self._output_path(output_name)
        if (
            not job_id
            or status != "completed"
            or path is None
            or not path.is_file()
            or not 0 < path.stat().st_size <= LINE_MAX_VIDEO_BYTES
        ):
            return jsonify({"error": "Not found"}), 404
        response = send_file(path, mimetype="video/mp4", as_attachment=True, download_name="video.mp4", conditional=True)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def preview(self, token: str):
        if not TOKEN_RE.fullmatch(token or "") or self.redis is None:
            return jsonify({"error": "Not found"}), 404
        record = self._redis_json(f"line:download:{token}")
        if not record:
            return jsonify({"error": "Not found"}), 404
        job_id = str(record.get("job_id") or "")
        preview_name = record.get("preview_name")
        status = canonical_status(self._status_record(job_id).get("status", ""))
        path = self._preview_path(preview_name)
        if (
            not job_id
            or status != "completed"
            or path is None
            or not path.is_file()
            or not 0 < path.stat().st_size <= LINE_MAX_PREVIEW_BYTES
        ):
            return jsonify({"error": "Not found"}), 404
        response = send_file(path, mimetype="image/jpeg", as_attachment=False, conditional=True)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


class LineCompletionMonitor:
    def __init__(self, adapter: LineAdapter, interval_seconds: float = 5.0):
        self.adapter = adapter
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="line-completion-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.adapter.poll_once()
            except Exception:
                self.adapter.logger.exception("LINE completion monitor failed")


def create_blueprint(runtime) -> Blueprint:
    adapter = LineAdapter(runtime)
    monitor = LineCompletionMonitor(adapter)
    bp = Blueprint("line", __name__)
    bp.line_adapter = adapter
    bp.line_completion_monitor = monitor

    @bp.route("/line/webhook", methods=["POST"])
    def webhook():
        raw_body = request.get_data(cache=True, as_text=False)
        payload, status = adapter.process_webhook(raw_body, request.headers.get("X-Line-Signature"))
        return jsonify(payload), status

    @bp.get("/line/download/<token>")
    def download(token: str):
        return adapter.download(token)

    @bp.get("/line/preview/<token>")
    def preview(token: str):
        return adapter.preview(token)

    return bp
