"""Real FFmpeg: audio looping/trimming, lossless video copy and safe failures."""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_SRC = str(Path(__file__).resolve().parents[2] / "backend/src")
sys.path.insert(0, BACKEND_SRC)
from media_postprocess import MediaPostprocessError, add_music, probe
sys.path.remove(BACKEND_SRC)


def run(args):
    return subprocess.run(args, check=True, capture_output=True, timeout=30).stdout


@pytest.fixture(scope="module")
def media_files(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe are required for local media E2E")
    root = tmp_path_factory.mktemp("music-ffmpeg")
    silent = root / "silent.mp4"
    run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=1024x1024:r=24:d=10",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(silent)])
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(silent), "-f", "lavfi", "-i", "sine=frequency=300:duration=10",
         "-c:v", "copy", "-c:a", "aac", "-t", "10", str(root / "audio.mp4")])
    for name, duration in (("short", 4), ("long", 12)):
        run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=600:duration={duration}",
             "-c:a", "libmp3lame", str(root / f"{name}.mp3")])
    return root


def video_hash(path):
    return run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:v:0",
                "-c:v", "copy", "-f", "hash", "-hash", "sha256", "-"])


@pytest.mark.parametrize("video", ["silent", "audio"])
@pytest.mark.parametrize("music", ["short", "long"])
@pytest.mark.parametrize("mode", ["mix", "replace"])
def test_real_mix_replace_loop_trim_and_copy(media_files, video, music, mode):
    root = media_files
    source = root / f"{video}.mp4"
    before = hashlib.sha256(source.read_bytes()).digest()
    output = add_music(source, root / f"{music}.mp3", root, root, mode=mode)
    result = probe(output)
    assert result["has_video"] and result["has_audio"]
    assert abs(result["duration"] - 10) <= 0.5
    assert video_hash(source) == video_hash(output)
    # Audio remains decodable through the last second after looping or trimming.
    audio = run(["ffmpeg", "-nostdin", "-v", "error", "-ss", "9", "-i", str(output),
                 "-map", "0:a:0", "-t", "0.5", "-f", "s16le", "-"])
    assert audio and any(audio)
    assert hashlib.sha256(source.read_bytes()).digest() == before
    output.unlink()


def test_real_corrupt_audio_timeout_and_cleanup(media_files):
    root = media_files
    corrupt = root / "corrupt.mp3"
    corrupt.write_bytes(b"not a decodable MP3")
    for music, timeout in ((corrupt, 120), (root / "short.mp3", 0.000001)):
        with pytest.raises(MediaPostprocessError):
            add_music(root / "silent.mp4", music, root, root, timeout=timeout)
    assert not list(root.glob("*.part"))
    assert not list(root.glob("line_music_*.mp4"))
