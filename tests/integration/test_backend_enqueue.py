import requests


def load_backend(monkeypatch):
    import sys
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend" / "src"))
    original_config = sys.modules.pop("config", None)
    sys.modules.pop("app", None)
    import app as backend
    sys.modules.pop("config", None)
    if original_config is not None:
        sys.modules["config"] = original_config
    return backend


def test_status_fallback_contract():
    response = requests.get("http://127.0.0.1:5000/api/status/not-a-real-job", timeout=3)
    assert response.status_code == 404


def test_multi_angle_enqueue_validation(monkeypatch):
    import json
    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.local")
    monkeypatch.setenv("REDIS_CONNECT_RETRIES", "0")
    monkeypatch.setenv("REDIS_CONNECT_INITIAL_DELAY", "0")
    backend = load_backend(monkeypatch)

    class FakeRedis:
        def __init__(self):
            self.queue = []

        def __bool__(self):
            return False  # Skip the unrelated durable-outbox replay before each request.

        def rpush(self, _key, payload):
            self.queue.append(payload)

        def hset(self, *_args, **_kwargs):
            pass

        def expire(self, *_args, **_kwargs):
            pass

        def llen(self, _key):
            return len(self.queue)

    fake_redis = FakeRedis()
    monkeypatch.setattr(backend, "redis_client", fake_redis)
    monkeypatch.setattr(backend, "JOB_OBSERVABILITY_ENABLED", False)
    client = backend.app.test_client()

    valid = client.post("/api/generate", json={
        "workflow": "multi_angle",
        "images": {"input": "fixture.png"},
        "horizontal_angle": 90,
        "vertical_angle": 30,
        "zoom": 7.5,
    })
    assert valid.status_code == 200
    assert json.loads(fake_redis.queue[0])["extra_params"] == {
        "horizontal_angle": 90,
        "vertical_angle": 30,
        "zoom": 7.5,
    }

    out_of_range = client.post("/api/generate", json={
        "workflow": "multi_angle", "images": {"input": "fixture.png"}, "vertical_angle": 90,
    })
    missing_image = client.post("/api/generate", json={"workflow": "multi_angle", "images": {}})
    assert out_of_range.status_code == 400
    assert missing_image.status_code == 400
    assert len(fake_redis.queue) == 1


def test_ltx_enqueue_validation(monkeypatch):
    import json
    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.local")
    monkeypatch.setenv("REDIS_CONNECT_RETRIES", "0")
    monkeypatch.setenv("REDIS_CONNECT_INITIAL_DELAY", "0")
    backend = load_backend(monkeypatch)

    class FakeRedis:
        def __init__(self):
            self.queue = []

        def __bool__(self):
            return False

        def rpush(self, _key, payload):
            self.queue.append(payload)

        def hset(self, *_args, **_kwargs):
            pass

        def expire(self, *_args, **_kwargs):
            pass

    fake_redis = FakeRedis()
    monkeypatch.setattr(backend, "redis_client", fake_redis)
    monkeypatch.setattr(backend, "JOB_OBSERVABILITY_ENABLED", False)
    client = backend.app.test_client()

    valid = client.post("/api/generate", json={
        "workflow": "ltx_i2v", "prompt": "test", "images": {"input": "fixture.png"},
        "video_width": 1280, "video_height": 704, "video_duration": 6,
    })
    assert valid.status_code == 202
    assert json.loads(fake_redis.queue[0])["extra_params"] == {
        "video_width": 1280, "video_height": 704, "video_duration": 6,
    }

    for field, value in (("video_duration", 30), ("video_width", 256), ("video_width", "1280; DROP TABLE")):
        response = client.post("/api/generate", json={
            "workflow": "ltx_i2v", "images": {"input": "fixture.png"}, field: value,
        })
        assert response.status_code == 400
        assert str(value) not in response.json["error"]
    assert len(fake_redis.queue) == 1

    missing_last_frame = client.post("/api/generate", json={
        "workflow": "ltx_flf", "images": {"first_frame": "start.png"},
    })
    assert missing_last_frame.status_code == 400

    defaults = client.post("/api/generate", json={
        "workflow": "ltx_i2v", "images": {"input": "fixture.png"},
    })
    assert defaults.status_code == 202
    assert json.loads(fake_redis.queue[-1])["extra_params"] == {}


def test_retired_video_workflows_are_rejected_before_enqueue(monkeypatch):
    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.local")
    monkeypatch.setenv("REDIS_CONNECT_RETRIES", "0")
    monkeypatch.setenv("REDIS_CONNECT_INITIAL_DELAY", "0")
    monkeypatch.setenv("VEO3_TEST_MODE", "true")
    backend = load_backend(monkeypatch)

    class FakeRedis:
        def __init__(self):
            self.queue = []

        def __bool__(self):
            return False

        def rpush(self, _key, payload):
            self.queue.append(payload)

        def llen(self, _key):
            return len(self.queue)

    fake_redis = FakeRedis()
    monkeypatch.setattr(backend, "redis_client", fake_redis)
    monkeypatch.setattr(backend, "JOB_OBSERVABILITY_ENABLED", False)
    client = backend.app.test_client()

    for workflow in ("veo3_long_video", "t2v_veo3", "flf_veo3", "T2V", "FLF"):
        response = client.post("/api/generate", json={"workflow": workflow, "prompt": "test"})
        assert response.status_code == 400
        assert response.json == {"error": "Unsupported workflow"}
    assert fake_redis.queue == []


def test_parameterized_workflows_have_backend_validation_paths():
    from pathlib import Path

    from shared.workflow_catalog import WorkflowCatalog

    root = Path(__file__).resolve().parents[2]
    catalog = WorkflowCatalog.from_paths(root / "ComfyUIworkflow" / "config.json", root / "ComfyUIworkflow")
    parameterized = {entry.workflow_id for entry in catalog.entries.values() if entry.mapping.get("param_map")}
    assert parameterized <= {"ltx_retake_v2v", "multi_angle", "ideogram4_regional_t2i", "ltx_i2v", "ltx_flf"}
