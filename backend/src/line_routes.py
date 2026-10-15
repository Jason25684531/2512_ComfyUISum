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
import struct
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
)
from shared.job_contracts import canonical_status
from shared.runtime_services import resolve_workflow_request


LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
PREVIEW_RE = re.compile(r"^[A-Za-z0-9_.-]{1,160}\.jpg$")
IMAGE_WORKFLOW_ID = "image_gpt25_sunburst"
VIDEO_WORKFLOW_ID = "video_minimax_h3"
MAX_PENDING_IMAGES = 3
MAX_VIDEO_IMAGES = 2

REPLY_GENERATING = "已開始生成。"
REPLY_QUEUED = "目前有工作正在生成，這次請求已排入佇列，會在前一個完成後執行。"
REPLY_IMAGE_RECEIVED = "已收到第 {count} 張圖片，可繼續上傳或輸入提示詞。"
REPLY_CHOOSE_OUTPUT = "要輸出圖片還是影片？"
REPLY_NEED_PROMPT = "請先輸入提示詞，再選擇輸出類型。"
REPLY_CANCELLED = "已取消，圖片和提示詞都已清除。"
REPLY_IMAGE_LIMIT = "最多可上傳 3 張圖片。"
REPLY_VIDEO_IMAGE_LIMIT = "影片最多接受 2 張圖片。"
REPLY_GENERATION_FAILED = "生成失敗，請重新嘗試。"
REPLY_IMAGE_FAILED = "圖片接收失敗，請重新傳送。"
REPLY_UNAVAILABLE = "目前無法生成，請稍後再試。"


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


def _mp4_size(path: Path) -> tuple[int, int] | None:
    """Read the first video track's display size from the MP4 tkhd box (no ffmpeg in Backend)."""
    try:
        with path.open("rb") as handle:
            end = path.stat().st_size
            containers = {b"moov", b"trak"}
            offset = 0
            while offset + 8 <= end:
                handle.seek(offset)
                size, kind = struct.unpack(">I4s", handle.read(8))
                header = 8
                if size == 1:
                    size, header = struct.unpack(">Q", handle.read(8))[0], 16
                elif size == 0:
                    size = end - offset
                if size < header:
                    return None
                if kind in containers:
                    offset += header
                    continue
                if kind == b"tkhd":
                    payload = handle.read(min(size - header, 96))
                    width_at = 88 if payload[:1] == b"\x01" else 76
                    if len(payload) >= width_at + 8:
                        width, height = (value >> 16 for value in struct.unpack(">II", payload[width_at:width_at + 8]))
                        if width and height:
                            return width, height
                offset += size
    except (OSError, struct.error):
        return None
    return None


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
        if not (LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN):
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

    def _output_path(self, relative_path: Any, kind: str = "video") -> Path | None:
        if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
            return None
        if "\\" in relative_path or ":" in relative_path:
            return None
        relative = Path(relative_path)
        extensions = {"video": {".mp4"}, "image": {".png", ".jpg", ".jpeg"}}
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() not in extensions.get(kind, set()):
            return None
        root = Path(self.runtime.storage_output_dir).resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _delete_pending(self, user_id: str, state: dict[str, Any] | None = None) -> None:
        if self.redis is not None:
            self.redis.delete(f"line:user:{user_id}")
        if state:
            relatives = state.get("images", [])
            if not isinstance(relatives, list):
                relatives = []
            legacy = state.get("image_path")
            if isinstance(legacy, str):
                relatives.append(legacy)
            for relative in relatives:
                path = self._input_path(relative)
                if path and path.is_file():
                    try:
                        path.unlink()
                    except OSError:
                        self.logger.warning("LINE pending image cleanup failed")

    def _empty_session(self) -> dict[str, Any]:
        return {"images": [], "prompt": None, "created_at": _iso_now()}

    def _load_session(self, user_id: str) -> dict[str, Any]:
        key = f"line:user:{user_id}"
        state = self._redis_json(key)
        if state is None:
            if self.redis is not None and self.redis.get(key) is not None:
                self.redis.delete(key)
            return self._empty_session()
        images = state.get("images")
        created_at = _parse_created_at(state.get("created_at"))
        prompt = state.get("prompt")
        if (
            state.get("state") == "i2v_wait_prompt"
            or not isinstance(images, list)
            or len(images) > MAX_PENDING_IMAGES
            or not created_at
            or (prompt is not None and not isinstance(prompt, str))
        ):
            self._delete_pending(user_id, state)
            return self._empty_session()
        paths = [self._input_path(item) for item in images]
        try:
            invalid_paths = any(path is None or not path.is_file() or path.stat().st_size <= 0 for path in paths)
        except OSError:
            invalid_paths = True
        if invalid_paths:
            self._delete_pending(user_id, state)
            return self._empty_session()
        state = {"images": images, "prompt": prompt, "created_at": state["created_at"]}
        self.redis.expire(key, LINE_PENDING_IMAGE_TTL)
        return state

    def _save_session(self, user_id: str, state: dict[str, Any]) -> None:
        if self.redis is None:
            raise RuntimeError("Redis unavailable")
        state.setdefault("created_at", _iso_now())
        self.redis.setex(f"line:user:{user_id}", LINE_PENDING_IMAGE_TTL, json.dumps(state))

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

    def push_image(self, user_id: str, image_url: str, preview_url: str) -> bool:
        if not user_id or not image_url.startswith("https://") or not preview_url.startswith("https://"):
            return False
        return self._line_request(
            "POST",
            LINE_PUSH_URL,
            {
                "to": user_id,
                "messages": [{
                    "type": "image",
                    "originalContentUrl": image_url,
                    "previewImageUrl": preview_url,
                }],
            },
        )

    def _resolve_workflow(self, workflow_id: str):
        if workflow_id not in {IMAGE_WORKFLOW_ID, VIDEO_WORKFLOW_ID}:
            return None
        try:
            resolution = resolve_workflow_request(self.runtime.project_root, workflow_id)
        except (KeyError, ValueError, OSError):
            return None
        entry = resolution.entry
        api_path = self.runtime.project_root / "ComfyUIworkflow_api" / entry.file
        if resolution.workflow_id != workflow_id or not entry.enabled or not entry.path.is_file() or not api_path.is_file():
            return None
        return resolution

    def _image_data_uri(self, path: Path) -> str:
        data = path.read_bytes()
        if not data or len(data) > LINE_MAX_IMAGE_BYTES:
            raise ValueError("image size is invalid")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    def _store_job_mapping(self, job_id: str, user_id: str, output_type: str, workflow_id: str) -> None:
        if self.redis is None:
            raise RuntimeError("Redis unavailable")
        self.redis.hset(
            f"line:job:{job_id}",
            mapping={
                "job_id": job_id,
                "user_id": user_id,
                "output_type": output_type,
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

    def submit_output(self, user_id: str, prompt: str, output_type: str, image_paths: list[str]) -> bool | None:
        workflow_id = IMAGE_WORKFLOW_ID if output_type == "image" else VIDEO_WORKFLOW_ID
        resolution = self._resolve_workflow(workflow_id)
        if resolution is None:
            return None
        try:
            paths = [self._input_path(value) for value in image_paths]
            if any(path is None or not path.is_file() for path in paths):
                return False
            if output_type == "image":
                images = [self._image_data_uri(path) for path in paths]
            else:
                if len(paths) > MAX_VIDEO_IMAGES:
                    return False
                images = {}
                if paths:
                    images["first_frame"] = self._image_data_uri(paths[0])
                if len(paths) == 2:
                    images["last_frame"] = self._image_data_uri(paths[1])
            payload, status = self.runtime.job_service.submit(
                {
                    "workflow": resolution.workflow_id,
                    "prompt": prompt,
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
            self._store_job_mapping(job_id, user_id, output_type, resolution.workflow_id)
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

    def stage_image(self, message_id: str) -> str | None:
        downloaded = self._download_image(message_id)
        if downloaded is None:
            return None
        data, extension = downloaded
        root = Path(self.runtime.upload_folder).resolve()
        root.mkdir(parents=True, exist_ok=True)
        filename = f"line_{uuid.uuid4().hex}{extension}"
        path = root / filename
        try:
            path.write_bytes(data)
            return path.relative_to(root).as_posix()
        except (OSError, ValueError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def reply_with_output_choice(
        self,
        reply_token: Any,
        image_only: bool = False,
        text: str = REPLY_CHOOSE_OUTPUT,
    ) -> bool:
        if not isinstance(reply_token, str) or not (1 <= len(reply_token) <= 2048):
            return False
        choices = [("圖片", "output=image")]
        if not image_only:
            choices.append(("影片", "output=video"))
        items = [{
            "type": "action",
            "action": {"type": "postback", "label": label, "data": data, "displayText": label},
        } for label, data in choices]
        return self._line_request(
            "POST",
            LINE_REPLY_URL,
            {
                "replyToken": reply_token,
                "messages": [{
                    "type": "text",
                    "text": text,
                    "quickReply": {"items": items},
                }],
            },
        )

    def _event_user_id(self, event: dict[str, Any]) -> str | None:
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        return _safe_identifier(source.get("userId"))

    def handle_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        user_id = self._event_user_id(event)
        if not user_id:
            return
        reply_token = event.get("replyToken")
        if event.get("type") == "postback":
            postback = event.get("postback") if isinstance(event.get("postback"), dict) else {}
            data = postback.get("data")
            if isinstance(data, str) and data in {"output=image", "output=video"}:
                self._handle_output_choice(user_id, data.partition("=")[2], reply_token)
            return
        if event.get("type") != "message":
            return
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        message_type = message.get("type")
        if message_type == "image":
            message_id = _safe_identifier(message.get("id"))
            session = self._load_session(user_id)
            if len(session["images"]) >= MAX_PENDING_IMAGES:
                if session["prompt"]:
                    self.reply_with_output_choice(reply_token, image_only=True, text=REPLY_IMAGE_LIMIT)
                else:
                    self.reply(reply_token, REPLY_IMAGE_LIMIT)
                return
            relative_path = self.stage_image(message_id) if message_id else None
            if relative_path is None:
                self.reply(reply_token, REPLY_IMAGE_FAILED)
                return
            session["images"].append(relative_path)
            self._save_session(user_id, session)
            if session["prompt"]:
                self.reply_with_output_choice(
                    reply_token,
                    len(session["images"]) == MAX_PENDING_IMAGES,
                    REPLY_IMAGE_RECEIVED.format(count=len(session["images"])),
                )
            else:
                self.reply(reply_token, REPLY_IMAGE_RECEIVED.format(count=len(session["images"])))
            return
        if message_type != "text":
            return
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        session = self._load_session(user_id)
        if text == "取消":
            self._delete_pending(user_id, session)
            self.reply(reply_token, REPLY_CANCELLED)
            return
        text = text.strip()
        session["prompt"] = text
        self._save_session(user_id, session)
        self.reply_with_output_choice(reply_token, len(session["images"]) == MAX_PENDING_IMAGES)

    def _handle_output_choice(self, user_id: str, output_type: str, reply_token: Any) -> None:
        session = self._load_session(user_id)
        prompt = session.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self.reply(reply_token, REPLY_NEED_PROMPT)
            return
        if output_type == "video" and len(session["images"]) > MAX_VIDEO_IMAGES:
            self.reply(reply_token, REPLY_VIDEO_IMAGE_LIMIT)
            return
        busy = self.has_active_job(user_id)
        submitted = self.submit_output(user_id, prompt, output_type, session["images"])
        if submitted is None:
            self.reply(reply_token, REPLY_UNAVAILABLE)
            return
        if not submitted:
            self.reply(reply_token, REPLY_GENERATION_FAILED)
            return
        self._delete_pending(user_id, session)
        self.reply(reply_token, REPLY_QUEUED if busy else REPLY_GENERATING)

    def process_webhook(self, raw_body: bytes, signature: str | None) -> tuple[dict[str, Any], int]:
        if len(raw_body) > LINE_MAX_WEBHOOK_BYTES:
            return {"error": "Request too large"}, 413
        if not verify_line_signature(raw_body, signature, LINE_CHANNEL_SECRET):
            return {"error": "Invalid signature"}, 401
        if not self.configured(require_public_url=True):
            return {"error": REPLY_UNAVAILABLE}, 503
        try:
            redis = self.redis
            if redis is None or not redis.ping():
                return {"error": REPLY_UNAVAILABLE}, 503
        except Exception:
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
                try:
                    if not redis.ping():
                        return {"error": REPLY_UNAVAILABLE}, 503
                except Exception:
                    return {"error": REPLY_UNAVAILABLE}, 503
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

    def _create_preview(self, preview_path: Path, image_path: Path | None = None, video_path: Path | None = None) -> bool:
        try:
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image, ImageDraw

            if image_path is None:
                # LINE sizes the video bubble from the preview, so match the video's aspect ratio.
                video_size = _mp4_size(video_path) if video_path else None
                if video_size:
                    scale = 1280 / max(video_size)
                    width, height = (max(64, round(side * scale)) for side in video_size)
                else:
                    width, height = 1280, 704
                image = Image.new("RGB", (width, height), (15, 23, 42))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, width - 1, height - 1), outline=(96, 165, 250), width=8)
                cx, cy, r = width // 2, height // 2, min(width, height) // 8
                draw.polygon(((cx - r, cy - r), (cx - r, cy + r), (cx + r, cy)), fill=(255, 255, 255))
                image.save(preview_path, format="JPEG", quality=88, optimize=True)
            else:
                with Image.open(image_path) as source:
                    source.thumbnail((1024, 1024))
                    if source.mode in {"RGBA", "LA"} or "transparency" in source.info:
                        rgba = source.convert("RGBA")
                        image = Image.new("RGB", rgba.size, "white")
                        image.paste(rgba, mask=rgba.getchannel("A"))
                    else:
                        image = source.convert("RGB")
                quality = 85
                while True:
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=quality, optimize=True)
                    if buffer.tell() <= LINE_MAX_PREVIEW_BYTES:
                        preview_path.write_bytes(buffer.getvalue())
                        break
                    if quality > 40:
                        quality -= 15
                        continue
                    width, height = image.size
                    if max(width, height) <= 64:
                        return False
                    image.thumbnail((max(1, width // 2), max(1, height // 2)))
                    quality = 70
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
                    output_type = str(mapping.get("output_type") or "video")
                    output_path = self._output_path(output_name, output_type)
                    size_limit = LINE_MAX_IMAGE_BYTES if output_type == "image" else LINE_MAX_VIDEO_BYTES
                    if (
                        output_type in {"image", "video"}
                        and output_path
                        and output_path.is_file()
                        and 0 < output_path.stat().st_size <= size_limit
                    ):
                        token = secrets.token_urlsafe(32)
                        preview_name = f"line_preview_{token}.jpg"
                        preview_path = self._preview_path(preview_name)
                        image_path = output_path if output_type == "image" else None
                        video_path = output_path if output_type == "video" else None
                        if preview_path is None or not self._create_preview(preview_path, image_path, video_path):
                            self._notify_failure(key, user_id)
                            continue
                        token_record = {
                            "job_id": job_id,
                            "kind": output_type,
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
                        pushed = (
                            self.push_image(user_id, public_url, preview_url)
                            if output_type == "image"
                            else self.push_video(user_id, public_url, preview_url)
                        )
                        if pushed:
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
        kind = record.get("kind")
        output_name = record.get("output_name")
        status = canonical_status(self._status_record(job_id).get("status", ""))
        job_mapping = _normalize_hash(self.redis.hgetall(f"line:job:{job_id}"))
        path = self._output_path(output_name, kind)
        size_limit = LINE_MAX_IMAGE_BYTES if kind == "image" else LINE_MAX_VIDEO_BYTES
        if (
            not job_id
            or kind not in {"image", "video"}
            or job_mapping.get("job_id") != job_id
            or job_mapping.get("output_type") != kind
            or status != "completed"
            or path is None
            or not path.is_file()
            or not 0 < path.stat().st_size <= size_limit
        ):
            return jsonify({"error": "Not found"}), 404
        if kind == "image":
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            filename = "image.png" if mime == "image/png" else "image.jpg"
        else:
            mime, filename = "video/mp4", "video.mp4"
        response = send_file(path, mimetype=mime, as_attachment=True, download_name=filename, conditional=True)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def preview(self, token: str):
        if not TOKEN_RE.fullmatch(token or "") or self.redis is None:
            return jsonify({"error": "Not found"}), 404
        record = self._redis_json(f"line:download:{token}")
        if not record:
            return jsonify({"error": "Not found"}), 404
        job_id = str(record.get("job_id") or "")
        kind = record.get("kind")
        preview_name = record.get("preview_name")
        status = canonical_status(self._status_record(job_id).get("status", ""))
        job_mapping = _normalize_hash(self.redis.hgetall(f"line:job:{job_id}"))
        path = self._preview_path(preview_name)
        if (
            not job_id
            or kind not in {"image", "video"}
            or job_mapping.get("job_id") != job_id
            or job_mapping.get("output_type") != kind
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
