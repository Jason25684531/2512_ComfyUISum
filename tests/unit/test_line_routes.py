import base64
import hashlib
import hmac
import io
import json
import logging
import sys
from pathlib import Path

from PIL import Image

BACKEND_SRC = Path(__file__).resolve().parents[2] / "backend" / "src"
sys.modules.pop("config", None)
sys.path.insert(0, str(BACKEND_SRC))

import line_routes  # noqa: E402
from line_routes import LineAdapter, create_blueprint, verify_line_signature  # noqa: E402
sys.path.remove(str(BACKEND_SRC))
sys.modules.pop("config", None)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value

    def set(self, key, value, ex=None, nx=False):
        if nx and (key in self.values or key in self.hashes):
            return False
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)
        self.hashes.pop(key, None)

    def expire(self, _key, _ttl):
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

    def submit(self, payload, **kwargs):
        self.calls.append((payload, kwargs))
        return {"job_id": self.next_job_id, "status": "queued"}, 202


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
    monkeypatch.setattr(line_routes, "LINE_VIDEO_WORKFLOW_ID", "ltx_i2v")


def test_signature_and_text_t2v_route(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    sent = []
    monkeypatch.setattr(line_routes.requests, "request", lambda *args, **kwargs: sent.append(kwargs["json"]) or LineResponse())
    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    event = {
        "events": [{
            "type": "message",
            "replyToken": "reply-token",
            "source": {"userId": "U123"},
            "message": {"id": "12345", "type": "text", "text": "A robot walking through Taipei at night."},
        }]
    }
    body, signature = signed_body(event)
    response = app.test_client().post("/line/webhook", data=body, headers={"X-Line-Signature": signature})
    assert response.status_code == 200
    assert runtime.job_service.calls[0][0]["workflow"] == "ltx_i2v"
    assert runtime.job_service.calls[0][0]["video_mode"] == "t2v"
    assert runtime.job_service.calls[0][0]["images"] == {}
    assert sent[0]["messages"][0]["text"] == "影片生成中。"
    assert verify_line_signature(body, signature, "test-secret")

    invalid = app.test_client().post("/line/webhook", data=body, headers={"X-Line-Signature": "bad"})
    assert invalid.status_code == 401
    assert len(runtime.job_service.calls) == 1


def test_second_prompt_uses_existing_queue_and_reports_queued(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    runtime.job_service.next_job_id = "job-line-2"
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "mode": "t2v",
        "workflow_id": "ltx_i2v", "notification_state": "pending",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={"status": "running"})
    replies = []
    monkeypatch.setattr(line_routes.requests, "request", lambda *args, **kwargs: replies.append(kwargs["json"]) or LineResponse())
    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    event = {"events": [{
        "type": "message", "replyToken": "reply-token", "source": {"userId": "U123"},
        "message": {"id": "12346", "type": "text", "text": "A second prompt."},
    }]}
    body, signature = signed_body(event)
    response = app.test_client().post("/line/webhook", data=body, headers={"X-Line-Signature": signature})
    assert response.status_code == 200
    assert runtime.job_service.calls[0][0]["video_mode"] == "t2v"
    assert replies[0]["messages"][0]["text"] == line_routes.REPLY_QUEUED


def test_image_pending_then_i2v_and_expiry_routes_to_t2v(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    image_buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(image_buffer, format="PNG")

    class ImageResponse:
        status_code = 200
        headers = {"Content-Type": "image/png", "Content-Length": str(len(image_buffer.getvalue()))}

        def iter_content(self, chunk_size):
            yield image_buffer.getvalue()

        def close(self):
            pass

    replies = []
    monkeypatch.setattr(line_routes.requests, "get", lambda *args, **kwargs: ImageResponse())
    monkeypatch.setattr(line_routes.requests, "request", lambda *args, **kwargs: replies.append(kwargs["json"]) or LineResponse())
    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    client = app.test_client()

    image_event = {"events": [{
        "type": "message", "replyToken": "image-reply", "source": {"userId": "U123"},
        "message": {"id": "67890", "type": "image"},
    }]}
    body, signature = signed_body(image_event)
    assert client.post("/line/webhook", data=body, headers={"X-Line-Signature": signature}).status_code == 200
    pending = runtime.redis_client.get("line:user:U123")
    assert json.loads(pending)["state"] == "i2v_wait_prompt"
    assert replies[-1]["messages"][0]["text"] == "圖片已收到，請輸入影片動作描述。"

    text_event = {"events": [{
        "type": "message", "replyToken": "text-reply", "source": {"userId": "U123"},
        "message": {"id": "67891", "type": "text", "text": "The character turns and waves."},
    }]}
    body, signature = signed_body(text_event)
    assert client.post("/line/webhook", data=body, headers={"X-Line-Signature": signature}).status_code == 200
    assert runtime.job_service.calls[-1][0]["video_mode"] == "i2v"
    assert runtime.job_service.calls[-1][0]["images"]["input"].startswith("data:image/png;base64,")
    assert runtime.redis_client.get("line:user:U123") is None

    runtime.redis_client.setex(
        "line:user:U123", 1200,
        json.dumps({"state": "i2v_wait_prompt", "image_path": "missing.png", "created_at": "2000-01-01T00:00:00Z"}),
    )
    expired = {"events": [{
        "type": "message", "replyToken": "expired-reply", "source": {"userId": "U123"},
        "message": {"id": "67892", "type": "text", "text": "Use a city timelapse."},
    }]}
    body, signature = signed_body(expired)
    client.post("/line/webhook", data=body, headers={"X-Line-Signature": signature})
    assert runtime.job_service.calls[-1][0]["video_mode"] == "t2v"


def test_completion_token_download_and_traversal_rejection(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    output = runtime.storage_output_dir / "job-line-1.mp4"
    output.write_bytes(b"valid mp4 bytes")
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "mode": "t2v", "workflow_id": "ltx_i2v",
        "notification_state": "pending", "notification_attempts": "0",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={
        "status": "finished", "image_url": "/outputs/job-line-1.mp4",
    })
    pushed = []
    monkeypatch.setattr(adapter, "push_video", lambda user, video, preview: pushed.append((user, video, preview)) or True)
    assert adapter.poll_once() == 1
    assert pushed and "https://public.example/line/download/" in pushed[0][1]
    assert "/line/preview/" in pushed[0][2]
    token_key = next(key for key in runtime.redis_client.values if key.startswith("line:download:"))
    token = token_key.split(":", 2)[2]

    app = __import__("flask").Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    response = app.test_client().get(f"/line/download/{token}")
    assert response.status_code == 200
    assert response.mimetype == "video/mp4"
    assert "video.mp4" in response.headers["Content-Disposition"]

    preview = app.test_client().get(f"/line/preview/{token}")
    assert preview.status_code == 200
    assert preview.mimetype == "image/jpeg"
    assert len(preview.data) <= 1024 * 1024

    bad_token = "b" * 32
    runtime.redis_client.setex(
        f"line:download:{bad_token}", 1800,
        json.dumps({"job_id": "job-line-1", "output_name": "../outside.mp4"}),
    )
    traversal = app.test_client().get("/line/download/" + bad_token)
    assert traversal.status_code == 404


def test_video_message_payload_uses_https_media_urls(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    sent = []
    monkeypatch.setattr(line_routes.requests, "request", lambda *args, **kwargs: sent.append(kwargs["json"]) or LineResponse())

    assert adapter.push_video("U123", "https://public.example/line/download/token", "https://public.example/line/preview/token")
    message = sent[0]["messages"][0]
    assert message == {
        "type": "video",
        "originalContentUrl": "https://public.example/line/download/token",
        "previewImageUrl": "https://public.example/line/preview/token",
    }
    assert not adapter.push_video("U123", "http://public.example/video", "https://public.example/preview")


def test_invalid_workflow_and_line_image_api_failure_do_not_enqueue(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    monkeypatch.setattr(line_routes, "LINE_VIDEO_WORKFLOW_ID", "missing-workflow")
    body, signature = signed_body({"events": [{
        "type": "message", "replyToken": "reply", "source": {"userId": "U123"},
        "message": {"id": "1", "type": "text", "text": "prompt"},
    }]})
    payload, status = adapter.process_webhook(body, signature)
    assert status == 200 and payload["ok"] is True
    assert runtime.job_service.calls == []

    monkeypatch.setattr(line_routes, "LINE_VIDEO_WORKFLOW_ID", "ltx_i2v")

    class FailedResponse:
        status_code = 500
        headers = {}

        def close(self):
            pass

    monkeypatch.setattr(line_routes.requests, "get", lambda *args, **kwargs: FailedResponse())
    image_body, image_signature = signed_body({"events": [{
        "type": "message", "replyToken": "reply", "source": {"userId": "U123"},
        "message": {"id": "2", "type": "image"},
    }]})
    adapter.process_webhook(image_body, image_signature)
    assert runtime.redis_client.get("line:user:U123") is None
    assert runtime.job_service.calls == []


def test_completion_push_failure_keeps_bounded_retry_state(monkeypatch, tmp_path):
    patch_line_config(monkeypatch)
    monkeypatch.setattr(line_routes, "LINE_NOTIFICATION_RETRY_LIMIT", 2)
    runtime = FakeRuntime(tmp_path)
    adapter = LineAdapter(runtime)
    (runtime.storage_output_dir / "job-line-1.mp4").write_bytes(b"valid mp4 bytes")
    runtime.redis_client.hset("line:job:job-line-1", mapping={
        "job_id": "job-line-1", "user_id": "U123", "notification_state": "pending",
        "notification_attempts": "0",
    })
    runtime.redis_client.hset("job:status:job-line-1", mapping={
        "status": "completed", "image_url": "/outputs/job-line-1.mp4",
    })
    monkeypatch.setattr(adapter, "push", lambda *_args: False)
    assert adapter.poll_once() == 1
    assert runtime.redis_client.hgetall("line:job:job-line-1")["notification_state"] == "retry"
    assert adapter.poll_once() == 1
    assert runtime.redis_client.hgetall("line:job:job-line-1")["notification_state"] == "failed"


def test_line_adapter_boundary_has_no_runtime_bypass():
    source = (BACKEND_SRC / "line_routes.py").read_text(encoding="utf-8")
    assert "ComfyUI" not in source
    assert "rpush" not in source.lower()
    assert "build_job_data" not in source
