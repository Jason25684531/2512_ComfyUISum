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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, jsonify, request, send_file

import config as line_config
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
    LINE_MUSIC_ENABLED,
    LINE_NOTIFICATION_RETRY_LIMIT,
    LINE_PENDING_IMAGE_TTL,
    LINE_PUBLIC_BASE_URL,
)
from line_music_service import MUSIC_ID_RE, LineMusicService, MusicLibrary, normalize
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
# Pre-preset MiniMax size lists; order matters (first exact ratio match wins).
LINE_VIDEO_WIDTHS = (1024, 1344, 768, 1920, 864, 1536, 576)
LINE_VIDEO_HEIGHTS = (1024, 768, 1344, 1088, 864, 1536, 1280)

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
REPLY_MUSIC_FALLBACK = "配樂失敗，先提供原始影片。"
REPLY_MUSIC_TIMEOUT = "選曲已逾時，已開始生成不配樂影片。"
REPLY_MUSIC_CHOOSE = "請先完成配樂選擇，或輸入「不要音樂」開始生成、「取消」取消本次請求。"


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
    """Read the first video track's display size without spawning a media process."""
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


def _generation_dimensions(entry, prompt: str, paths: list[Path]) -> dict[str, Any]:
    text = normalize(prompt)
    ratio = re.search(r"(?<!\d)(9\s*[:/x×]\s*20|9\s*[:/x×]\s*16|16\s*[:/x×]\s*9|1\s*[:/x×]\s*1|2\s*[:/x×]\s*3|3\s*[:/x×]\s*2)(?!\d)", text)
    if ratio:
        width, height = map(int, re.split(r"\s*[:/x×]\s*", ratio.group(1)))
    elif re.search(r"\bmobile\b|\bphone\b|手機(?:比例|版|直式|尺寸|畫面)?", text):
        width, height = 9, 20
    elif re.search(r"\bvertical\b|portrait orientation|直式|直向|縱向|竖版|竖屏", text):
        width, height = 9, 16
    elif re.search(r"\bhorizontal\b|landscape orientation|橫式|橫向|横版|横屏", text):
        width, height = 16, 9
    elif paths:
        from PIL import Image, ImageOps

        with Image.open(paths[0]) as image:
            width, height = ImageOps.exif_transpose(image).size
    else:
        return {}
    if entry.output_type == "image":
        if width * 20 == height * 9:
            # Sunburst requires 16-aligned dimensions and at least 655,360 pixels.
            return {"size": "custom", "custom_width": 576, "custom_height": 1280}
        sizes = [tuple(map(int, size.split("x"))) for size in entry.choices["size"] if size != "custom"]
    else:
        # MiniMax now takes free-form 32-aligned width/height (choices only hold 16:9 presets),
        # so LINE keeps its own orientation-aware list.
        widths = entry.choices.get("width") or LINE_VIDEO_WIDTHS
        sizes = [(w, h) for w in widths for h in entry.choices.get("height") or LINE_VIDEO_HEIGHTS]
    chosen_width, chosen_height = min(sizes, key=lambda size: abs(size[0] / size[1] - width / height))
    if entry.output_type == "image":
        return {"size": f"{chosen_width}x{chosen_height}"}
    return {"width": chosen_width, "height": chosen_height}


class LineAdapter:
    def __init__(self, runtime):
        self.runtime = runtime
        self.music: LineMusicService | None = None

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
        request_id = state.get("music_request_id")
        state = {"images": images, "prompt": prompt, "created_at": state["created_at"]}
        if isinstance(request_id, str) and re.fullmatch(r"[a-f0-9]{32}", request_id):
            state["music_request_id"] = request_id
        ttl = LINE_JOB_MAPPING_TTL + line_config.LINE_MUSIC_STATE_TTL if "music_request_id" in state else LINE_PENDING_IMAGE_TTL
        self.redis.expire(key, ttl)
        return state

    def _save_session(self, user_id: str, state: dict[str, Any]) -> None:
        if self.redis is None:
            raise RuntimeError("Redis unavailable")
        state.setdefault("created_at", _iso_now())
        ttl = LINE_JOB_MAPPING_TTL + line_config.LINE_MUSIC_STATE_TTL if "music_request_id" in state else LINE_PENDING_IMAGE_TTL
        self.redis.setex(f"line:user:{user_id}", ttl, json.dumps(state))

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

    def push_video(self, user_id: str, video_url: str, preview_url: str, *, text: str | None = None) -> bool:
        if not user_id or not video_url.startswith("https://") or not preview_url.startswith("https://"):
            return False
        messages = [{"type": "video", "originalContentUrl": video_url, "previewImageUrl": preview_url}]
        if text:
            messages.insert(0, {"type": "text", "text": text})
        return self._line_request(
            "POST",
            LINE_PUSH_URL,
            {
                "to": user_id,
                "messages": messages,
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

    def _store_job_mapping(
        self, job_id: str, user_id: str, output_type: str, workflow_id: str,
        *, music_id: str | None = None, music_mode: str = "mix",
    ) -> None:
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
                **({"music_id": music_id, "music_mode": music_mode, "music_state": "pending"} if music_id else {}),
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

    def submit_output(
        self, user_id: str, prompt: str, output_type: str, image_paths: list[str],
        *, music_id: str | None = None, music_mode: str = "mix",
    ) -> bool | None:
        if music_id is not None and (output_type != "video" or not self.music
                or music_id not in self.music.library.tracks or music_mode not in {"mix", "replace"}):
            return False
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
            data = {"workflow": resolution.workflow_id, "prompt": prompt, "images": images}
            dimensions = _generation_dimensions(resolution.entry, prompt, paths)
            if output_type == "video":
                dimensions["duration"] = 10
            internal_extra_params = dimensions if dimensions.get("size") == "custom" else None
            if dimensions and internal_extra_params is None:
                data["extra_params"] = dimensions
            payload, status = self.runtime.job_service.submit(
                data,
                request_id=str(uuid.uuid4()),
                user_label="line",
                internal_extra_params=internal_extra_params,
            )
        except Exception:
            self.logger.exception("LINE job submission failed")
            return False
        job_id = payload.get("job_id") if isinstance(payload, dict) else None
        if status >= 400 or not isinstance(job_id, str) or not job_id:
            return False
        try:
            self._store_job_mapping(job_id, user_id, output_type, resolution.workflow_id,
                                    music_id=music_id, music_mode=music_mode)
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
            elif self.music and isinstance(data, str) and re.fullmatch(r"music=(yes|no):[a-f0-9]{32}", data):
                choice, request_id = data.removeprefix("music=").split(":")
                state = self._load_music_session(user_id)
                if state and state["request_id"] == request_id:
                    self._handle_music_text(user_id, "要配樂" if choice == "yes" else "不要音樂", reply_token)
                else:
                    self.reply(reply_token, "選曲已結束，請先輸入提示詞並選擇影片。")
            return
        if event.get("type") != "message":
            return
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        message_type = message.get("type")
        if message_type == "image":
            message_id = _safe_identifier(message.get("id"))
            session = self._load_session(user_id)
            if self.music and self._load_music_session(user_id):
                self.reply(reply_token, REPLY_MUSIC_CHOOSE)
                return
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
            state = self._load_music_session(user_id) if self.music else None
            if state and self.redis.get(f"line:music:submit:{state['request_id']}"):
                self.reply(reply_token, REPLY_GENERATING)
                return
            self._delete_pending(user_id, session)
            if self.music:
                self.redis.delete(f"line:music:{user_id}")
            self.reply(reply_token, REPLY_CANCELLED)
            return
        text = text.strip()
        if self.music and self._handle_music_text(user_id, text, reply_token):
            return
        session.pop("music_request_id", None)
        session["prompt"] = text
        self._save_session(user_id, session)
        self.reply_with_output_choice(reply_token, len(session["images"]) == MAX_PENDING_IMAGES)

    def _job_mapping(self, job_id: str) -> dict:
        return _normalize_hash(self.redis.hgetall(f"line:job:{job_id}"))

    def _music_video(self, user_id: str, job_id: str) -> Path | None:
        mapping = self._job_mapping(job_id)
        if (not _safe_identifier(job_id) or mapping.get("job_id") != job_id
                or mapping.get("user_id") != user_id or mapping.get("output_type") != "video"
                or mapping.get("notification_state") in {"delivered", "failed", "notified_failure"}):
            return None
        status = self._status_record(job_id)
        if canonical_status(status.get("status", "")) != "completed":
            return None
        path = self._output_path(self._output_name(status, job_id))
        try:
            return path if path and path.is_file() and 0 < path.stat().st_size <= LINE_MAX_VIDEO_BYTES else None
        except OSError:
            return None

    def _load_music_session(self, user_id: str) -> dict | None:
        key = f"line:music:{user_id}"
        state = self._redis_json(key)
        if state is None:
            if self.redis.get(key) is not None:
                self.redis.delete(key)
            return None
        candidates = state.get("candidates")
        created = _parse_created_at(state.get("created_at"))
        valid = (
            isinstance(state.get("state"), str) and state["state"] in {"music_offer", "music_select"}
            and isinstance(state.get("mode"), str) and state["mode"] in {"mix", "replace"}
            and isinstance(state.get("request_id"), str) and re.fullmatch(r"[a-f0-9]{32}", state["request_id"])
            and isinstance(candidates, list) and len(candidates) <= 5
            and all(isinstance(item, str) and MUSIC_ID_RE.fullmatch(item) for item in candidates)
            and isinstance(state.get("created_at"), str) and created is not None
            and set(state) == {"state", "mode", "request_id", "candidates", "created_at"}
        )
        if not valid:
            self.redis.delete(key)
            return None
        return state

    def _save_music_session(self, user_id: str, state: dict) -> None:
        # Keep data past the decision deadline so the monitor can submit without a new webhook.
        ttl = self.music.settings.LINE_MUSIC_STATE_TTL + LINE_JOB_MAPPING_TTL
        self.redis.setex(f"line:music:{user_id}", ttl, json.dumps(state))

    def _music_expired(self, state: dict) -> bool:
        settings = self.music.settings if self.music else line_config
        return _now() >= _parse_created_at(state["created_at"]) + timedelta(seconds=settings.LINE_MUSIC_STATE_TTL)

    def _reply_music_offer(self, reply_token, state: dict) -> None:
        if not isinstance(reply_token, str) or not (1 <= len(reply_token) <= 2048):
            return
        items = [{"type": "action", "action": {
            "type": "postback", "label": label, "displayText": label,
            "data": f"music={choice}:{state['request_id']}",
        }} for label, choice in (("要配樂", "yes"), ("不用配樂", "no"))]
        self._line_request("POST", LINE_REPLY_URL, {"replyToken": reply_token, "messages": [{
            "type": "text", "text": "是否加入配樂？逾時未完成選曲，將不配樂並開始生成。",
            "quickReply": {"items": items},
        }]})

    def _finish_music_choice(self, user_id: str, state: dict, reply_token=None, music_id=None) -> None:
        if self._load_music_session(user_id) != state:
            return
        # One decision, whether made by a webhook or the timeout monitor, submits at most once.
        # ponytail: claim/submission are not transactional; check for an existing job before clearing a stranded claim.
        if not self.redis.set(f"line:music:submit:{state['request_id']}", "1", nx=True, ex=LINE_JOB_MAPPING_TTL):
            return
        session = self._load_session(user_id)
        if session.get("music_request_id") != state["request_id"] or not session["prompt"]:
            self.redis.delete(f"line:music:{user_id}")
            return
        expired = self._music_expired(state)
        if not self.music or music_id not in self.music.library.tracks:
            music_id = None
        self._submit_session(user_id, "video", session, reply_token,
                             music_id=None if expired else music_id, music_mode=state["mode"], timed_out=expired)

    def _expire_music_choices(self) -> None:
        for raw_key in self.redis.scan_iter(match="line:music:*"):
            user_id = _safe_identifier(str(_decode_redis(raw_key)).removeprefix("line:music:"))
            if user_id:
                state = self._load_music_session(user_id)
                if state and self._music_expired(state):
                    self._finish_music_choice(user_id, state)

    def _handle_music_text(self, user_id: str, text: str, reply_token) -> bool:
        state = self._load_music_session(user_id)
        if state and self.redis.get(f"line:music:submit:{state['request_id']}"):
            self.reply(reply_token, REPLY_GENERATING)
            return True
        if state and self._music_expired(state):
            self._finish_music_choice(user_id, state, reply_token)
            return True
        playlist = text in {"音樂", "音樂清單", "配樂", "要配樂"}
        search = text.startswith("找") and (state is not None or any(word in text for word in ("音樂", "配樂", "歌")))
        number = normalize(text)
        selection = state is not None and bool(re.fullmatch(r"[0-9]+", number))
        mode = state is not None and text in {"原聲加音樂", "只要音樂"}
        if state is not None and text in {"不要音樂", "不用配樂"}:
            self._finish_music_choice(user_id, state, reply_token)
            return True
        if state is None:
            if not (playlist or search):
                return False
            self.reply(reply_token, "請先輸入提示詞並選擇影片，再選擇配樂。")
            return True
        if not self.music.library.tracks:
            self._finish_music_choice(user_id, state, reply_token)
            return True
        if playlist or search:
            tracks = self.music.library.playlist() if playlist else self.music.library.search(text)
            state.update(state="music_select", candidates=[track["id"] for track in tracks])
            self._save_music_session(user_id, state)
            listing = "\n".join(f"{i}. {t['title']}｜{t['genre']} / {t['mood']} / {t['tempo']}" for i, t in enumerate(tracks, 1))
            self.reply(reply_token, (listing + "\n輸入序號選曲；可輸入「只要音樂」切換模式，或「不要音樂」直接生成。")
                       if listing else "找不到符合的音樂，可輸入「音樂」查看全部。")
        elif mode:
            state["mode"] = "mix" if text == "原聲加音樂" else "replace"
            self._save_music_session(user_id, state)
            self.reply(reply_token, "已設定為原聲加音樂。" if state["mode"] == "mix" else "已設定為只要音樂。")
        elif selection:
            count = len(state["candidates"])
            if len(number) > 2 or not 1 <= int(number) <= count:
                self.reply(reply_token, f"請輸入 1～{count} 選擇音樂。" if count else "請重新輸入「音樂」選曲。")
            else:
                self._finish_music_choice(user_id, state, reply_token, state["candidates"][int(number) - 1])
        else:
            self.reply(reply_token, REPLY_MUSIC_CHOOSE)
        return True

    def _handle_output_choice(self, user_id: str, output_type: str, reply_token: Any) -> None:
        session = self._load_session(user_id)
        prompt = session.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self.reply(reply_token, REPLY_NEED_PROMPT)
            return
        if output_type == "video" and len(session["images"]) > MAX_VIDEO_IMAGES:
            self.reply(reply_token, REPLY_VIDEO_IMAGE_LIMIT)
            return
        if self.music:
            state = self._load_music_session(user_id)
            if state:
                if self._music_expired(state):
                    self._finish_music_choice(user_id, state, reply_token)
                else:
                    self.reply(reply_token, REPLY_MUSIC_CHOOSE)
                return
            if output_type == "video" and self.music.library.tracks:
                request_id = secrets.token_hex(16)
                state = {"state": "music_offer", "request_id": request_id, "candidates": [],
                         "mode": "mix", "created_at": _iso_now()}
                session["music_request_id"] = request_id
                self._save_session(user_id, session)
                self._save_music_session(user_id, state)
                self._reply_music_offer(reply_token, state)
                return
        self._submit_session(user_id, output_type, session, reply_token)

    def _submit_session(self, user_id, output_type, session, reply_token=None,
                        *, music_id=None, music_mode="mix", timed_out=False) -> None:
        notify = lambda text: self.reply(reply_token, text) if reply_token else self.push(user_id, text)
        busy = self.has_active_job(user_id)
        submitted = self.submit_output(user_id, session["prompt"], output_type, session["images"],
                                       music_id=music_id, music_mode=music_mode)
        self.redis.delete(f"line:music:{user_id}")
        if not submitted:
            session.pop("music_request_id", None)
            self._save_session(user_id, session)
            notify(REPLY_UNAVAILABLE if submitted is None else REPLY_GENERATION_FAILED)
            return
        self._delete_pending(user_id, session)
        notify(REPLY_MUSIC_TIMEOUT if timed_out else REPLY_QUEUED if busy else REPLY_GENERATING)

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

    def _create_media_token(self, job_id: str, output_name: str, kind: str, output_path: Path):
        token = secrets.token_urlsafe(32)
        preview_name = f"line_preview_{token}.jpg"
        preview_path = self._preview_path(preview_name)
        try:
            if preview_path is None or not self._create_preview(
                preview_path, output_path if kind == "image" else None, output_path if kind == "video" else None,
            ):
                raise ValueError("preview_failed")
            self.redis.setex(f"line:download:{token}", LINE_DOWNLOAD_TOKEN_TTL, json.dumps({
                "job_id": job_id, "kind": kind, "output_name": output_name,
                "preview_name": preview_name, "created_at": _iso_now(),
            }))
            # Downloads and previews require both records for the token's entire lifetime.
            for key in (f"line:job:{job_id}", f"job:status:{job_id}"):
                self.redis.expire(key, LINE_DOWNLOAD_TOKEN_TTL, gt=True)
        except Exception:
            if preview_path:
                preview_path.unlink(missing_ok=True)
            try:
                self.redis.delete(f"line:download:{token}")
            except Exception:
                self.logger.warning("LINE media token cleanup unavailable")
            raise
        return token, preview_path

    def poll_once(self) -> int:
        if self.redis is None or not self.configured(require_public_url=True):
            return 0
        self._expire_music_choices()
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
                    original_name, original_path = output_name, output_path
                    text = None
                    if output_type == "video" and mapping.get("music_id"):
                        music_state = mapping.get("music_state", "pending")
                        if (self.music and music_state not in {"ready", "fallback"}
                                and output_path and output_path.is_file()
                                and 0 < output_path.stat().st_size <= size_limit):
                            try:
                                self.music.schedule(user_id, job_id)
                            except Exception:
                                self.logger.warning("LINE music scheduling failed")
                                self.redis.hset(key, mapping={"music_state": "fallback"})
                            continue
                        music_path = self._output_path(mapping.get("music_output")) if music_state == "ready" else None
                        if (music_path and music_path.is_file()
                                and re.fullmatch(r"line_music_[a-f0-9]{24}\.mp4", music_path.name)
                                and 0 < music_path.stat().st_size <= LINE_MAX_VIDEO_BYTES):
                            output_name, output_path = mapping["music_output"], music_path
                            text = "配樂影片已完成。"
                        else:
                            text = REPLY_MUSIC_FALLBACK
                            self.redis.hset(key, mapping={"music_state": "fallback"})
                    if (
                        output_type in {"image", "video"}
                        and output_path
                        and output_path.is_file()
                        and 0 < output_path.stat().st_size <= size_limit
                    ):
                        try:
                            token, preview_path = self._create_media_token(job_id, output_name, output_type, output_path)
                        except (OSError, ValueError):
                            if output_path == original_path:
                                self._notify_failure(key, user_id)
                                continue
                            output_path.unlink(missing_ok=True)
                            self.redis.hset(key, mapping={"music_state": "fallback", "music_output": ""})
                            text = REPLY_MUSIC_FALLBACK
                            if (not original_path or not original_path.is_file()
                                    or not 0 < original_path.stat().st_size <= size_limit):
                                self._notify_failure(key, user_id)
                                continue
                            try:
                                token, preview_path = self._create_media_token(job_id, original_name, output_type, original_path)
                            except (OSError, ValueError):
                                self._notify_failure(key, user_id)
                                continue
                        public_url = f"{LINE_PUBLIC_BASE_URL}/line/download/{token}"
                        preview_url = f"{LINE_PUBLIC_BASE_URL}/line/preview/{token}"
                        pushed = (
                            self.push_image(user_id, public_url, preview_url)
                            if output_type == "image"
                            else self.push_video(user_id, public_url, preview_url, **({"text": text} if text else {}))
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
    if LINE_MUSIC_ENABLED:
        library = MusicLibrary(line_config.LINE_MUSIC_LIBRARY_DIR, limit=line_config.LINE_MUSIC_RESULT_LIMIT, logger=runtime.logger)
        adapter.music = LineMusicService(adapter, library, line_config)
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
