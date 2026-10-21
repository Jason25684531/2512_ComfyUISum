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


def test_three_job_status_polls_do_not_hit_rate_limit(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.local")
    monkeypatch.setenv("REDIS_CONNECT_RETRIES", "0")
    backend = load_backend(monkeypatch)
    monkeypatch.setattr(backend, "redis_client", None)
    monkeypatch.setattr(backend, "JOB_OBSERVABILITY_ENABLED", False)
    runtime = backend.app.extensions["backend_runtime"]
    monkeypatch.setattr(runtime, "repository_provider", lambda: SimpleNamespace(get_job=lambda _: None))
    client = backend.app.test_client()
    assert [client.get(f"/api/status/missing-{index % 3}").status_code for index in range(6)] == [404] * 6


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


def test_seedvr2_enqueue_validates_image_and_scale(monkeypatch):
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
    runtime_response = client.get("/api/runtime-config")
    assert runtime_response.status_code == 200
    runtime_json = json.dumps(runtime_response.json).lower()
    assert "studiocore_azure_api_key" not in runtime_json
    assert "studiocore_azure_endpoint" not in runtime_json
    image = "data:image/png;base64,aGVsbG8="

    for scale in ("2", "4"):
        response = client.post("/api/generate", json={
            "workflow": "image_upscale_seedvr2",
            "images": {"image": image},
            "extra_params": {"scale": scale},
        })
        assert response.status_code == 200

    jobs = [json.loads(payload) for payload in fake_redis.queue]
    assert [job["extra_params"]["scale"] for job in jobs] == [2, 4]
    assert all(job["workflow"] == "image_upscale_seedvr2" for job in jobs)
    assert all("studiocore_azure" not in json.dumps(job).lower() for job in jobs)
    assert all("api_key" not in json.dumps(job).lower() for job in jobs)

    missing_image = client.post("/api/generate", json={
        "workflow": "image_upscale_seedvr2", "images": {}, "extra_params": {"scale": 2},
    })
    unsupported_scale = client.post("/api/generate", json={
        "workflow": "image_upscale_seedvr2",
        "images": {"image": image},
        "extra_params": {"scale": 3},
    })
    assert missing_image.status_code == 400
    assert unsupported_scale.status_code == 400
    assert len(fake_redis.queue) == 2


def test_studiocore_enqueue_contracts(monkeypatch):
    import copy
    import json
    from pathlib import Path
    from shared import runtime_services
    from shared.workflow_catalog import WorkflowCatalog

    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.local")
    monkeypatch.setenv("REDIS_CONNECT_RETRIES", "0")
    backend = load_backend(monkeypatch)
    root = Path(__file__).resolve().parents[2]
    catalog = WorkflowCatalog.from_paths(root / "ComfyUIworkflow/config.json", root / "ComfyUIworkflow")
    raw = copy.deepcopy(catalog.raw_config)
    for name in ("image_gpt25_sunburst", "video_minimax_h3"):
        raw[name]["enabled"] = True
    candidate = WorkflowCatalog(catalog.config_path, catalog.workflow_dir, raw)
    monkeypatch.setattr(runtime_services, "_get_catalog", lambda project_root: candidate)

    class FakeRedis(list):
        def __bool__(self):
            return False
        def rpush(self, key, payload):
            self.append(payload)
        def hset(self, *args, **kwargs):
            pass
        def expire(self, *args, **kwargs):
            pass

    queue = FakeRedis()
    monkeypatch.setattr(backend, "redis_client", queue)
    monkeypatch.setattr(backend, "JOB_OBSERVABILITY_ENABLED", False)
    monkeypatch.setattr(backend.app.extensions["limiter"], "enabled", False)
    client = backend.app.test_client()
    monkeypatch.setattr(WorkflowCatalog, "from_paths", classmethod(lambda cls, *args: candidate))
    public = client.get("/api/runtime-config").json
    assert {"image_gpt25_sunburst", "image_upscale_seedvr2", "video_minimax_h3"} <= {entry["id"] for entry in public["workflow_catalog"]}
    assert "api_key" not in json.dumps(public).lower()
    assert "endpoint" not in json.dumps(public).lower()
    image = "data:image/png;base64,aGVsbG8="
    for count in (0, 1, 3):
        response = client.post("/api/generate", json={
            "workflow": "image_gpt25_sunburst", "prompt": "a blue bird", "images": [image] * count,
            "api_key": "browser-must-not-be-forwarded",
            "extra_params": {"background": "transparent", "api_key": "browser-must-not-be-forwarded", "endpoint_url": "browser-must-not-be-forwarded"},
        })
        assert response.status_code == 200
        job = json.loads(queue[-1])
        assert set(job["images"]) == {f"images.{i}" for i in range(count)}
        assert job["extra_params"]["background"] == "transparent"
        assert "browser-must-not-be-forwarded" not in json.dumps(job)
    assert client.post("/api/generate", json={
        "workflow": "image_gpt25_sunburst", "prompt": "bird", "images": [image] * 4,
    }).status_code == 400
    assert client.post("/api/generate", json={"workflow": "image_gpt25_sunburst"}).status_code == 400

    cases = [("t2v", {}), ("i2v", {"first_frame": image}), ("fl2v", {"first_frame": image, "last_frame": image})]
    for mode, frames in cases:
        response = client.post("/api/generate", json={
            "workflow": "video_minimax_h3", "prompt": "a calm sea", "images": frames, "seed": 112,
        })
        assert response.status_code == 200
        job = json.loads(queue[-1])
        assert job["video_mode"] == mode
        assert job["seed"] == 112
        assert job["extra_params"]["duration"] == 5
    for dimensions in ({"width": 608, "height": 352}, {"width": 1024, "height": 576}, {"width": 1920, "height": 1088}):
        response = client.post("/api/generate", json={
            "workflow": "video_minimax_h3", "prompt": "sea", "extra_params": dimensions,
        })
        assert response.status_code == 200
        assert all(json.loads(queue[-1])["extra_params"][key] == value for key, value in dimensions.items())
    queued = len(queue)
    for dimensions in ({"width": 1920, "height": 1080}, {"width": 607, "height": 352}):
        response = client.post("/api/generate", json={
            "workflow": "video_minimax_h3", "prompt": "sea", "extra_params": dimensions,
        })
        assert response.status_code == 400 and "32" in response.json["error"]
        assert len(queue) == queued
    last_only = client.post("/api/generate", json={
        "workflow": "video_minimax_h3", "prompt": "sea", "images": {"last_frame": image},
    })
    assert last_only.status_code == (200 if "l2v" in candidate.entries["video_minimax_h3"].video_mode_map else 400)
    if "l2v" in candidate.entries["video_minimax_h3"].video_mode_map:
        assert json.loads(queue[-1])["video_mode"] == "l2v"
        candidate.entries["video_minimax_h3"].video_mode_map.pop("l2v")
        assert client.post("/api/generate", json={
            "workflow": "video_minimax_h3", "prompt": "sea", "images": {"last_frame": image},
        }).status_code == 400

    monkeypatch.setattr(backend, "redis_client", None)
    unavailable = client.post("/api/generate", json={
        "workflow": "image_gpt25_sunburst", "prompt": "bird", "images": [],
    })
    assert unavailable.status_code == 503
    assert "job_id" not in unavailable.json


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
    catalog_validated = {entry.workflow_id for entry in catalog.entries.values() if entry.input_types}
    assert parameterized <= catalog_validated | {
        "ltx_retake_v2v",
        "multi_angle",
        "ideogram4_regional_t2i",
        "ltx_i2v",
        "ltx_flf",
        "image_upscale_seedvr2",
    }
