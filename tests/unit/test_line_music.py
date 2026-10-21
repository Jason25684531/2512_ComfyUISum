"""Music trust boundaries, state transitions and signed LINE delivery checks."""
import io
import json
import subprocess
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from PIL import Image

from test_line_routes import (
    FakeRedis, FakeRuntime, LineAdapter, _message, _mp4_header, _png, _postback,
    line_routes, patch_line_api, patch_line_config, signed_body,
)
import line_music_service as music_service
import media_postprocess as media


def track(track_id="neon", **fields):
    return {"id": track_id, "title": "Neon Drive", "file": "neon.mp3", "genre": "electronic",
            "mood": "energetic", "tempo": "fast", "tags": ["racing", "futuristic", "賽車"], **fields}


def library(root, tracks=None):
    root.mkdir(exist_ok=True)
    (root / "neon.mp3").write_bytes(b"test audio")
    (root / "library.json").write_text(json.dumps({"tracks": [track()] if tracks is None else tracks}), encoding="utf-8")
    return music_service.MusicLibrary(root)


class MusicRedis(FakeRedis):
    def __init__(self):
        super().__init__()
        self.ttls = {}

    def setex(self, key, ttl, value):
        super().setex(key, ttl, value)
        self.ttls[key] = ttl

    def set(self, key, value, ex=None, nx=False):
        result = super().set(key, value, ex=ex, nx=nx)
        if result and ex:
            self.ttls[key] = ex
        return result

    def scan_iter(self, match=None):
        from fnmatch import fnmatch

        return iter(key for key in list(self.values) + list(self.hashes) if not match or fnmatch(key, match))

    def ttl(self, key):
        if key not in self.values and key not in self.hashes:
            return -2
        return self.ttls.get(key, 86400)

    def expire(self, key, ttl, gt=False):
        current = self.ttl(key)
        if current == -2 or (gt and (current == -1 or current >= ttl)):
            return False
        self.ttls[key] = ttl
        return True

    def eval(self, script, count, key, owner, ttl):
        assert count == 1
        if self.get(key) != owner:
            return 0
        if "'del'" in script:
            self.delete(key)
        else:
            self.expire(key, ttl)
        return 1


def music_adapter(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    runtime.redis_client = MusicRedis()
    adapter = LineAdapter(runtime)
    settings = SimpleNamespace(**{key: getattr(line_routes.line_config, key) for key in (
        "LINE_MUSIC_STATE_TTL", "LINE_MUSIC_FFMPEG_TIMEOUT", "LINE_MUSIC_ORIGINAL_VOLUME",
        "LINE_MUSIC_BGM_VOLUME", "FFMPEG_BINARY", "FFPROBE_BINARY", "LINE_MAX_VIDEO_BYTES", "LINE_DOWNLOAD_TOKEN_TTL",
    )}, LINE_PUBLIC_BASE_URL="https://public.example")
    adapter.music = music_service.LineMusicService(adapter, library(tmp_path / "music"), settings)
    adapter._store_job_mapping("job-1", "U123", "video", "video_minimax_h3")
    runtime.redis_client.hset("line:job:job-1", mapping={"notification_state": "delivered"})
    runtime.redis_client.hset("job:status:job-1", mapping={"status": "completed", "image_url": "/outputs/original.mp4"})
    (runtime.storage_output_dir / "original.mp4").write_bytes(_mp4_header(1024, 1024))
    return adapter, runtime, sent


def test_library_validation_and_recheck(tmp_path):
    root = tmp_path / "music"
    good = track(license="CC-BY", attribution="Artist")
    bad = [track("duplicate", file="missing.mp3"), track("missing", file="absent.wav"),
           track("extension", file="x.txt"), track("traversal", file="../outside.mp3"),
           track("absolute", file=str(tmp_path / "outside.mp3")), track("backslash", file="a\\b.mp3"),
           track("url", file="https://x/a.mp3"), track("colon", file="C:/a.mp3"),
           track("empty", title=""), track("bad-id"), track("long", tags=["x" * 33]),
           track("type", tags="racing"), {"id": "incomplete"}, []]
    index = library(root, [good, track(title="duplicate"), *bad])
    assert list(index.tracks) == ["neon"]
    assert index.tracks["neon"]["license"] == "CC-BY"
    assert index.get("neon").is_absolute()
    assert index.get("fake") is None
    (root / "neon.mp3").unlink()
    assert index.get("neon") is None
    (root / "library.json").write_text("[]")
    assert music_service.MusicLibrary(root).tracks == {}
    (root / "library.json").write_text("{")
    assert music_service.MusicLibrary(root).tracks == {}
    (root / "library.json").unlink()
    assert music_service.MusicLibrary(root).tracks == {}


def test_library_rejects_oversize(tmp_path):
    root = tmp_path / "music"
    library(root)
    with (root / "large.mp3").open("wb") as handle:
        handle.truncate(50 * 1024 * 1024 + 1)
    (root / "library.json").write_text(json.dumps({"tracks": [track(file="large.mp3")]}))
    assert music_service.MusicLibrary(root).tracks == {}


def test_library_rejects_symlink(tmp_path):
    root = tmp_path / "music"
    index = library(root)
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"audio")
    try:
        (root / "escape.mp3").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    assert library(root, [track(file="escape.mp3")]).tracks == {}
    (root / "neon.mp3").unlink()
    (root / "neon.mp3").symlink_to(outside)
    assert index.get("neon") is None


def test_search_is_local_additive_and_deterministic(tmp_path):
    index = library(tmp_path / "music", [track(), track("calm", title="Quiet", genre="ambient", mood="calm", tempo="slow", tags=["racing"]),
                                       track("dark", title="Night", genre="cinematic", mood="dark", tags=[])])
    assert index.search("NEON DRIVE")[0]["id"] == "neon"
    assert index.search("找一首高速、未來科技、賽車感的音樂")[0]["id"] == "neon"
    assert index.search("racing futuristic")[0]["id"] == "neon"
    assert index.search("cinematic dark")[0]["id"] == "dark"
    assert index.search("找平靜音樂")[0]["id"] == "calm"
    assert index.search("unknown") == []
    assert index.search("找音樂") == []


@pytest.mark.parametrize("mode,has_audio", [("mix", True), ("replace", True), ("mix", False)])
def test_media_argv_and_atomic_output(monkeypatch, tmp_path, mode, has_audio):
    video = tmp_path / "source.mp4"
    music = tmp_path / "music.mp3"
    video.write_bytes(b"source")
    music.write_bytes(b"audio")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"output")
            return SimpleNamespace(returncode=0)
        streams = [{"codec_type": "video"}]
        if has_audio or str(args[-1]).endswith(".part"):
            streams.append({"codec_type": "audio"})
        return SimpleNamespace(returncode=0, stdout=json.dumps({"format": {"duration": "10"}, "streams": streams}))

    monkeypatch.setattr(media.subprocess, "run", run)
    output = media.add_music(video, music, tmp_path, tmp_path, mode=mode)
    assert output.read_bytes() == b"output" and video.read_bytes() == b"source"
    assert not list(tmp_path.glob("*.part"))
    args, kwargs = next(call for call in calls if call[0][0] == "ffmpeg")
    assert kwargs["shell"] is False and 0 < kwargs["timeout"] <= 120
    assert args[args.index("-c:v") + 1] == "copy"
    assert args[args.index("-t") + 1] == "10.0"
    assert args[args.index("-stream_loop") + 1] == "-1"
    assert args.count("-protocol_whitelist") == 2 and "-nostdin" in args
    assert ("amix" in args[args.index("-filter_complex") + 1]) == (mode == "mix" and has_audio)


@pytest.mark.parametrize("failure", ["missing", "timeout", "exit", "json"])
def test_media_errors_are_fixed(monkeypatch, tmp_path, failure):
    def run(args, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("private/path")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        return SimpleNamespace(returncode=1 if failure == "exit" else 0, stdout=b"bad json")

    monkeypatch.setattr(media.subprocess, "run", run)
    with pytest.raises(media.MediaPostprocessError) as error:
        media.probe(tmp_path / "video.mp4")
    assert "private" not in str(error.value)


@pytest.mark.parametrize("bad_path", ["../evil.mp3", "https://x/a.mp3", "C:/a.mp3"])
def test_media_rejects_paths_before_subprocess(monkeypatch, tmp_path, bad_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: pytest.fail("must reject before spawning"))
    with pytest.raises(media.MediaPostprocessError):
        media.add_music(video, Path(bad_path), tmp_path, tmp_path)


def begin_choice(adapter, *, images=0):
    for i in range(images):
        name = f"reference-{i}.png"
        (adapter.runtime.upload_folder / name).write_bytes(_png())
    adapter._save_session("U123", {"prompt": "Quiet forest", "images": [f"reference-{i}.png" for i in range(images)]})
    adapter.handle_event(_postback("output=video"))
    state = adapter._load_music_session("U123")
    assert state["state"] == "music_offer"
    assert adapter.runtime.job_service.calls == []
    return state


def choose_track(adapter, *, images=0):
    state = begin_choice(adapter, images=images)
    adapter.handle_event(_postback(f"music=yes:{state['request_id']}"))
    adapter.handle_event(_message(text="１"))
    assert len(adapter.runtime.job_service.calls) == 1
    return state


def complete_video(adapter, job_id="job-line-1"):
    adapter.redis.hset(f"job:status:{job_id}", mapping={"status": "completed", "image_url": "/outputs/original.mp4"})


def prepared_video(video, music, output_root, music_root, **kwargs):
    path = output_root / ("line_music_" + "a" * 24 + ".mp4")
    path.write_bytes(video.read_bytes())
    return path


def test_offer_playlist_search_modes_and_input_isolation(monkeypatch, tmp_path):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    adapter.handle_event(_message(text="找到寶藏的海盜"))
    assert json.loads(adapter.redis.get("line:user:U123"))["prompt"] == "找到寶藏的海盜"
    state = begin_choice(adapter)
    actions = sent[-1][1]["messages"][0]["quickReply"]["items"]
    assert [a["action"]["data"] for a in actions] == [
        f"music=yes:{state['request_id']}", f"music=no:{state['request_id']}"]
    adapter.handle_event(_postback("music=yes:" + "f" * 32))
    assert adapter._load_music_session("U123") == state
    adapter.handle_event(_postback(f"music=yes:{state['request_id']}"))
    assert "1. Neon Drive" in sent[-1][1]["messages"][0]["text"]
    assert "neon.mp3" not in str(sent)
    adapter.handle_event(_message(text="找高速未來科技感"))
    assert adapter._load_music_session("U123")["candidates"] == ["neon"]
    adapter.handle_event(_message(text="只要音樂"))
    assert adapter._load_music_session("U123")["mode"] == "replace"
    adapter.handle_event(_message(text="原聲加音樂"))
    adapter.handle_event(_message(text="９"))
    assert "1～1" in sent[-1][1]["messages"][0]["text"]
    adapter.handle_event(_message(text="A different prompt"))
    assert json.loads(adapter.redis.get("line:user:U123"))["prompt"] == "Quiet forest"
    adapter.handle_event(_message(message_type="image"))
    assert "請先完成配樂選擇" in sent[-1][1]["messages"][0]["text"]
    adapter.handle_event(_message(text="找不存在音樂"))
    adapter.handle_event(_message(text="1"))
    assert "請重新輸入" in sent[-1][1]["messages"][0]["text"]
    adapter.handle_event(_message(text="音樂"))
    assert adapter._load_music_session("U123")["created_at"] == state["created_at"]
    adapter.handle_event(_message(text="只要音樂"))
    adapter.handle_event(_message(text="１"))
    mapping = adapter._job_mapping("job-line-1")
    assert (mapping["music_id"], mapping["music_mode"]) == ("neon", "replace")
    assert "music_id" not in str(runtime.job_service.calls)
    adapter.handle_event(_message(text="1"))
    assert json.loads(adapter.redis.get("line:user:U123"))["prompt"] == "1"
    adapter.music.executor.shutdown()


def test_full_playlist_selection_submits_instead_of_reasking_output(monkeypatch, tmp_path):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    adapter.music.library = library(tmp_path / "music", [track(f"t{i:02d}") for i in range(10)])
    begin_choice(adapter)
    adapter.handle_event(_message(text="音樂"))
    assert len(adapter._load_music_session("U123")["candidates"]) == 10
    adapter.handle_event(_message(text="10"))
    assert adapter._job_mapping("job-line-1")["music_id"] == "t09"
    assert "quickReply" not in sent[-1][1]["messages"][0]
    adapter.music.executor.shutdown()


@pytest.mark.parametrize("tamper", [{"request_id": "../x"}, {"state": []}, {"mode": {}},
                                   {"candidates": ["../fake"]}, {"path": "/secret"},
                                   {"created_at": None}, {"created_at": 20261016}])
def test_tampered_sessions_are_discarded(monkeypatch, tmp_path, tamper):
    adapter, runtime, _ = music_adapter(monkeypatch, tmp_path)
    state = begin_choice(adapter)
    adapter.redis.setex("line:music:U123", 1200, json.dumps({**state, **tamper}))
    assert adapter._load_music_session("U123") is None
    assert runtime.job_service.calls == []
    adapter.music.executor.shutdown()


@pytest.mark.parametrize("selecting", [False, True])
@pytest.mark.parametrize("late_message", [False, True])
def test_timeout_submits_without_music_and_without_new_webhook(monkeypatch, tmp_path, selecting, late_message):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    state = begin_choice(adapter, images=1)
    if selecting:
        adapter.handle_event(_message(text="音樂"))
    assert adapter.redis.ttl("line:music:U123") > adapter.music.settings.LINE_MUSIC_STATE_TTL
    assert adapter.redis.ttl("line:user:U123") > adapter.music.settings.LINE_MUSIC_STATE_TTL
    future = line_routes._parse_created_at(state["created_at"]) + timedelta(seconds=1201)
    monkeypatch.setattr(line_routes, "_now", lambda: future)
    if late_message:
        adapter.handle_event(_message(text="1"))
    else:
        adapter.poll_once()
    adapter.poll_once()
    adapter.handle_event(_postback(f"music=yes:{state['request_id']}"))
    assert len(runtime.job_service.calls) == 1
    assert "first_frame" in runtime.job_service.calls[0][0]["images"]
    assert not adapter._job_mapping("job-line-1").get("music_id")
    assert any("選曲已逾時" in str(payload) for _, payload in sent)
    assert not list(runtime.upload_folder.glob("reference-*"))
    adapter.music.executor.shutdown()


def test_duplicate_decisions_and_timeout_do_not_submit_twice(monkeypatch, tmp_path):
    adapter, runtime, _ = music_adapter(monkeypatch, tmp_path)
    state = begin_choice(adapter)
    adapter.handle_event(_message(text="音樂"))
    state = adapter._load_music_session("U123")
    entered, finish = threading.Event(), threading.Event()
    submit = adapter.submit_output

    def blocked(*args, **kwargs):
        entered.set()
        assert finish.wait(5)
        return submit(*args, **kwargs)

    monkeypatch.setattr(adapter, "submit_output", blocked)
    task = threading.Thread(target=adapter.handle_event, args=(_message(text="1"),))
    task.start()
    try:
        assert entered.wait(2)
        adapter._finish_music_choice("U123", state)
        adapter.handle_event(_message(text="不要音樂"))
        adapter.handle_event(_message(text="取消"))
    finally:
        finish.set()
        task.join(5)
    assert not task.is_alive()
    assert len(runtime.job_service.calls) == 1
    adapter.music.executor.shutdown()


@pytest.mark.parametrize("images", [0, 1, 2])
def test_signed_async_final_delivery_and_download(monkeypatch, tmp_path, images):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    state = begin_choice(adapter, images=images)
    adapter.handle_event(_message(text="音樂"))
    body, signature = signed_body({"events": [_message(text="１")]})
    assert adapter.process_webhook(body, signature)[1] == 200
    assert len(runtime.job_service.calls) == 1
    assert not [payload for url, payload in sent if url == line_routes.LINE_PUSH_URL]
    entered, finish = threading.Event(), threading.Event()
    calls = []

    def process(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert finish.wait(5)
        return prepared_video(*args, **kwargs)

    monkeypatch.setattr(music_service, "add_music", process)
    complete_video(adapter)
    adapter.poll_once()
    assert entered.wait(2)
    adapter.poll_once()
    assert not [payload for url, payload in sent if url == line_routes.LINE_PUSH_URL]
    finish.set()
    adapter.music.executor.shutdown(wait=True)
    adapter.poll_once()
    adapter.poll_once()
    assert calls == [1]
    assert adapter.redis.get("line:music:lock:U123") is None
    assert adapter.redis.ttl("line:job:job-line-1") == 604800
    assert adapter.redis.ttl("job:status:job-line-1") == 604800
    pushed = [payload for url, payload in sent if url == line_routes.LINE_PUSH_URL]
    assert len(pushed) == 1
    assert [m["type"] for m in pushed[0]["messages"]] == ["text", "video"]
    assert pushed[0]["messages"][0]["text"] == "配樂影片已完成。"
    token = pushed[0]["messages"][1]["originalContentUrl"].rsplit("/", 1)[1]
    record = json.loads(adapter.redis.get(f"line:download:{token}"))
    assert record["job_id"] == "job-line-1" and record["output_name"].startswith("line_music_")
    app = Flask(__name__)
    app.register_blueprint(line_routes.create_blueprint(runtime))
    with app.test_client() as client:
        result = client.get(f"/line/download/{token}")
        assert result.status_code == 200 and result.mimetype == "video/mp4"
        assert result.headers["X-Content-Type-Options"] == "nosniff"
        with Image.open(io.BytesIO(client.get(f"/line/preview/{token}").data)) as image:
            assert image.width == image.height
        adapter.redis.delete(f"line:download:{token}")
        assert client.get(f"/line/download/{token}").status_code == 404


@pytest.mark.parametrize("failure", ["media", "removed", "preview", "schedule"])
def test_music_failure_delivers_original_once(monkeypatch, tmp_path, failure):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    choose_track(adapter)
    source = runtime.storage_output_dir / "original.mp4"
    original = source.read_bytes()

    def process(*args, **kwargs):
        if failure == "media":
            raise RuntimeError("PRIVATE/path ; $(secret)")
        return prepared_video(*args, **kwargs)

    monkeypatch.setattr(music_service, "add_music", process)
    if failure == "removed":
        (adapter.music.library.root / "neon.mp3").unlink()
    if failure == "preview":
        preview = adapter._create_preview
        monkeypatch.setattr(adapter, "_create_preview", lambda out, image, video:
                            False if video and video.name.startswith("line_music_") else preview(out, image, video))
    if failure == "schedule":
        monkeypatch.setattr(adapter.music.executor, "submit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rejected")))
    complete_video(adapter)
    adapter.poll_once()
    adapter.music.executor.shutdown(wait=True)
    adapter.poll_once()
    adapter.poll_once()
    assert source.read_bytes() == original
    assert not list(runtime.storage_output_dir.glob("line_music_*"))
    pushed = [payload for url, payload in sent if url == line_routes.LINE_PUSH_URL]
    assert len(pushed) == 1 and pushed[0]["messages"][0]["text"] == line_routes.REPLY_MUSIC_FALLBACK
    token = pushed[0]["messages"][1]["originalContentUrl"].rsplit("/", 1)[1]
    assert json.loads(adapter.redis.get(f"line:download:{token}"))["output_name"] == "original.mp4"
    assert adapter._job_mapping("job-line-1")["notification_state"] == "delivered"
    assert adapter.redis.hgetall("job:status:job-line-1")["status"] == "completed"
    assert "PRIVATE" not in str(sent)


def test_push_retry_reuses_ready_music(monkeypatch, tmp_path):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    choose_track(adapter)
    media_calls = []

    def process(*args, **kwargs):
        media_calls.append(1)
        return prepared_video(*args, **kwargs)

    monkeypatch.setattr(music_service, "add_music", process)
    complete_video(adapter)
    adapter.poll_once()
    adapter.music.executor.shutdown(wait=True)
    push = adapter.push_video
    attempts = []

    def fail_once(*args, **kwargs):
        attempts.append(1)
        return False if len(attempts) == 1 else push(*args, **kwargs)

    monkeypatch.setattr(adapter, "push_video", fail_once)
    adapter.poll_once()
    assert adapter._job_mapping("job-line-1")["notification_state"] == "retry"
    assert not any(key.startswith("line:download:") for key in adapter.redis.values)
    assert not list(runtime.storage_output_dir.glob("line_preview_*"))
    assert len(list(runtime.storage_output_dir.glob("line_music_*"))) == 1
    adapter.poll_once()
    assert media_calls == [1] and len(attempts) == 2
    assert adapter._job_mapping("job-line-1")["notification_state"] == "delivered"


@pytest.mark.parametrize("missing", ["source", "ready", "both"])
def test_ready_delivery_or_original_fallback_after_file_loss(monkeypatch, tmp_path, missing):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    choose_track(adapter)
    monkeypatch.setattr(music_service, "add_music", prepared_video)
    complete_video(adapter)
    adapter.poll_once()
    adapter.music.executor.shutdown(wait=True)
    if missing in {"source", "both"}:
        (runtime.storage_output_dir / "original.mp4").unlink()
    if missing in {"ready", "both"}:
        (runtime.storage_output_dir / adapter._job_mapping("job-line-1")["music_output"]).unlink()
    adapter.poll_once()
    pushed = [p for url, p in sent if url == line_routes.LINE_PUSH_URL]
    assert len(pushed) == 1
    text = pushed[0]["messages"][0]["text"]
    assert text == {"source": "配樂影片已完成。", "ready": line_routes.REPLY_MUSIC_FALLBACK,
                    "both": line_routes.REPLY_GENERATION_FAILED}[missing]


@pytest.mark.parametrize("ready", [False, True])
def test_restart_recovers_pending_or_prepared_music(monkeypatch, tmp_path, ready):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    choose_track(adapter)
    complete_video(adapter)
    old = adapter.music
    calls = []

    def process(*args, **kwargs):
        calls.append(1)
        return prepared_video(*args, **kwargs)

    monkeypatch.setattr(music_service, "add_music", process)
    if ready:
        adapter.poll_once()
    old.executor.shutdown(wait=True)
    adapter.music = music_service.LineMusicService(adapter, old.library, old.settings)
    if not ready:
        adapter.redis.set("line:music:lock:U123", "crashed-owner")
        adapter.poll_once()
        assert calls == []
        adapter.redis.delete("line:music:lock:U123")  # Lease expiry after restart.
    adapter.poll_once()
    adapter.music.executor.shutdown(wait=True)
    adapter.poll_once()
    assert calls == [1]
    assert len([p for url, p in sent if url == line_routes.LINE_PUSH_URL]) == 1


def test_busy_music_jobs_stay_mapped_and_deliver_later(monkeypatch, tmp_path):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    choose_track(adapter)
    complete_video(adapter)
    adapter._store_job_mapping("second", "U456", "video", "video_minimax_h3", music_id="neon")
    complete_video(adapter, "second")
    entered, finish = threading.Event(), threading.Event()
    futures, calls = [], []
    submit = adapter.music.executor.submit

    def capture(*args, **kwargs):
        future = submit(*args, **kwargs)
        futures.append(future)
        return future

    def process(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert finish.wait(5)
        path = args[2] / ("line_music_" + str(len(calls)) * 24 + ".mp4")
        path.write_bytes(args[0].read_bytes())
        return path

    monkeypatch.setattr(adapter.music.executor, "submit", capture)
    monkeypatch.setattr(music_service, "add_music", process)
    adapter.poll_once()
    assert entered.wait(2) and len(futures) == 1
    assert adapter.redis.get("line:music:lock:U456") is None
    assert adapter._job_mapping("second")["music_state"] == "pending"
    # A new selection is independent of the previous job's execution lock.
    saved = {"state": "music_offer", "request_id": "f" * 32, "candidates": [],
             "mode": "mix", "created_at": line_routes._iso_now()}
    adapter._save_music_session("U123", saved)
    finish.set()
    futures[0].result(timeout=5)
    assert adapter._load_music_session("U123") == saved
    adapter.poll_once()
    assert len(futures) == 2
    futures[1].result(timeout=5)
    adapter.poll_once()
    adapter.music.executor.shutdown(wait=True)
    assert calls == [1, 1]
    assert sorted(p["to"] for url, p in sent if url == line_routes.LINE_PUSH_URL) == ["U123", "U456"]


def test_source_binding_cancel_and_redis_failure(monkeypatch, tmp_path):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    assert adapter._music_video("U123", "job-1") is None  # Previously delivered output is never selected.
    begin_choice(adapter, images=1)
    adapter.handle_event(_message(text="取消"))
    adapter.poll_once()
    assert adapter._load_music_session("U123") is None and runtime.job_service.calls == []
    assert not list(runtime.upload_folder.glob("reference-*"))
    choose_track(adapter)
    complete_video(adapter)
    assert adapter._music_video("U123", "job-line-1").name == "original.mp4"
    assert adapter._music_video("U999", "job-line-1") is None
    adapter.redis.set("line:music:lock:U123", "new-owner")
    assert not adapter.music._lease("U123", "old-owner", release=True)
    assert adapter.redis.get("line:music:lock:U123") == "new-owner"
    adapter.redis.available = False
    body, signature = signed_body({"events": [_message(text="音樂")]})
    assert adapter.process_webhook(body, signature)[1] == 503
    adapter.music.executor.shutdown()


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("kind,images", [("video", 0), ("video", 1), ("image", 0)])
def test_original_generation_and_rollback(monkeypatch, tmp_path, enabled, kind, images):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    service = adapter.music
    if not enabled:
        adapter.music = None
    staged = []
    if images:
        (runtime.upload_folder / "input.png").write_bytes(_png())
        staged = ["input.png"]
    adapter._save_session("U123", {"images": staged, "prompt": None})
    adapter.handle_event(_message(text="Quiet forest"))
    adapter.handle_event(_postback(f"output={kind}"))
    if enabled and kind == "video":
        state = adapter._load_music_session("U123")
        adapter.handle_event(_postback(f"music=no:{state['request_id']}"))
    assert runtime.job_service.calls[0][0]["prompt"] == "Quiet forest"
    output = runtime.storage_output_dir / ("original.mp4" if kind == "video" else "image.png")
    if kind == "image":
        output.write_bytes(_png())
    adapter.redis.hset("job:status:job-line-1", mapping={"status": "completed", "image_url": f"/outputs/{output.name}"})
    assert adapter.poll_once() == 1
    pushed = [payload for url, payload in sent if url == line_routes.LINE_PUSH_URL][-1]
    message = pushed["messages"][0]
    assert message["type"] == kind and len(pushed["messages"]) == 1
    token = message["originalContentUrl"].rsplit("/", 1)[1]
    assert json.loads(adapter.redis.get(f"line:download:{token}"))["output_name"] == output.name
    if not enabled:
        adapter.handle_event(_message(text="音樂"))
        assert json.loads(adapter.redis.get("line:user:U123"))["prompt"] == "音樂"
    service.executor.shutdown()


def test_disabled_before_completion_falls_back_and_empty_library_skips_offer(monkeypatch, tmp_path):
    adapter, runtime, sent = music_adapter(monkeypatch, tmp_path)
    choose_track(adapter)
    service, adapter.music = adapter.music, None
    complete_video(adapter)
    adapter.poll_once()
    pushed = [p for url, p in sent if url == line_routes.LINE_PUSH_URL]
    assert pushed[-1]["messages"][0]["text"] == line_routes.REPLY_MUSIC_FALLBACK
    adapter.music = service
    service.library.tracks.clear()
    runtime.job_service.calls.clear()
    adapter.handle_event(_message(text="New scene"))
    adapter.handle_event(_postback("output=video"))
    assert len(runtime.job_service.calls) == 1 and adapter._load_music_session("U123") is None
    service.executor.shutdown()


@pytest.mark.parametrize("disabled", [False, True])
def test_pending_choice_survives_library_change_or_disabled_restart(monkeypatch, tmp_path, disabled):
    adapter, runtime, _ = music_adapter(monkeypatch, tmp_path)
    state = begin_choice(adapter)
    adapter.handle_event(_message(text="音樂"))
    service = adapter.music
    if disabled:
        adapter.music = None
    else:
        service.library.tracks.clear()
    future = line_routes._parse_created_at(state["created_at"]) + timedelta(seconds=1201)
    monkeypatch.setattr(line_routes, "_now", lambda: future)
    adapter.poll_once()
    adapter.poll_once()
    assert len(runtime.job_service.calls) == 1
    assert not adapter._job_mapping("job-line-1").get("music_id")
    service.executor.shutdown()


@pytest.mark.parametrize("invalid", ["duration", "video", "audio", "size"])
def test_invalid_outputs_are_removed(monkeypatch, tmp_path, invalid):
    video, music = tmp_path / "v.mp4", tmp_path / "m.mp3"
    video.write_bytes(b"v")
    music.write_bytes(b"m")
    calls = 0

    def probe(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {"duration": 20 if calls > 1 and invalid == "duration" else 10,
                "has_video": calls == 1 or invalid != "video", "has_audio": invalid != "audio"}

    def run(args, timeout):
        Path(args[-1]).write_bytes(b"x" * (101 if invalid == "size" else 1))

    monkeypatch.setattr(media, "probe", probe)
    monkeypatch.setattr(media, "_run", run)
    with pytest.raises(media.MediaPostprocessError):
        media.add_music(video, music, tmp_path, tmp_path, max_video_bytes=100)
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob("line_music_*.mp4"))


def test_config_clamps_and_disabled_startup(monkeypatch, tmp_path):
    import runpy

    monkeypatch.setenv("LINE_MUSIC_STATE_TTL", "10")
    monkeypatch.setenv("LINE_MUSIC_RESULT_LIMIT", "9")
    monkeypatch.setenv("LINE_MUSIC_ORIGINAL_VOLUME", "nan")
    monkeypatch.setenv("LINE_MUSIC_BGM_VOLUME", "3")
    monkeypatch.setenv("LINE_MUSIC_FFMPEG_TIMEOUT", "9999")
    values = runpy.run_path(str(Path(line_routes.__file__).with_name("config.py")))
    assert [values[key] for key in ("LINE_MUSIC_STATE_TTL", "LINE_MUSIC_RESULT_LIMIT", "LINE_MUSIC_ORIGINAL_VOLUME",
                                  "LINE_MUSIC_BGM_VOLUME", "LINE_MUSIC_FFMPEG_TIMEOUT")] == [600, 5, 0, 2, 600]
    monkeypatch.setattr(line_routes, "LINE_MUSIC_ENABLED", False)
    monkeypatch.setattr(line_routes, "MusicLibrary", lambda *a, **k: pytest.fail("disabled feature must not scan library"))
    assert line_routes.create_blueprint(FakeRuntime(tmp_path)).line_adapter.music is None
