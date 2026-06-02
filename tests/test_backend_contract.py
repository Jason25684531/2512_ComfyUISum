import base64
import json
import os
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from redis import RedisError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

os.environ.setdefault("STUDIO_ENV_FILE", ".env.local")
os.environ.setdefault("REDIS_CONNECT_RETRIES", "0")
os.environ.setdefault("REDIS_HOST", "127.0.0.1")
os.environ.setdefault("REDIS_PORT", "1")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "1")
os.environ.setdefault("DB_PASSWORD", "test-password")

import app as backend_app
import config as backend_config
from shared.security import OPERATION_FAILED_MESSAGE


@pytest.fixture(autouse=True)
def isolate_backend_app(monkeypatch, tmp_path):
    monkeypatch.setitem(backend_app.app.config, "TESTING", True)
    monkeypatch.setitem(backend_app.app.config, "RATELIMIT_ENABLED", False)
    monkeypatch.setattr(backend_app.limiter, "enabled", False)
    monkeypatch.setattr(backend_app, "redis_client", None)
    monkeypatch.setattr(backend_app, "db_client", None)
    monkeypatch.setattr(backend_app, "VEO3_TEST_MODE", False)
    upload_dir = tmp_path / "inputs"
    upload_dir.mkdir()
    monkeypatch.setattr(backend_app, "UPLOAD_FOLDER", upload_dir)
    yield


class RecordingRedis:
    def __init__(
        self,
        events=None,
        status_map=None,
        warmup_map=None,
        heartbeat="alive",
        ping_result=True,
    ):
        self.events = events if events is not None else []
        self.enqueued = []
        self.hashes = dict(status_map or {})
        self.expires = {}
        self.warmup_map = dict(warmup_map or {})
        self.heartbeat = heartbeat
        self.ping_result = ping_result

    def rpush(self, queue_name, payload):
        self.events.append("redis:rpush")
        self.enqueued.append((queue_name, json.loads(payload)))

    def hset(self, name, key=None, value=None, mapping=None):
        self.events.append("redis:hset")
        self.hashes.setdefault(name, {})
        if mapping is not None:
            self.hashes[name].update(mapping)
        elif key is not None:
            self.hashes[name][key] = value

    def expire(self, key, ttl):
        self.events.append("redis:expire")
        self.expires[key] = ttl

    def hgetall(self, key):
        if key == backend_app.WARMUP_STATUS_KEY:
            return dict(self.warmup_map)
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def get(self, key):
        if key == "worker:heartbeat":
            return self.heartbeat
        return None

    def keys(self, pattern):
        if pattern == "job:status:*":
            return [key for key in self.hashes if key.startswith("job:status:")]
        return []

    def llen(self, key):
        self.events.append("redis:llen")
        return len(self.enqueued)

    def ping(self):
        return self.ping_result


class FailingPushRedis(RecordingRedis):
    def rpush(self, queue_name, payload):
        self.events.append("redis:rpush")
        raise RedisError("redis push failed <secret>")


class RecordingSession:
    def __init__(self, events=None, query_result=None):
        self.events = events if events is not None else []
        self.added = []
        self.query_result = query_result
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def add(self, value):
        self.events.append("db:add")
        self.added.append(value)

    def flush(self):
        self.events.append("db:flush")

    def commit(self):
        self.events.append("db:commit")
        self.committed = True

    def rollback(self):
        self.events.append("db:rollback")
        self.rolled_back = True

    def close(self):
        self.events.append("db:close")
        self.closed = True

    def query(self, model):
        return RecordingQuery(self.query_result)


class RecordingQuery:
    def __init__(self, result):
        self.result = result

    def filter_by(self, **kwargs):
        if self.result is None:
            return self
        for key, value in kwargs.items():
            if getattr(self.result, key, None) != value:
                return RecordingQuery(None)
        return self

    def first(self):
        return self.result


class RecordingDbClient:
    def __init__(self, history_jobs=None, connection_ok=True):
        self.history_jobs = list(history_jobs or [])
        self.connection_ok = connection_ok
        self.history_calls = []
        self.status_updates = []
        self.seen_ips = []

    def get_or_create_user_id(self, ip_address):
        self.seen_ips.append(ip_address)
        return 1

    def get_history(self, limit=50, offset=0, user_id=None):
        self.history_calls.append({
            "limit": limit,
            "offset": offset,
            "user_id": user_id,
        })
        return self.history_jobs[offset:offset + limit]

    def update_job_status(self, job_id, status, output_path=None):
        self.status_updates.append({
            "job_id": job_id,
            "status": status,
            "output_path": output_path,
        })
        return True

    def check_connection(self):
        return self.connection_ok


class DbJob:
    def __init__(self, job_id, status, created_at=None):
        self.id = job_id
        self.status = status
        self.created_at = created_at or datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def test_generate_success_records_db_redis_and_response_contract(monkeypatch):
    events = []
    fake_redis = RecordingRedis(events=events)
    fake_session = RecordingSession(events=events)
    fake_db_client = RecordingDbClient()
    monkeypatch.setattr(backend_app, "redis_client", fake_redis)
    monkeypatch.setattr(backend_app, "db_client", fake_db_client)
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)

    audio_data = base64.b64encode(b"wav-bytes").decode("ascii")
    response = backend_app.app.test_client().post(
        "/api/generate",
        json={
            "workflow": "multi_image_blend",
            "prompt": "blend these",
            "seed": 123,
            "model": "turbo_fp8",
            "aspect_ratio": "1:1",
            "batch_size": 2,
            "images": {},
            "audio": f"data:audio/wav;base64,{audio_data}",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"job_id", "status", "message"}
    assert payload["job_id"]
    assert payload["status"] == "queued"

    assert fake_session.committed is True
    assert fake_session.rolled_back is False
    assert len(fake_session.added) == 1
    db_job = fake_session.added[0]
    assert db_job.id == payload["job_id"]
    assert db_job.status == "queued"
    assert db_job.workflow_name == "multi_image_blend"
    assert db_job.seed == 123

    assert len(fake_redis.enqueued) == 1
    queue_name, job_data = fake_redis.enqueued[0]
    assert queue_name == backend_app.REDIS_QUEUE_NAME
    assert job_data["job_id"] == payload["job_id"]
    assert job_data["workflow"] == "multi_image_blend"
    assert job_data["prompt"] == "blend these"
    assert job_data["seed"] == 123
    assert job_data["audio"].startswith("audio_")
    assert (backend_app.UPLOAD_FOLDER / job_data["audio"]).read_bytes() == b"wav-bytes"

    status_key = f"job:status:{payload['job_id']}"
    assert fake_redis.hashes[status_key] == {
        "job_id": payload["job_id"],
        "status": "queued",
        "progress": 0,
        "image_url": "",
        "error": "",
        "updated_at": fake_redis.hashes[status_key]["updated_at"],
    }
    assert fake_redis.expires[status_key] == 86400
    assert events[:7] == [
        "db:add",
        "db:flush",
        "redis:rpush",
        "redis:hset",
        "redis:expire",
        "db:commit",
        "db:close",
    ]


def test_generate_redis_push_failure_rolls_back_and_preserves_error_contract(monkeypatch):
    events = []
    fake_session = RecordingSession(events=events)
    monkeypatch.setattr(backend_app, "redis_client", FailingPushRedis(events=events))
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)

    response = backend_app.app.test_client().post(
        "/api/generate",
        json={"workflow": "multi_image_blend", "prompt": "blend these"},
    )

    assert response.status_code == 500
    assert response.get_json() == {"error": OPERATION_FAILED_MESSAGE}
    assert fake_session.rolled_back is True
    assert fake_session.committed is False
    assert events[:4] == ["db:add", "db:flush", "redis:rpush", "db:rollback"]


def test_upload_rejects_invalid_extension_and_missing_file(monkeypatch):
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())
    client = backend_app.app.test_client()

    invalid = client.post(
        "/api/upload",
        data={"file": (BytesIO(b"not audio"), "voice.txt")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"].startswith("Unsupported file type.")

    missing = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert missing.status_code == 400
    assert missing.get_json() == {"error": "No file provided"}


def test_upload_accepts_audio_and_normalizes_unsafe_original_filename(monkeypatch):
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())

    response = backend_app.app.test_client().post(
        "/api/upload",
        data={"file": (BytesIO(b"wav"), "../../voice.wav")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["filename"].startswith("audio_")
    assert payload["filename"].endswith(".wav")
    assert "/" not in payload["filename"]
    assert "\\" not in payload["filename"]
    assert (backend_app.UPLOAD_FOLDER / payload["filename"]).read_bytes() == b"wav"


def test_generate_missing_text_prompt_and_missing_images_follow_current_contract(monkeypatch):
    fake_redis = RecordingRedis()
    fake_session = RecordingSession()
    monkeypatch.setattr(backend_app, "redis_client", fake_redis)
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)
    client = backend_app.app.test_client()

    missing_prompt = client.post("/api/generate", json={"workflow": "text_to_image"})
    assert missing_prompt.status_code == 400
    assert missing_prompt.get_json() == {"error": "prompt is required for text_to_image"}

    missing_images = client.post(
        "/api/generate",
        json={"workflow": "multi_image_blend", "prompt": "no images supplied"},
    )
    assert missing_images.status_code == 200
    assert missing_images.get_json()["status"] == "queued"
    assert fake_redis.enqueued[-1][1]["images"] == {}


def test_status_returns_redis_hit_and_not_found(monkeypatch):
    fake_db = RecordingDbClient()
    fake_redis = RecordingRedis(status_map={
        "job:status:job-1": {
            "job_id": "job-1",
            "status": "finished",
            "progress": "100",
            "image_url": "/outputs/job-1.png",
            "error": "",
        }
    })
    monkeypatch.setattr(backend_app, "redis_client", fake_redis)
    monkeypatch.setattr(backend_app, "db_client", fake_db)
    monkeypatch.setattr(backend_app, "get_db_session", lambda: RecordingSession(query_result=None))
    client = backend_app.app.test_client()

    found = client.get("/api/status/job-1")
    assert found.status_code == 200
    assert found.get_json() == {
        "job_id": "job-1",
        "status": "finished",
        "progress": 100,
        "image_url": "/outputs/job-1.png",
        "error": "",
        "source": "redis",
    }
    assert fake_db.status_updates == [{
        "job_id": "job-1",
        "status": "finished",
        "output_path": "/outputs/job-1.png",
    }]

    missing = client.get("/api/status/missing-job")
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "Job not found"
    assert missing.get_json()["job_id"] == "missing-job"


def test_status_database_fallback_shape(monkeypatch):
    db_job = DbJob("job-db", "finished")
    fake_session = RecordingSession(query_result=db_job)
    monkeypatch.setattr(backend_app, "redis_client", RecordingRedis())
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)

    response = backend_app.app.test_client().get("/api/status/job-db")

    assert response.status_code == 200
    assert response.get_json() == {
        "job_id": "job-db",
        "status": "finished",
        "progress": 100,
        "image_url": "/outputs/job-db_0.png",
        "error": "",
        "source": "database",
        "created_at": db_job.created_at.isoformat(),
    }
    assert fake_session.closed is True


def test_history_pagination_empty_and_response_shape(monkeypatch):
    jobs = [
        {"id": "job-1", "prompt": "one", "workflow": "text_to_image", "model": "m1", "status": "finished", "output_path": r"C:\out\one.png"},
        {"id": "job-2", "prompt": "two", "workflow": "text_to_image", "model": "m2", "status": "failed", "output_path": ""},
        {"id": "job-3", "prompt": "three", "workflow": "text_to_image", "model": "m3", "status": "queued", "output_path": "/tmp/three.png"},
    ]
    fake_db = RecordingDbClient(history_jobs=jobs)
    monkeypatch.setattr(backend_app, "db_client", fake_db)
    client = backend_app.app.test_client()

    page = client.get("/api/history?limit=2&offset=1")
    assert page.status_code == 200
    payload = page.get_json()
    assert set(payload) == {"total", "limit", "offset", "jobs"}
    assert payload["total"] == 2
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [job["id"] for job in payload["jobs"]] == ["job-2", "job-3"]
    assert payload["jobs"][1]["output_path"] == "/outputs/three.png"
    assert fake_db.history_calls[-1] == {"limit": 2, "offset": 1, "user_id": None}

    empty = client.get("/api/history?limit=2&offset=20")
    assert empty.status_code == 200
    assert empty.get_json() == {"total": 0, "limit": 2, "offset": 20, "jobs": []}


def test_models_response_shape_and_missing_directory_fallback(monkeypatch, tmp_path):
    checkpoints = tmp_path / "checkpoints"
    unet = tmp_path / "unet"
    checkpoints.mkdir()
    unet.mkdir()
    (checkpoints / "b.ckpt").write_text("model", encoding="utf-8")
    nested = checkpoints / "nested"
    nested.mkdir()
    (nested / "a.safetensors").write_text("model", encoding="utf-8")
    (unet / "u.pt").write_text("model", encoding="utf-8")
    (unet / "ignored.txt").write_text("model", encoding="utf-8")
    monkeypatch.setattr(backend_config, "COMFYUI_CHECKPOINTS_DIR", checkpoints)
    monkeypatch.setattr(backend_config, "COMFYUI_UNET_DIR", unet)

    response = backend_app.app.test_client().get("/api/models")

    assert response.status_code == 200
    assert response.get_json() == {
        "models": ["b.ckpt", str(Path("nested") / "a.safetensors")],
        "unet_models": ["u.pt"],
    }

    monkeypatch.setattr(backend_config, "COMFYUI_CHECKPOINTS_DIR", tmp_path / "missing-checkpoints")
    monkeypatch.setattr(backend_config, "COMFYUI_UNET_DIR", tmp_path / "missing-unet")
    fallback = backend_app.app.test_client().get("/api/models")
    assert fallback.status_code == 200
    assert fallback.get_json() == {
        "models": ["default_model.safetensors"],
        "unet_models": ["z-image/z-image-turbo-fp8-e4m3fn.safetensors"],
    }


def test_cancel_updates_existing_job_and_handles_missing_job(monkeypatch):
    fake_redis = RecordingRedis(status_map={
        "job:status:queued-job": {
            "job_id": "queued-job",
            "status": "queued",
            "progress": "0",
            "image_url": "",
            "error": "",
        }
    })
    monkeypatch.setattr(backend_app, "redis_client", fake_redis)
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())
    client = backend_app.app.test_client()

    response = client.post("/api/cancel/queued-job")
    assert response.status_code == 200
    assert response.get_json() == {"success": True, "message": "Task cancelled"}
    assert fake_redis.hashes["job:status:queued-job"]["status"] == "cancelled"
    assert fake_redis.hashes["job:status:queued-job"]["error"] == "Task cancelled by user"

    missing = client.post("/api/cancel/missing-job")
    assert missing.status_code == 404
    assert missing.get_json() == {"error": "Job not found"}


def test_health_all_dependencies_healthy_and_partial_failure(monkeypatch):
    healthy_redis = RecordingRedis(warmup_map={"status": "ready"}, heartbeat="alive", ping_result=True)
    monkeypatch.setattr(backend_app, "redis_client", healthy_redis)
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient(connection_ok=True))

    healthy = backend_app.app.test_client().get("/api/health")
    assert healthy.status_code == 200
    healthy_payload = healthy.get_json()
    assert healthy_payload["status"] == "ok"
    assert healthy_payload["redis"] == "healthy"
    assert healthy_payload["mysql"] == "healthy"
    assert healthy_payload["worker"] == "online"
    assert healthy_payload["warnings"] == []

    offline_redis = RecordingRedis(warmup_map={}, heartbeat=None, ping_result=False)
    monkeypatch.setattr(backend_app, "redis_client", offline_redis)
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient(connection_ok=False))

    partial = backend_app.app.test_client().get("/api/health")
    assert partial.status_code == 200
    partial_payload = partial.get_json()
    assert partial_payload["status"] == "degraded"
    assert partial_payload["redis"] == "unavailable"
    assert partial_payload["mysql"] == "error"
    assert partial_payload["worker"] == "offline"
    assert "Worker heartbeat unavailable" in partial_payload["warnings"]


def test_outputs_valid_missing_and_traversal_behavior(monkeypatch, tmp_path):
    output_file = tmp_path / "safe.png"
    output_file.write_bytes(b"png-bytes")
    outside_file = tmp_path.parent / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    monkeypatch.setenv("STORAGE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(backend_app, "db_client", RecordingDbClient())
    client = backend_app.app.test_client()

    valid = client.get("/outputs/safe.png")
    assert valid.status_code == 200
    assert valid.data == b"png-bytes"
    assert valid.mimetype == "image/png"

    missing = client.get("/outputs/missing.png")
    assert missing.status_code == 404

    traversal = client.get("/outputs/%2e%2e/secret.txt")
    assert traversal.status_code == 404
    assert traversal.data != b"secret"
