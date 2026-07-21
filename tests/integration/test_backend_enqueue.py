import requests


def test_status_fallback_contract():
    response = requests.get("http://127.0.0.1:5000/api/status/not-a-real-job", timeout=3)
    assert response.status_code == 404


def test_multi_angle_enqueue_validation(monkeypatch):
    import json
    import sys
    from pathlib import Path

    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.local")
    monkeypatch.setenv("REDIS_CONNECT_RETRIES", "0")
    monkeypatch.setenv("REDIS_CONNECT_INITIAL_DELAY", "0")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))
    sys.modules.pop("app", None)
    import app as backend

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
