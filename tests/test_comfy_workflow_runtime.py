import importlib.util
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = PROJECT_ROOT / "worker" / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("STUDIO_ENV_FILE", ".env.twcc")

from shared.utils import load_env


def load_worker_module(monkeypatch, module_filename: str, module_alias: str):
    monkeypatch.setenv("STUDIO_ENV_FILE", ".env.twcc")
    load_env(PROJECT_ROOT)
    monkeypatch.setenv("DB_PASSWORD", os.getenv("DB_PASSWORD", "test-password"))

    previous_config_module = sys.modules.get("config")
    previous_websocket_module = sys.modules.get("websocket")
    previous_sys_path = list(sys.path)

    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        sys.path.insert(0, str(WORKER_SRC))
        if "websocket" not in sys.modules:
            class FakeWebSocketModule:
                class WebSocketTimeoutException(Exception):
                    pass

                @staticmethod
                def create_connection(*args, **kwargs):
                    raise RuntimeError("websocket test stub should not be used in this test")

            sys.modules["websocket"] = FakeWebSocketModule()

        config_spec = importlib.util.spec_from_file_location(
            "worker_runtime_test_config",
            WORKER_SRC / "config.py",
        )
        config_module = importlib.util.module_from_spec(config_spec)
        sys.modules[config_spec.name] = config_module
        sys.modules["config"] = config_module
        assert config_spec.loader is not None
        config_spec.loader.exec_module(config_module)

        module_spec = importlib.util.spec_from_file_location(
            module_alias,
            WORKER_SRC / module_filename,
        )
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_spec.name] = module
        assert module_spec.loader is not None
        module_spec.loader.exec_module(module)
        return module
    finally:
        if previous_config_module is not None:
            sys.modules["config"] = previous_config_module
        else:
            sys.modules.pop("config", None)
        if previous_websocket_module is not None:
            sys.modules["websocket"] = previous_websocket_module
        else:
            sys.modules.pop("websocket", None)
        sys.path[:] = previous_sys_path


def test_json_parser_uses_api_fallback_directory(monkeypatch):
    json_parser = load_worker_module(monkeypatch, "json_parser.py", "worker_runtime_test_json_parser")

    assert json_parser.API_WORKFLOW_FALLBACK_DIR.name == "ComfyUIworkflow_api"


def test_normalize_comfy_paths_rewrites_known_windows_model_paths(monkeypatch):
    module_path = WORKER_SRC / "comfy_paths.py"
    assert module_path.exists(), "worker/src/comfy_paths.py should exist"

    module_spec = importlib.util.spec_from_file_location("worker_runtime_test_comfy_paths", module_path)
    comfy_paths = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(comfy_paths)

    payload = {
        "prompt": {
            "504:404": {
                "inputs": {
                    "unet_name": "Qwen\\Qwen-Image-Edit-2509-Q4_K_M.gguf",
                    "clip_name": "Qwen\\qwen_2.5_vl_7b_fp8_scaled.safetensors",
                    "vae_name": "Qwen\\qwen_image_vae.safetensors",
                    "lora_name": "Qwen_Edit\\Lightning\\Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
                    "bfs_name": "Qwen_Edit\\bfs_head_v3_qwen_image_edit_2509.safetensors",
                    "wan_name": "wan2.1\\umt5-xxl-enc-bf16.safetensors",
                    "talk_model": "InfiniTetalk\\Wan2_1-InfiniTetalk-Single_fp16.safetensors",
                }
            }
        }
    }

    normalized = comfy_paths.normalize_comfy_paths(payload)
    inputs = normalized["prompt"]["504:404"]["inputs"]

    assert inputs["unet_name"] == "Qwen_Image_Edit/Qwen-Image-Edit-2509-Q4_K_M.gguf"
    assert inputs["clip_name"] == "Qwen_Image_Edit/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
    assert inputs["vae_name"] == "Qwen_Image_Edit/split_files/vae/qwen_image_vae.safetensors"
    assert inputs["lora_name"] == "Qwen_Edit/Lightning/Qwen-Image-Lightning-4steps-V1.0.safetensors"
    assert inputs["bfs_name"] == "bfs_head_v3_qwen_image_edit_2509.safetensors"
    assert inputs["wan_name"] == "Wan2.1/umt5-xxl-enc-bf16.safetensors"
    assert inputs["talk_model"] == "InfiniteTalk/Wan2_1-InfiniTetalk-Single_fp16.safetensors"


def test_queue_prompt_normalizes_payload_before_submit(monkeypatch):
    comfy_client = load_worker_module(monkeypatch, "comfy_client.py", "worker_runtime_test_comfy_client")
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"prompt_id": "prompt-123"}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["payload"] = json
        return FakeResponse()

    monkeypatch.setattr(comfy_client.requests, "post", fake_post)

    client = comfy_client.ComfyClient()
    prompt = {
        "504:404": {
            "inputs": {
                "unet_name": "Qwen\\Qwen-Image-Edit-2509-Q4_K_M.gguf",
                "vae_name": "Qwen\\qwen_image_vae.safetensors",
            }
        }
    }

    prompt_id = client.queue_prompt(prompt)

    assert prompt_id == "prompt-123"
    assert captured["payload"]["prompt"]["504:404"]["inputs"]["unet_name"] == (
        "Qwen_Image_Edit/Qwen-Image-Edit-2509-Q4_K_M.gguf"
    )
    assert captured["payload"]["prompt"]["504:404"]["inputs"]["vae_name"] == (
        "Qwen_Image_Edit/split_files/vae/qwen_image_vae.safetensors"
    )


def test_copy_output_file_downloads_missing_gpu_output_via_view(monkeypatch, tmp_path):
    comfy_client = load_worker_module(monkeypatch, "comfy_client.py", "worker_runtime_test_comfy_client_view")
    monkeypatch.setattr(comfy_client, "COMFY_OUTPUT_DIR", tmp_path / "comfy-output")
    monkeypatch.setattr(comfy_client, "STORAGE_OUTPUT_DIR", tmp_path / "storage-outputs")
    comfy_client.STORAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"gpu-bytes"

        @staticmethod
        def iter_content(chunk_size=8192):
            yield b"gpu-bytes"

    def fake_get(url, params=None, timeout=None, stream=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        captured["stream"] = stream
        return FakeResponse()

    monkeypatch.setattr(comfy_client.requests, "get", fake_get)

    client = comfy_client.ComfyClient()
    result = client.copy_output_file(
        filename="result.png",
        subfolder="集成應用1222",
        file_type="output",
        job_id="job-1",
    )

    assert result == "job-1.png"
    assert captured["url"].endswith("/view")
    assert captured["params"] == {
        "filename": "result.png",
        "subfolder": "集成應用1222",
        "type": "output",
    }
    assert (tmp_path / "storage-outputs" / "集成應用1222" / "result.png").read_bytes() == b"gpu-bytes"
    assert (tmp_path / "storage-outputs" / "job-1.png").read_bytes() == b"gpu-bytes"


def test_process_task_tries_next_output_when_first_download_fails(monkeypatch):
    comfy_client = load_worker_module(monkeypatch, "comfy_client.py", "worker_runtime_test_comfy_client_outputs")

    client = comfy_client.ComfyClient()
    monkeypatch.setattr(client, "check_connection", lambda: True)
    monkeypatch.setattr(client, "queue_prompt", lambda workflow: "prompt-1")
    monkeypatch.setattr(
        client,
        "wait_for_completion",
        lambda prompt_id: {
            "success": True,
            "videos": [],
            "gifs": [],
            "images": [
                {"filename": "missing.png", "subfolder": "集成應用1222", "type": "output"},
                {"filename": "good.png", "subfolder": "", "type": "output"},
            ],
        },
    )

    seen = []

    def fake_copy_output_file(filename, subfolder="", file_type="output", job_id=None):
        seen.append((filename, subfolder, file_type, job_id))
        if filename == "missing.png":
            return None
        return "job-2.png"

    monkeypatch.setattr(client, "copy_output_file", fake_copy_output_file)

    result = client.process_task({"1": {"inputs": {}}}, job_id="job-2")

    assert result["success"] is True
    assert result["image_url"] == "/outputs/job-2.png"
    assert seen == [
        ("missing.png", "集成應用1222", "output", "job-2"),
        ("good.png", "", "output", "job-2"),
    ]


def test_main_shutdown_path_does_not_raise_unboundlocal(monkeypatch):
    main_module = load_worker_module(monkeypatch, "main.py", "worker_runtime_test_main")

    class FakeRedis:
        def ping(self):
            return True

        def blpop(self, *args, **kwargs):
            return None

    class FakeComfyClient:
        def check_connection(self):
            return False

    class FakeWarmupController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            return None

        def mark_unavailable(self):
            return None

        def request_priority_handoff(self):
            return None

    monkeypatch.setattr(main_module, "get_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(main_module, "ComfyClient", FakeComfyClient)
    monkeypatch.setattr(main_module, "WarmupController", FakeWarmupController)
    monkeypatch.setattr(main_module, "cleanup_old_temp_files", lambda: None)
    monkeypatch.setattr(main_module, "cleanup_old_output_files", lambda db_client=None: None)

    main_module._shutdown_flag = True
    main_module._current_job_id = None

    try:
        main_module.main()
    except UnboundLocalError as exc:  # pragma: no cover - explicit regression guard
        pytest.fail(f"main() should not raise UnboundLocalError during shutdown: {exc}")
