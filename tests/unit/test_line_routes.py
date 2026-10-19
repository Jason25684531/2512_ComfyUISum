import base64
import hashlib
import hmac
import io
import json
import logging
import sys
from pathlib import Path

import pytest
from PIL import Image

BACKEND_SRC = Path(__file__).resolve().parents[2] / "backend" / "src"
sys.modules.pop("config", None)
sys.path.insert(0, str(BACKEND_SRC))

import line_routes  # noqa: E402
from line_routes import LineAdapter, create_blueprint, verify_line_signature  # noqa: E402
from job_service import _normalize_catalog_inputs  # noqa: E402

sys.path.remove(str(BACKEND_SRC))
sys.modules.pop("config", None)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}
        self.ttls = {}
        self.available = True

    def ping(self):
        if not self.available:
            raise ConnectionError("Redis unavailable")
        return True

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl

    def set(self, key, value, ex=None, nx=False):
        if nx and (key in self.values or key in self.hashes):
            return False
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, key):
        self.values.pop(key, None)
        self.hashes.pop(key, None)
        self.ttls.pop(key, None)

    def ttl(self, key):
        if key not in self.values and key not in self.hashes:
            return -2
        return self.ttls.get(key, -1)

    def expire(self, key, ttl, gt=False):
        current = self.ttl(key)
        if current == -2 or (gt and (current == -1 or current >= ttl)):
            return False
        self.ttls[key] = ttl
        return True

    def hset(self, key, mapping=None, **kwargs):
        fields = dict(mapping or {})
        fields.update(kwargs)
        self.hashes.setdefault(key, {}).update(fields)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def scan_iter(self, match=None):
        keys = list(self.hashes)
        if match == "line:job:*":
            return iter(key for key in keys if key.startswith("line:job:"))
        return iter(keys)

    def keys(self, _pattern):
        return list(self.hashes)


class FakeJobService:
    def __init__(self):
        self.calls = []
        self.next_job_id = "job-line-1"
        self.status = 200

    def submit(self, payload, **kwargs):
        self.calls.append((payload, kwargs))
        return {"job_id": self.next_job_id, "status": "queued"}, self.status


class FakeRuntime:
    def __init__(self, tmp_path):
        self.project_root = Path(__file__).resolve().parents[2]
        self.upload_folder = tmp_path / "inputs"
        self.storage_output_dir = tmp_path / "outputs"
        self.upload_folder.mkdir()
        self.storage_output_dir.mkdir()
        self.redis_client = FakeRedis()
        self.job_service = FakeJobService()
        self.logger = logging.getLogger("line-test")
        self.repository_provider = lambda: self

    def get_job(self, _job_id):
        return None

    def list_outputs(self, _job_id):
        return []


class LineResponse:
    status_code = 200


def signed_body(payload, secret="test-secret"):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return body, signature


def patch_line_config(monkeypatch):
    monkeypatch.setattr(line_routes, "LINE_CHANNEL_SECRET", "test-secret")
    monkeypatch.setattr(line_routes, "LINE_CHANNEL_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setattr(line_routes, "LINE_PUBLIC_BASE_URL", "https://public.example")


def patch_line_api(monkeypatch):
    sent = []
    monkeypatch.setattr(
        line_routes.requests,
        "request",
        lambda method, url, **kwargs: sent.append((url, kwargs["json"])) or LineResponse(),
    )
    return sent


def _png(color="blue"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _message(user="U123", message_type="text", text="", message_id="msg-1", reply_token="reply"):
    message = {"type": message_type, "id": message_id}
    if message_type == "text":
        message["text"] = text
    return {
        "type": "message",
        "replyToken": reply_token,
        "source": {"userId": user},
        "message": message,
    }


def _postback(data, user="U123", reply_token="reply"):
    return {
        "type": "postback",
        "replyToken": reply_token,
        "source": {"userId": user},
        "postback": {"data": data},
    }


def _stage_files(adapter, runtime, count):
    paths = []
    for index in range(count):
        name = f"reference-{index}.png"
        (runtime.upload_folder / name).write_bytes(_png())
        paths.append(name)
    adapter._save_session("U123", {"images": paths, "prompt": None})
    return paths


def test_prompt_requires_postback_and_routes_text_only_video(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)

    adapter.handle_event(_message(text="圖片"))
    assert runtime.job_service.calls == []
    assert json.loads(runtime.redis_client.get("line:user:U123"))["prompt"] == "圖片"
    quick_reply = sent[-1][1]["messages"][0]["quickReply"]["items"]
    assert [item["action"]["data"] for item in quick_reply] == ["output=image", "output=video"]
    assert all(item["action"]["type"] == "postback" for item in quick_reply)

    before = len(sent)
    adapter.handle_event(_postback("output=unknown"))
    assert len(sent) == before
    assert runtime.job_service.calls == []

    adapter.handle_event(_postback("output=video"))
    payload = runtime.job_service.calls[0][0]
    assert payload == {
        "workflow": "video_minimax_h3", "prompt": "圖片", "images": {},
        "extra_params": {"duration": 10},
    }
    assert "video_mode" not in payload
    assert runtime.redis_client.hgetall("line:job:job-line-1")["output_type"] == "video"
    assert runtime.redis_client.get("line:user:U123") is None
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_GENERATING


@pytest.mark.parametrize(
    ("output_type", "image_count", "expected_fields"),
    [
        ("image", 0, set()),
        ("image", 3, set()),
        ("video", 0, set()),
        ("video", 1, {"first_frame"}),
        ("video", 2, {"first_frame", "last_frame"}),
    ],
)
def test_output_choice_routes_catalog_payloads(monkeypatch, tmp_path, output_type, image_count, expected_fields):
    patch_line_config(monkeypatch)
    patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    _stage_files(adapter, runtime, image_count)

    adapter.handle_event(_message(text="A quiet forest at sunrise."))
    adapter.handle_event(_postback(f"output={output_type}"))

    payload = runtime.job_service.calls[0][0]
    expected_workflow = "image_gpt25_sunburst" if output_type == "image" else "video_minimax_h3"
    assert payload["workflow"] == expected_workflow
    assert payload["prompt"] == "A quiet forest at sunrise."
    if output_type == "image":
        assert isinstance(payload["images"], list)
        assert len(payload["images"]) == image_count
        assert all(image.startswith("data:image/png;base64,") for image in payload["images"])
    else:
        assert set(payload["images"]) == expected_fields
        assert all(value.startswith("data:image/png;base64,") for value in payload["images"].values())
        assert "video_mode" not in payload


def test_three_images_only_offer_image_and_fourth_is_not_downloaded(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    content = _png()
    downloads = []

    class ImageResponse:
        status_code = 200
        headers = {"Content-Type": "image/png", "Content-Length": str(len(content))}

        def iter_content(self, chunk_size):
            yield content

        def close(self):
            pass

    monkeypatch.setattr(line_routes.requests, "get", lambda *args, **kwargs: downloads.append(args[0]) or ImageResponse())
    for index in range(3):
        adapter.handle_event(_message(message_type="image", message_id=f"img-{index}"))
        assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_IMAGE_RECEIVED.format(count=index + 1)
    adapter.handle_event(_message(message_type="image", message_id="img-4"))
    assert len(downloads) == 3
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_IMAGE_LIMIT

    adapter.handle_event(_message(text="A cat on a chair."))
    items = sent[-1][1]["messages"][0]["quickReply"]["items"]
    assert [item["action"]["data"] for item in items] == ["output=image"]
    adapter.handle_event(_message(message_type="image", message_id="img-5"))
    assert len(downloads) == 3
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_IMAGE_LIMIT
    assert [item["action"]["data"] for item in sent[-1][1]["messages"][0]["quickReply"]["items"]] == ["output=image"]
    adapter.handle_event(_postback("output=video"))
    assert runtime.job_service.calls == []
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_VIDEO_IMAGE_LIMIT


def test_prompt_after_upload_repeats_output_quick_reply(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    content = _png()

    class ImageResponse:
        status_code = 200
        headers = {"Content-Type": "image/png"}

        def iter_content(self, chunk_size):
            yield content

        def close(self):
            pass

    monkeypatch.setattr(line_routes.requests, "get", lambda *args, **kwargs: ImageResponse())
    adapter.handle_event(_message(message_type="image"))
    adapter.handle_event(_message(text="A house by the sea."))
    assert [item["action"]["data"] for item in sent[-1][1]["messages"][0]["quickReply"]["items"]] == [
        "output=image", "output=video"
    ]
    adapter.handle_event(_message(message_type="image", message_id="img-2"))
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_IMAGE_RECEIVED.format(count=2)
    assert [item["action"]["data"] for item in sent[-1][1]["messages"][0]["quickReply"]["items"]] == [
        "output=image", "output=video"
    ]


def test_failed_image_download_does_not_change_session(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    paths = _stage_files(adapter, runtime, 1)
    session = {"images": paths, "prompt": "Keep this prompt"}
    adapter._save_session("U123", session)
    before = json.loads(runtime.redis_client.get("line:user:U123"))

    class FailedImageResponse:
        status_code = 500
        headers = {}

        def close(self):
            pass

    monkeypatch.setattr(line_routes.requests, "get", lambda *args, **kwargs: FailedImageResponse())
    adapter.handle_event(_message(message_type="image", message_id="bad-image"))
    after = json.loads(runtime.redis_client.get("line:user:U123"))
    assert after["images"] == before["images"]
    assert after["prompt"] == before["prompt"]
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_IMAGE_FAILED
    assert runtime.job_service.calls == []


def test_cancel_removes_images_and_prompt(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    paths = _stage_files(adapter, runtime, 2)
    adapter.handle_event(_message(text="A prompt"))
    adapter.handle_event(_message(text="取消"))
    assert runtime.redis_client.get("line:user:U123") is None
    assert all(not (runtime.upload_folder / path).exists() for path in paths)
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_CANCELLED


def test_postback_without_prompt_and_unknown_postback_do_no_work(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    adapter.handle_event(_postback("output=image"))
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_NEED_PROMPT
    before = len(sent)
    adapter.handle_event(_postback("arbitrary=data"))
    assert len(sent) == before
    adapter.handle_event(_postback(["output=image"]))
    assert len(sent) == before
    assert runtime.job_service.calls == []


def test_unavailable_and_rejected_submissions_preserve_session(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    resolve_workflow = adapter._resolve_workflow
    adapter.handle_event(_message(text="Keep this prompt"))
    monkeypatch.setattr(adapter, "_resolve_workflow", lambda _workflow_id: None)
    adapter.handle_event(_postback("output=image"))
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_UNAVAILABLE
    assert json.loads(runtime.redis_client.get("line:user:U123"))["prompt"] == "Keep this prompt"

    monkeypatch.setattr(adapter, "_resolve_workflow", resolve_workflow)
    runtime.job_service.status = 400
    adapter = LineAdapter(runtime)
    adapter.handle_event(_message(text="Rejected prompt"))
    adapter.handle_event(_postback("output=image"))
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_GENERATION_FAILED
    assert json.loads(runtime.redis_client.get("line:user:U123"))["prompt"] == "Rejected prompt"
    assert runtime.redis_client.hgetall("line:job:job-line-1") == {}


def test_webhook_signature_redis_and_html_prompt_safety(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    event = {"events": [_message(text="<script>alert(1)</script>") ]}
    body, signature = signed_body(event)
    assert verify_line_signature(body, signature, "test-secret")
    assert adapter.process_webhook(body, "bad")[1] == 401
    assert runtime.job_service.calls == []
    assert adapter.process_webhook(body, signature)[1] == 200
    assert runtime.job_service.calls == []
    assert "<script>" not in json.dumps(sent[-1][1])

    runtime.redis_client.available = False
    assert adapter.process_webhook(body, signature)[1] == 503


def test_legacy_session_is_cleared_with_staged_file(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    legacy = runtime.upload_folder / "legacy.png"
    legacy.write_bytes(_png())
    runtime.redis_client.setex(
        "line:user:U123",
        1200,
        json.dumps({"state": "i2v_wait_prompt", "image_path": "legacy.png", "created_at": line_routes._iso_now()}),
    )
    assert adapter._load_session("U123")["images"] == []
    assert runtime.redis_client.get("line:user:U123") is None
    assert not legacy.exists()


def test_video_completion_and_secure_download(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    output = runtime.storage_output_dir / "job-line-1.mp4"
    output.write_bytes(b"valid mp4 bytes")
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "output_type": "video", "workflow_id": "video_minimax_h3",
        "notification_state": "pending", "notification_attempts": "0",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={
        "status": "completed", "image_url": "/outputs/job-line-1.mp4",
    })
    pushed = []
    monkeypatch.setattr(adapter, "push_video", lambda user, video, preview: pushed.append((user, video, preview)) or True)
    assert adapter.poll_once() == 1
    assert pushed and "https://public.example/line/download/" in pushed[0][1]
    assert "/line/preview/" in pushed[0][2]
    token = next(key.split(":", 2)[2] for key in runtime.redis_client.values if key.startswith("line:download:"))
    assert json.loads(runtime.redis_client.get(f"line:download:{token}"))["kind"] == "video"

    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    client = app.test_client()
    response = client.get(f"/line/download/{token}")
    assert response.status_code == 200
    assert response.mimetype == "video/mp4"
    assert "video.mp4" in response.headers["Content-Disposition"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    preview = client.get(f"/line/preview/{token}")
    assert preview.status_code == 200 and preview.mimetype == "image/jpeg"
    assert len(preview.data) <= 1024 * 1024
    assert client.get("/line/download/invalid-token").status_code == 404
    assert client.get("/line/preview/invalid-token").status_code == 404


@pytest.mark.parametrize("kind", ["video", "image"])
@pytest.mark.parametrize("existing_ttl", [3600, 8 * 86400, -1])
def test_media_remains_accessible_until_seven_days(monkeypatch, tmp_path, kind, existing_ttl):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    monkeypatch.setattr(line_routes, "LINE_DOWNLOAD_TOKEN_TTL", 7 * 86400)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    redis = runtime.redis_client
    adapter._store_job_mapping("job-line-1", "U123", kind, "test-workflow")
    output = runtime.storage_output_dir / ("result.mp4" if kind == "video" else "result.png")
    output.write_bytes(b"video bytes" if kind == "video" else _png())
    redis.hset("job:status:job-line-1", mapping={"status": "completed", "image_url": f"/outputs/{output.name}"})
    for key in ("line:job:job-line-1", "job:status:job-line-1"):
        if existing_ttl == -1:
            redis.ttls.pop(key, None)
        else:
            redis.expire(key, existing_ttl)
    assert adapter.poll_once() == 1
    payload = next(payload for url, payload in sent if url == line_routes.LINE_PUSH_URL)
    token = payload["messages"][0]["originalContentUrl"].rsplit("/", 1)[1]
    expected_ttl = -1 if existing_ttl == -1 else max(existing_ttl, 7 * 86400)
    assert redis.ttl("line:job:job-line-1") == expected_ttl
    assert redis.ttl("job:status:job-line-1") == expected_ttl
    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))

    def advance(seconds):
        for key in list(redis.values) + list(redis.hashes):
            ttl = redis.ttl(key)
            if 0 <= ttl <= seconds:
                redis.delete(key)
            elif ttl > seconds:
                redis.expire(key, ttl - seconds)

    with app.test_client() as client:
        # No database fallback: both Redis dependencies must outlive the token.
        for seconds in (3601, 86400, 7 * 86400 - 1 - 3601 - 86400):
            advance(seconds)
            assert client.get(f"/line/download/{token}").status_code == 200
            assert client.get(f"/line/preview/{token}").status_code == 200
            assert adapter.poll_once() == 0
        advance(1)
        assert client.get(f"/line/download/{token}").status_code == 404
        assert client.get(f"/line/preview/{token}").status_code == 404


def _mp4_header(width, height):
    import struct

    def box(kind, payload):
        return struct.pack(">I4s", 8 + len(payload), kind) + payload

    tkhd = b"\x00" * 76 + struct.pack(">II", width << 16, height << 16)
    return box(b"ftyp", b"isom") + box(b"mdat", b"\x00" * 16) + box(b"moov", box(b"trak", box(b"tkhd", tkhd)))


def test_video_preview_matches_video_aspect_ratio(tmp_path):
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    video = tmp_path / "square.mp4"
    video.write_bytes(_mp4_header(1024, 1024))
    assert line_routes._mp4_size(video) == (1024, 1024)
    preview = tmp_path / "preview.jpg"
    assert adapter._create_preview(preview, video_path=video)
    with Image.open(preview) as image:
        assert image.size == (1280, 1280)


@pytest.mark.parametrize('output_type', ['image', 'video'])
@pytest.mark.parametrize(('prompt', 'dimensions'), [
    ('A city, vertical 9:16', (864, 1536)),
    ('請用直式 ９：１６生成', (864, 1536)),
    ('A vertical city video', (864, 1536)),
    ('手機壁紙', (576, 1280)),
    ('A phone wallpaper, 9:20', (576, 1280)),
    ('風景，16:9 橫式', (1536, 864)),
    ('Square 1:1', (1024, 1024)),
])
def test_line_prompt_dimensions_reach_the_generation_payload(monkeypatch, tmp_path, output_type, prompt, dimensions):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    assert adapter.submit_output('U123', prompt, output_type, []) is True
    data, kwargs = runtime.job_service.calls[-1]
    entry = adapter._resolve_workflow(data['workflow']).entry
    width, height = dimensions
    if output_type == 'image':
        if dimensions == (576, 1280):
            assert kwargs['internal_extra_params'] == {
                'size': 'custom', 'custom_width': width, 'custom_height': height,
            }
        else:
            extra, _, error = _normalize_catalog_inputs(entry, data, prompt)
            assert error is None
            assert extra['size'] == f'{width}x{height}'
    else:
        extra, _, error = _normalize_catalog_inputs(entry, data, prompt)
        assert error is None
        assert (extra['width'], extra['height']) == dimensions
        assert extra['duration'] == 10
        assert width % 32 == height % 32 == 0


@pytest.mark.parametrize('output_type', ['image', 'video'])
def test_line_uses_reference_orientation_and_explicit_prompt_wins(monkeypatch, tmp_path, output_type):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    path = runtime.upload_folder / 'portrait.jpg'
    # Stored landscape pixels with EXIF rotation represent a portrait reference.
    image = Image.new('RGB', (160, 90), 'blue')
    exif = image.getexif()
    exif[274] = 6
    image.save(path, exif=exif)
    for prompt, expected in [('Animate this image', (864, 1536)), ('Use 16:9', (1536, 864))]:
        assert adapter.submit_output('U123', prompt, output_type, [path.name]) is True
        extra = runtime.job_service.calls[-1][0]['extra_params']
        if output_type == 'image':
            assert extra['size'] == f'{expected[0]}x{expected[1]}'
        else:
            assert (extra['width'], extra['height']) == expected


@pytest.mark.parametrize(('width', 'height', 'expected'), [(864, 1536, (720, 1280)), (1536, 864, (1280, 720))])
def test_line_video_preview_preserves_portrait_and_landscape(tmp_path, width, height, expected):
    runtime = FakeRuntime(tmp_path)
    video = tmp_path / 'video.mp4'
    video.write_bytes(_mp4_header(width, height))
    preview = tmp_path / 'preview.jpg'
    assert LineAdapter(runtime)._create_preview(preview, video_path=video)
    with Image.open(preview) as image:
        assert image.size == expected


def test_line_image_preview_does_not_stretch_portrait(tmp_path):
    runtime = FakeRuntime(tmp_path)
    image_path = tmp_path / 'portrait.png'
    Image.new('RGB', (864, 1536), 'blue').save(image_path)
    preview = tmp_path / 'preview.jpg'
    assert LineAdapter(runtime)._create_preview(preview, image_path=image_path)
    with Image.open(preview) as image:
        assert image.size == (576, 1024)


def test_image_completion_preview_push_and_download(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    output = runtime.storage_output_dir / "job-line-1.png"
    output.write_bytes(_png())
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "output_type": "image", "workflow_id": "image_gpt25_sunburst",
        "notification_state": "pending", "notification_attempts": "0",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={
        "status": "completed", "image_url": "/outputs/job-line-1.png",
    })
    pushed = []
    monkeypatch.setattr(adapter, "push_image", lambda user, image, preview: pushed.append((user, image, preview)) or True)
    assert adapter.poll_once() == 1
    assert pushed and pushed[0][0] == "U123"
    token = next(key.split(":", 2)[2] for key in runtime.redis_client.values if key.startswith("line:download:"))
    record = json.loads(runtime.redis_client.get(f"line:download:{token}"))
    assert record["kind"] == "image"

    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    client = app.test_client()
    response = client.get(f"/line/download/{token}")
    assert response.status_code == 200 and response.mimetype == "image/png"
    assert "image.png" in response.headers["Content-Disposition"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    preview = client.get(f"/line/preview/{token}")
    assert preview.status_code == 200 and preview.mimetype == "image/jpeg"
    assert len(preview.data) <= 1024 * 1024
    assert client.get("/line/download/invalid-token").status_code == 404
    assert client.get("/line/preview/invalid-token").status_code == 404

    bad_token = "b" * 32
    runtime.redis_client.setex(
        f"line:download:{bad_token}",
        1800,
        json.dumps({"job_id": "job-line-1", "kind": "image", "output_name": "../outside.png"}),
    )
    assert client.get(f"/line/download/{bad_token}").status_code == 404


def test_oversized_image_result_sends_failure_without_token(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    (runtime.storage_output_dir / "large.png").write_bytes(b"x" * (line_routes.LINE_MAX_IMAGE_BYTES + 1))
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "output_type": "image",
        "notification_state": "pending", "notification_attempts": "0",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={
        "status": "completed", "image_url": "/outputs/large.png",
    })
    messages = []
    monkeypatch.setattr(adapter, "push", lambda _user, text: messages.append(text) or True)
    assert adapter.poll_once() == 1
    assert messages == [line_routes.REPLY_GENERATION_FAILED]
    assert not any(key.startswith("line:download:") for key in runtime.redis_client.values)


def test_image_push_failure_keeps_bounded_retry_state(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    monkeypatch.setattr(line_routes, "LINE_NOTIFICATION_RETRY_LIMIT", 2)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    (runtime.storage_output_dir / "image.png").write_bytes(_png())
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "output_type": "image",
        "notification_state": "pending", "notification_attempts": "0",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={
        "status": "completed", "image_url": "/outputs/image.png",
    })
    monkeypatch.setattr(adapter, "push_image", lambda *_args: False)
    assert adapter.poll_once() == 1
    mapping = runtime.redis_client.hgetall("line:job:job-line-1")
    assert mapping["notification_state"] == "retry" and mapping["notification_attempts"] == "1"
    assert not any(key.startswith("line:download:") for key in runtime.redis_client.values)
    assert not list(runtime.storage_output_dir.glob("line_preview_*.jpg"))
    assert adapter.poll_once() == 1
    mapping = runtime.redis_client.hgetall("line:job:job-line-1")
    assert mapping["notification_state"] == "failed" and mapping["notification_attempts"] == "2"


def test_running_jobs_wait_and_failed_job_notifies_once(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    runtime.redis_client.hset("line:job:job-running", mapping={
        "job_id": "job-running", "user_id": "U123", "output_type": "video", "notification_state": "pending",
    })
    runtime.redis_client.hset("job:status:job-running", mapping={"status": "running"})
    pushes = []
    monkeypatch.setattr(adapter, "push", lambda _user, text: pushes.append(text) or True)
    assert adapter.poll_once() == 0 and pushes == []

    runtime.redis_client.hset("job:status:job-running", mapping={"status": "failed"})
    assert adapter.poll_once() == 1
    assert pushes == [line_routes.REPLY_GENERATION_FAILED]
    assert runtime.redis_client.hgetall("line:job:job-running")["notification_state"] == "notified_failure"
    assert adapter.poll_once() == 0 and len(pushes) == 1


def test_second_choice_uses_existing_queue_notice(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    sent = patch_line_api(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    runtime.redis_client.hset("line:job:job-old", mapping={
        "job_id": "job-old", "user_id": "U123", "output_type": "video", "workflow_id": "video_minimax_h3",
    })
    runtime.redis_client.hset("job:status:job-old", mapping={"status": "running"})
    adapter.handle_event(_message(text="Next prompt"))
    adapter.handle_event(_postback("output=image"))
    assert runtime.job_service.calls[0][0]["workflow"] == "image_gpt25_sunburst"
    assert sent[-1][1]["messages"][0]["text"] == line_routes.REPLY_QUEUED


def test_line_adapter_boundary_has_no_runtime_bypass():
    source = (BACKEND_SRC / "line_routes.py").read_text(encoding="utf-8")
    assert "comfy_client" not in source.lower()
    assert "rpush" not in source.lower()
    assert "build_job_data" not in source
    assert "LINE_VIDEO_WORKFLOW_ID" not in source
