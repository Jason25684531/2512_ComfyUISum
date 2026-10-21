"""Local music metadata and Backend-only post-processing coordination."""
from __future__ import annotations

import json
import logging
import math
import re
import secrets
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from media_postprocess import MAX_AUDIO_BYTES, add_music
from shared.path_utils import resolve_storage_path


MUSIC_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")
SYNONYMS = {
    "高速": ("fast", "energetic"), "快": ("fast",),
    "科技": ("futuristic", "electronic", "cyber"), "未來": ("futuristic", "electronic", "cyber"),
    "賽車": ("racing",), "黑暗": ("dark",), "電影": ("cinematic",),
    "平靜": ("calm", "ambient"), "放鬆": ("calm", "ambient"),
    "歡樂": ("upbeat", "happy"), "開心": ("upbeat", "happy"), "史詩": ("epic",), "溫柔": ("soft",),
}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower().strip()


class MusicLibrary:
    def __init__(self, root: Path, *, limit: int = 3, logger=None):
        self.root = Path(root).resolve()
        self.limit = limit
        self.logger = logger or logging.getLogger(__name__)
        self.tracks: dict[str, dict] = {}
        try:
            manifest = resolve_storage_path(self.root, "library.json")
            if manifest.stat().st_size > 2 * 1024 * 1024:
                raise ValueError
            data = json.loads(manifest.read_text(encoding="utf-8"))
            tracks = data["tracks"]
            if not isinstance(tracks, list):
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            self.logger.warning("LINE music library unavailable")
            return
        for track in tracks:
            if self._valid(track):
                self.tracks[track["id"]] = dict(track)
            else:
                track_id = track.get("id") if isinstance(track, dict) else None
                safe_id = track_id if isinstance(track_id, str) and MUSIC_ID_RE.fullmatch(track_id) else "invalid"
                self.logger.warning("LINE music track skipped id=%s", safe_id)

    def _valid(self, track) -> bool:
        if not isinstance(track, dict):
            return False
        track_id = track.get("id")
        if not isinstance(track_id, str) or not MUSIC_ID_RE.fullmatch(track_id) or track_id in self.tracks:
            return False
        for field, length in (("title", 80), ("file", 512), ("genre", 80), ("mood", 80), ("tempo", 80)):
            value = track.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > length or any(ord(c) < 32 for c in value):
                return False
        tags = track.get("tags")
        if not isinstance(tags, list) or len(tags) > 20 or any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 32 or any(ord(c) < 32 for c in tag) for tag in tags
        ):
            return False
        if "duration" in track:
            value = track["duration"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                return False
        for field in ("artist", "license", "attribution"):
            if field in track and (not isinstance(track[field], str) or len(track[field]) > 500):
                return False
        return self._path(track) is not None

    def _path(self, track: dict) -> Path | None:
        try:
            filename = track["file"]
            if ":" in filename or Path(filename).suffix.lower() not in {".mp3", ".wav"}:
                return None
            path = resolve_storage_path(self.root, filename)
            if path.suffix.lower() in {".mp3", ".wav"} and path.is_file() and 0 < path.stat().st_size <= MAX_AUDIO_BYTES:
                return path
        except (OSError, ValueError, RuntimeError):
            pass
        return None

    def get(self, music_id: str) -> Path | None:
        track = self.tracks.get(music_id)
        return self._path(track) if track else None

    def playlist(self) -> list[dict]:
        # 「音樂」列出全部曲目（最多 99 首，對齊兩位數選號）；limit 只限制搜尋結果數量
        return [self.tracks[key] for key in sorted(self.tracks)[:99]]

    def search(self, query: str) -> list[dict]:
        query = normalize(query)
        cleaned = re.sub(r"一首|一個|配樂|音樂|[找的歌感、，]", "", query).strip()
        terms = set(re.findall(r"[a-z0-9]+", cleaned))
        terms.update(term for key, values in SYNONYMS.items() if key in query for term in values)
        if cleaned:
            terms.add(cleaned)

        def matches(value):
            value = normalize(value)
            return any(term in value for term in terms) or bool(value and value in cleaned)

        scores = []
        for track in self.tracks.values():
            score = 100 if normalize(track["title"]) in {query, cleaned} else 0
            if matches(track["title"]):
                score += 30
            score += sum(10 for tag in track["tags"] if matches(tag))
            score += sum(6 for field in ("genre", "mood") if matches(track[field]))
            if matches(track["tempo"]):
                score += 4
            if score:
                scores.append((-score, track["id"]))
        return [self.tracks[key] for _, key in sorted(scores)[:self.limit]]


class LineMusicService:
    def __init__(self, adapter, library: MusicLibrary, settings):
        self.adapter = adapter
        self.library = library
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="line-music")
        # Keep waiting jobs in their existing LINE mappings, never in an expiring in-memory queue.
        self.available = threading.BoundedSemaphore(1)

    def _lease(self, user_id: str, owner: str, *, release=False) -> bool:
        action = "redis.call('del', KEYS[1])" if release else "redis.call('expire', KEYS[1], ARGV[2])"
        return bool(self.adapter.redis.eval(
            f"if redis.call('get', KEYS[1]) == ARGV[1] then {action}; return 1 end; return 0",
            1, f"line:music:lock:{user_id}", owner,
            self.settings.LINE_MUSIC_FFMPEG_TIMEOUT + 60,
        ))

    def schedule(self, user_id: str, job_id: str) -> bool:
        if not self.available.acquire(blocking=False):
            return False
        owner = secrets.token_hex(16)
        try:
            if not self.adapter.redis.set(f"line:music:lock:{user_id}", owner, nx=True,
                                          ex=self.settings.LINE_MUSIC_FFMPEG_TIMEOUT + 60):
                self.available.release()
                return False
            self.executor.submit(self._process, user_id, job_id, owner)
        except Exception:
            try:
                self._lease(user_id, owner, release=True)
            finally:
                self.available.release()
            raise
        return True

    def _process(self, user_id: str, job_id: str, owner: str):
        adapter, settings = self.adapter, self.settings
        output = None
        saved = False
        try:
            if not self._lease(user_id, owner):
                return
            mapping = adapter._job_mapping(job_id)
            video = adapter._music_video(user_id, job_id)
            music = self.library.get(mapping.get("music_id"))
            if video is None or music is None:
                raise ValueError
            output = add_music(
                video, music, Path(adapter.runtime.storage_output_dir), self.library.root,
                mode=mapping.get("music_mode", "mix"), original_volume=settings.LINE_MUSIC_ORIGINAL_VOLUME,
                music_volume=settings.LINE_MUSIC_BGM_VOLUME, timeout=settings.LINE_MUSIC_FFMPEG_TIMEOUT,
                ffmpeg=settings.FFMPEG_BINARY, ffprobe=settings.FFPROBE_BINARY,
                max_video_bytes=settings.LINE_MAX_VIDEO_BYTES,
            )
            if not self._lease(user_id, owner) or adapter._music_video(user_id, job_id) is None:
                return
            adapter.redis.hset(f"line:job:{job_id}", mapping={"music_state": "ready", "music_output": output.name})
            saved = True
        except Exception:
            adapter.logger.warning("LINE music processing failed")
            try:
                mapping = adapter._job_mapping(job_id)
                if self._lease(user_id, owner) and mapping.get("user_id") == user_id:
                    adapter.redis.hset(f"line:job:{job_id}", mapping={"music_state": "fallback"})
            except Exception:
                adapter.logger.warning("LINE music result unavailable")
        finally:
            try:
                if output and not saved:
                    output.unlink(missing_ok=True)
            finally:
                try:
                    self._lease(user_id, owner, release=True)
                except Exception:
                    adapter.logger.warning("LINE music lease cleanup unavailable")
                finally:
                    self.available.release()
