import importlib.util
import logging
import os
import sys
from pathlib import Path

from shared.utils import load_env


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = PROJECT_ROOT / "worker" / "src"


class FakeRedis:
    def __init__(self, queue_length=0, fail_hset=False):
        self.queue_length = queue_length
        self.fail_hset = fail_hset
        self.hashes = {}
        self.expirations = {}

    def hset(self, key, mapping):
        if self.fail_hset:
            raise RuntimeError("redis unavailable")
        self.hashes[key] = dict(mapping)

    def expire(self, key, ttl):
        self.expirations[key] = ttl

    def llen(self, key):
        return self.queue_length


class FakeComfyClient:
    def __init__(self, result=None):
        self.result = result or {
            "success": True,
            "images": [],
            "videos": [],
            "gifs": [],
            "error": None,
            "aborted": False,
            "abort_reason": None,
        }
        self.queued_prompts = []
        self.interrupt_calls = 0

    def queue_prompt(self, workflow):
        self.queued_prompts.append(workflow)
        return f"prompt-{len(self.queued_prompts)}"

    def wait_for_completion(self, prompt_id, timeout=None, should_abort=None, on_abort=None, **kwargs):
        if should_abort:
            abort_reason = should_abort()
            if abort_reason:
                if on_abort:
                    on_abort()
                return {
                    "success": False,
                    "images": [],
                    "videos": [],
                    "gifs": [],
                    "error": "執行已中止",
                    "aborted": True,
                    "abort_reason": abort_reason,
                }
        return dict(self.result)

    def interrupt(self):
        self.interrupt_calls += 1
        return True


def load_worker_modules(monkeypatch):
    load_env(PROJECT_ROOT)
    monkeypatch.setenv("DB_PASSWORD", os.getenv("DB_PASSWORD", "test-password"))

    previous_config_module = sys.modules.get("config")
    previous_sys_path = list(sys.path)
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        sys.path.insert(0, str(WORKER_SRC))

        config_spec = importlib.util.spec_from_file_location("worker_test_config", WORKER_SRC / "config.py")
        config_module = importlib.util.module_from_spec(config_spec)
        sys.modules[config_spec.name] = config_module
        sys.modules["config"] = config_module
        assert config_spec.loader is not None
        config_spec.loader.exec_module(config_module)

        warmup_spec = importlib.util.spec_from_file_location("worker_test_warmup", WORKER_SRC / "warmup.py")
        warmup_module = importlib.util.module_from_spec(warmup_spec)
        sys.modules[warmup_spec.name] = warmup_module
        assert warmup_spec.loader is not None
        warmup_spec.loader.exec_module(warmup_module)
        return config_module, warmup_module
    finally:
        if previous_config_module is not None:
            sys.modules["config"] = previous_config_module
        else:
            sys.modules.pop("config", None)
        sys.path[:] = previous_sys_path


def test_skip_warmup_env_forces_off_mode(monkeypatch):
    monkeypatch.setenv("SKIP_WARMUP", "true")
    monkeypatch.setenv("WARMUP_MODE", "managed")

    worker_config, _ = load_worker_modules(monkeypatch)

    assert worker_config.WARMUP_MODE == "off"


def test_managed_warmup_defers_when_queue_has_pending_jobs(monkeypatch):
    _, warmup_module = load_worker_modules(monkeypatch)
    fake_redis = FakeRedis(queue_length=2)
    fake_client = FakeComfyClient()

    controller = warmup_module.WarmupController(
        redis_client=fake_redis,
        comfy_client=fake_client,
        logger=logging.getLogger("warmup-test"),
        queue_name="job_queue",
        mode="managed",
        profiles=[warmup_module.WarmupProfile(name="default-image", timeout_seconds=30)],
    )

    controller._run_warmup(managed_mode=True)

    assert controller.get_status()["status"] == "deferred"
    assert fake_client.queued_prompts == []


def test_managed_warmup_cleans_outputs_and_reaches_ready(monkeypatch, tmp_path):
    _, warmup_module = load_worker_modules(monkeypatch)
    output_file = tmp_path / "_warmup_default-image_00001_.png"
    output_file.write_bytes(b"warmup")

    monkeypatch.setattr(warmup_module, "COMFYUI_OUTPUT_DIR", tmp_path)

    fake_redis = FakeRedis(queue_length=0)
    fake_client = FakeComfyClient(
        result={
            "success": True,
            "images": [{"filename": output_file.name, "subfolder": "", "type": "output"}],
            "videos": [],
            "gifs": [],
            "error": None,
            "aborted": False,
            "abort_reason": None,
        }
    )

    controller = warmup_module.WarmupController(
        redis_client=fake_redis,
        comfy_client=fake_client,
        logger=logging.getLogger("warmup-test"),
        queue_name="job_queue",
        mode="managed",
        profiles=[warmup_module.WarmupProfile(name="default-image", timeout_seconds=30)],
    )

    controller._run_warmup(managed_mode=True)

    assert controller.get_status()["status"] == "ready"
    assert not output_file.exists()
    assert len(fake_client.queued_prompts) == 1


def test_managed_warmup_timeout_marks_failed(monkeypatch):
    _, warmup_module = load_worker_modules(monkeypatch)
    fake_redis = FakeRedis(queue_length=0)
    fake_client = FakeComfyClient(
        result={
            "success": False,
            "images": [],
            "videos": [],
            "gifs": [],
            "error": "execution timeout",
            "aborted": False,
            "abort_reason": None,
        }
    )

    controller = warmup_module.WarmupController(
        redis_client=fake_redis,
        comfy_client=fake_client,
        logger=logging.getLogger("warmup-test"),
        queue_name="job_queue",
        mode="managed",
        profiles=[warmup_module.WarmupProfile(name="default-image", timeout_seconds=15)],
    )

    controller._run_warmup(managed_mode=True)

    assert controller.get_status()["status"] == "failed"
    assert controller.get_status()["last_error"] == "Warmup timeout"


def test_warmup_status_publish_failure_falls_back_to_local_state(monkeypatch):
    _, warmup_module = load_worker_modules(monkeypatch)
    fake_redis = FakeRedis(queue_length=0, fail_hset=True)
    fake_client = FakeComfyClient()

    controller = warmup_module.WarmupController(
        redis_client=fake_redis,
        comfy_client=fake_client,
        logger=logging.getLogger("warmup-test"),
        queue_name="job_queue",
        mode="managed",
        profiles=[warmup_module.WarmupProfile(name="default-image", timeout_seconds=15)],
    )

    controller._run_warmup(managed_mode=True)

    assert controller.get_status()["status"] == "ready"
    assert len(fake_client.queued_prompts) == 1