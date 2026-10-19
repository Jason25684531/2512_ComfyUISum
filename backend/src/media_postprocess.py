"""Bounded CPU audio post-processing of validated local media only."""
from __future__ import annotations

import json
import math
import secrets
import subprocess
import time
from pathlib import Path

MAX_AUDIO_BYTES = 50 * 1024 * 1024


class MediaPostprocessError(RuntimeError):
    """Fixed failure category; never carry subprocess output or media paths."""


def _run(args: list[str], timeout: float):
    try:
        result = subprocess.run(args, shell=False, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        raise MediaPostprocessError("media_process_failed") from None
    if result.returncode:
        raise MediaPostprocessError("media_process_failed")
    return result


def probe(path: Path, *, binary: str = "ffprobe", timeout: float = 120) -> dict:
    result = _run([
        binary, "-v", "error", "-protocol_whitelist", "file", "-show_entries",
        "format=duration:stream=codec_type", "-of", "json", str(path.resolve()),
    ], timeout)
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        kinds = {stream["codec_type"] for stream in data["streams"]}
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError
        return {"duration": duration, "has_video": "video" in kinds, "has_audio": "audio" in kinds}
    except (KeyError, ValueError, TypeError):
        raise MediaPostprocessError("invalid_media") from None


def _input(path: Path, root: Path, extensions: set[str], size_limit: int) -> Path:
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
        if resolved.suffix.lower() not in extensions or not resolved.is_file() or not 0 < resolved.stat().st_size <= size_limit:
            raise ValueError
        return resolved
    except (OSError, ValueError, RuntimeError):
        raise MediaPostprocessError("invalid_media_path") from None


def add_music(
    video: Path, music: Path, output_root: Path, music_root: Path, *, mode: str = "mix",
    original_volume: float = 0.3, music_volume: float = 0.7, timeout: float = 120,
    ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", max_video_bytes: int = 200 * 1024 * 1024,
) -> Path:
    if mode not in {"mix", "replace"} or any(not math.isfinite(v) or not 0 <= v <= 2 for v in (original_volume, music_volume)):
        raise MediaPostprocessError("invalid_options")
    video = _input(video, output_root, {".mp4"}, max_video_bytes)
    music = _input(music, music_root, {".mp3", ".wav"}, MAX_AUDIO_BYTES)
    deadline = time.monotonic() + timeout

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise MediaPostprocessError("media_timeout")
        return seconds

    source = probe(video, binary=ffprobe, timeout=remaining())
    if not source["has_video"]:
        raise MediaPostprocessError("invalid_media")
    output = output_root.resolve() / f"line_music_{secrets.token_hex(12)}.mp4"
    temporary = output.with_suffix(".part")
    try:
        args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-protocol_whitelist", "file", "-i", str(video), "-stream_loop", "-1",
                "-protocol_whitelist", "file", "-i", str(music)]
        if mode == "mix" and source["has_audio"]:
            graph = (f"[0:a:0]volume={original_volume},apad[a0];[1:a:0]volume={music_volume}[a1];"
                     "[a0][a1]amix=inputs=2:duration=longest:normalize=0[aout]")
        else:
            graph = f"[1:a:0]volume={music_volume}[aout]"
        args += ["-filter_complex", graph, "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "192k", "-t", str(source["duration"]),
                 "-movflags", "+faststart", "-f", "mp4", str(temporary)]
        _run(args, remaining())
        result = probe(temporary, binary=ffprobe, timeout=remaining())
        if (not result["has_video"] or not result["has_audio"]
                or abs(result["duration"] - source["duration"]) > 0.5
                or not 0 < temporary.stat().st_size <= max_video_bytes):
            raise MediaPostprocessError("invalid_output")
        temporary.replace(output)
        return output
    except OSError:
        raise MediaPostprocessError("media_io_failed") from None
    finally:
        temporary.unlink(missing_ok=True)
