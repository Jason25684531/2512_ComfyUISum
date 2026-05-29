import importlib.util
import json
import logging
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = PROJECT_ROOT / "worker" / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_PREVIOUS_STUDIO_ENV_FILE = os.environ.get("STUDIO_ENV_FILE")
os.environ.setdefault("STUDIO_ENV_FILE", ".env.twcc")
from shared.utils import load_env
from shared.utils import JSONFormatter, JobLogAdapter


MULTI_BLEND_DEFAULT_PROMPT = "圖1的女生拖著圖2的行李箱，站在圖3的地鐵站入口，逼真的光影"
MULTI_BLEND_DEFAULT_PROMPT_PREFIX = "圖1的女生拖著圖2的行李箱"
PROMPT_SENTINEL = "__PROMPT_OVERRIDE_TEST__"
WINDOWS_TEXT_TO_IMAGE_MODELS = {
    ("33:18", "clip_name"): "z-image\\qwen_3_4b.safetensors",
    ("33:16", "unet_name"): "z-image\\z-image-turbo-fp8-e4m3fn.safetensors",
    ("33:17", "vae_name"): "z-image\\ae.safetensors",
}


def teardown_module():
    if _PREVIOUS_STUDIO_ENV_FILE is None:
        os.environ.pop("STUDIO_ENV_FILE", None)
    else:
        os.environ["STUDIO_ENV_FILE"] = _PREVIOUS_STUDIO_ENV_FILE


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


def _prompt_value_for_node(workflow, node_id):
    node = workflow.get(node_id)
    assert node is not None, f"missing workflow node {node_id}"

    inputs = node.get("inputs")
    if isinstance(inputs, dict) and "prompt" in inputs:
        return inputs["prompt"]

    widgets_values = node.get("widgets_values")
    if isinstance(widgets_values, list) and widgets_values:
        return widgets_values[0]
    if isinstance(widgets_values, dict):
        for key in ("prompt", "text", "string"):
            if key in widgets_values:
                return widgets_values[key]

    pytest.fail(f"node {node_id} does not expose a prompt value")


def _input_value_for_node(workflow, node_id, input_key):
    node = workflow.get(node_id)
    assert node is not None, f"missing workflow node {node_id}"

    inputs = node.get("inputs")
    assert isinstance(inputs, dict), f"node {node_id} does not expose dict inputs"
    assert input_key in inputs, f"node {node_id} missing input {input_key}"
    return inputs[input_key]


def test_parse_workflow_text_to_image_applies_windows_model_overrides(monkeypatch):
    monkeypatch.setenv("COMFYUI_RUNTIME_PROFILE", "windows")
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_windows_model_overrides",
    )

    workflow = json_parser.parse_workflow(
        "text_to_image",
        prompt="test prompt",
        seed=123,
    )

    for (node_id, input_key), expected_value in WINDOWS_TEXT_TO_IMAGE_MODELS.items():
        assert _input_value_for_node(workflow, node_id, input_key) == expected_value


def test_parse_workflow_text_to_image_linux_profile_does_not_apply_windows_overrides(monkeypatch):
    monkeypatch.setenv("COMFYUI_RUNTIME_PROFILE", "linux")
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_linux_model_overrides",
    )
    source_workflow = json_parser.load_workflow("text_to_image")

    workflow = json_parser.parse_workflow(
        "text_to_image",
        prompt="test prompt",
        seed=123,
    )

    for node_id, input_key in WINDOWS_TEXT_TO_IMAGE_MODELS:
        assert _input_value_for_node(workflow, node_id, input_key) == _input_value_for_node(
            source_workflow,
            node_id,
            input_key,
        )


def test_parse_workflow_text_to_image_unknown_profile_is_noop_for_model_overrides(monkeypatch):
    monkeypatch.setenv("COMFYUI_RUNTIME_PROFILE", "unknown-profile")
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_unknown_model_overrides",
    )
    source_workflow = json_parser.load_workflow("text_to_image")

    workflow = json_parser.parse_workflow(
        "text_to_image",
        prompt="test prompt",
        seed=123,
    )

    for node_id, input_key in WINDOWS_TEXT_TO_IMAGE_MODELS:
        assert _input_value_for_node(workflow, node_id, input_key) == _input_value_for_node(
            source_workflow,
            node_id,
            input_key,
        )


def test_parse_workflow_text_to_image_model_overrides_do_not_modify_workflow_json(monkeypatch):
    monkeypatch.setenv("COMFYUI_RUNTIME_PROFILE", "windows")
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_model_override_immutability",
    )
    workflow_path = json_parser.get_workflow_path("text_to_image")
    fallback_path = json_parser.API_WORKFLOW_FALLBACK_DIR / workflow_path.name
    before_workflow = workflow_path.read_bytes()
    before_fallback = fallback_path.read_bytes()

    json_parser.parse_workflow(
        "text_to_image",
        prompt="test prompt",
        seed=123,
    )

    assert workflow_path.read_bytes() == before_workflow
    assert fallback_path.read_bytes() == before_fallback


def test_parse_workflow_multi_image_blend_uses_configured_prompt_map(monkeypatch):
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_prompt_map",
    )

    workflow = json_parser.parse_workflow(
        "multi_image_blend",
        prompt=PROMPT_SENTINEL,
        seed=123,
    )

    target_prompt = _prompt_value_for_node(workflow, "433:111")
    assert target_prompt == PROMPT_SENTINEL
    assert target_prompt != MULTI_BLEND_DEFAULT_PROMPT


def test_parse_workflow_multi_image_blend_overrides_api_fallback_prompt_payload(monkeypatch):
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_api_prompt_map",
    )

    workflow = json_parser.parse_workflow(
        "multi_image_blend",
        prompt=PROMPT_SENTINEL,
        seed=123,
    )

    assert workflow["433:111"]["inputs"]["prompt"] == PROMPT_SENTINEL
    assert workflow["433:110"]["inputs"]["prompt"] == ""
    assert MULTI_BLEND_DEFAULT_PROMPT_PREFIX not in workflow["433:111"]["inputs"]["prompt"]


def test_parse_workflow_multi_image_blend_keeps_configured_image_map(monkeypatch):
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_multi_blend_image_map",
    )

    workflow = json_parser.parse_workflow(
        "multi_image_blend",
        prompt=PROMPT_SENTINEL,
        seed=123,
        image_files={
            "source": "source-test.png",
            "target": "target-test.png",
            "extra": "extra-test.png",
        },
    )

    assert workflow["78"]["inputs"]["image"] == "source-test.png"
    assert workflow["436"]["inputs"]["image"] == "target-test.png"
    assert workflow["437"]["inputs"]["image"] == "extra-test.png"


def test_set_configured_prompt_value_supports_ui_widgets_values(monkeypatch):
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_ui_prompt_widget",
    )
    workflow = {
        "nodes": [
            {
                "id": "433:111",
                "type": "TextEncodeQwenImageEditPlus",
                "inputs": [],
                "widgets_values": [MULTI_BLEND_DEFAULT_PROMPT],
            }
        ]
    }

    assert json_parser.set_configured_prompt_value(
        workflow,
        "433:111",
        "prompt",
        PROMPT_SENTINEL,
    )
    assert workflow["nodes"][0]["widgets_values"][0] == PROMPT_SENTINEL


def test_workflow_registry_resolves_aliases_and_validates_declared_maps(monkeypatch):
    workflow_registry = load_worker_module(
        monkeypatch,
        "workflow_registry.py",
        "worker_runtime_test_workflow_registry",
    )

    registry = workflow_registry.WorkflowRegistry()
    entry = registry.get("multi_image_blend")
    legacy_entry = registry.get("multi_blend")

    assert entry.name == "multi_image_blend"
    assert legacy_entry.name == "multi_image_blend"
    assert entry.file == "multi_image_blend_qwen_2509_gguf_1222.json"
    assert entry.prompt_map["main"] == {
        "node_id": "433:111",
        "input_key": "prompt",
    }
    assert registry.validate_configured_workflows() == []


def test_parse_workflow_multi_image_blend_logs_prompt_map_api_injection(monkeypatch, capsys):
    json_parser = load_worker_module(
        monkeypatch,
        "json_parser.py",
        "worker_runtime_test_json_parser_prompt_map_log",
    )

    json_parser.parse_workflow(
        "multi_image_blend",
        prompt=PROMPT_SENTINEL,
        seed=123,
    )

    captured = capsys.readouterr().out
    assert "prompt_map API 注入: Node 433:111.prompt" in captured
    assert "Qwen Prompt 注入: Node 433:110.prompt" not in captured


def test_job_log_adapter_and_formatter_include_workflow_and_user_context():
    logger = logging.getLogger("test-job-context")
    adapter = JobLogAdapter(
        logger,
        {
            "job_id": "job-123",
            "workflow": "multi_image_blend",
            "user_label": "anonymous",
        },
    )

    _message, kwargs = adapter.process("processing", {})

    assert kwargs["extra"]["job_id"] == "job-123"
    assert kwargs["extra"]["workflow"] == "multi_image_blend"
    assert kwargs["extra"]["user_label"] == "anonymous"

    record = logging.LogRecord(
        name="worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="processing",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-123"
    record.workflow = "multi_image_blend"
    record.user_label = "anonymous"

    payload = json.loads(JSONFormatter().format(record))

    assert payload["job_id"] == "job-123"
    assert payload["workflow"] == "multi_image_blend"
    assert payload["user_label"] == "anonymous"


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


def test_queue_prompt_uses_submit_timeout(monkeypatch):
    comfy_client = load_worker_module(monkeypatch, "comfy_client.py", "worker_runtime_test_comfy_client_submit_timeout")
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"prompt_id": "prompt-123"}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(comfy_client, "COMFY_SUBMIT_TIMEOUT_SECONDS", 12, raising=False)
    monkeypatch.setattr(comfy_client.requests, "post", fake_post)

    prompt_id = comfy_client.ComfyClient().queue_prompt({"1": {"inputs": {}}})

    assert prompt_id == "prompt-123"
    assert captured["timeout"] == 12


def test_history_api_uses_history_timeout(monkeypatch):
    comfy_client = load_worker_module(monkeypatch, "comfy_client.py", "worker_runtime_test_comfy_client_history_timeout")
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"prompt-123": {"outputs": {}}}

    def fake_get(url, timeout=None, **kwargs):
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(comfy_client, "COMFY_HISTORY_TIMEOUT_SECONDS", 7, raising=False)
    monkeypatch.setattr(comfy_client.requests, "get", fake_get)

    result = comfy_client.ComfyClient().get_outputs_from_history("prompt-123")

    assert result == {"images": [], "videos": [], "gifs": []}
    assert captured["timeout"] == 7


def test_copy_output_file_retries_until_local_output_appears(monkeypatch, tmp_path):
    comfy_client = load_worker_module(monkeypatch, "comfy_client.py", "worker_runtime_test_comfy_client_copy_retry")
    comfy_output_dir = tmp_path / "comfy-output"
    storage_output_dir = tmp_path / "storage-outputs"
    comfy_output_dir.mkdir()
    storage_output_dir.mkdir()
    source_file = comfy_output_dir / "late.png"

    monkeypatch.setattr(comfy_client, "COMFY_OUTPUT_DIR", comfy_output_dir)
    monkeypatch.setattr(comfy_client, "STORAGE_OUTPUT_DIR", storage_output_dir)
    monkeypatch.setattr(comfy_client, "OUTPUT_COPY_RETRY_COUNT", 2, raising=False)
    monkeypatch.setattr(comfy_client, "OUTPUT_COPY_RETRY_DELAY_SECONDS", 0, raising=False)
    monkeypatch.setattr(comfy_client, "OUTPUT_COPY_WAIT_SECONDS", 0, raising=False)

    def fake_sleep(seconds):
        if not source_file.exists():
            source_file.write_bytes(b"late-output")

    client = comfy_client.ComfyClient()
    monkeypatch.setattr(comfy_client.time, "sleep", fake_sleep)
    monkeypatch.setattr(client, "download_output_via_view", lambda *args, **kwargs: None)

    result = client.copy_output_file("late.png", job_id="job-late")

    assert result == "job-late.png"
    assert (storage_output_dir / "job-late.png").read_bytes() == b"late-output"


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


def test_process_job_persists_recovered_local_output(monkeypatch, tmp_path):
    main_module = load_worker_module(monkeypatch, "main.py", "worker_runtime_test_main_outputs")
    output_dir = tmp_path / "worker-outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main_module, "COMFYUI_OUTPUT_DIR", output_dir, raising=False)
    monkeypatch.setattr(main_module, "parse_workflow", lambda **kwargs: {"1": {"inputs": {}}})

    class FakeRedis:
        def __init__(self):
            self.hashes = {}
            self.expirations = {}

        def hset(self, key, mapping):
            self.hashes[key] = dict(mapping)

        def expire(self, key, ttl):
            self.expirations[key] = ttl

        def hget(self, key, field):
            return self.hashes.get(key, {}).get(field)

    class FakeDbClient:
        def __init__(self):
            self.calls = []

        def update_job_status(self, job_id, status, output_path=None):
            self.calls.append(
                {
                    "job_id": job_id,
                    "status": status,
                    "output_path": output_path,
                }
            )
            return True

    class FakeClient:
        def check_connection(self):
            return True

        def queue_prompt(self, workflow):
            return "prompt-123"

        def wait_for_completion(self, prompt_id, timeout=None, on_progress=None):
            if on_progress:
                on_progress(50)
            return {
                "success": True,
                "videos": [],
                "gifs": [],
                "images": [
                    {"filename": "gpu.png", "subfolder": "", "type": "output"},
                ],
            }

        def copy_output_file(self, filename, subfolder="", file_type="output", job_id=None):
            dest = output_dir / f"{job_id}.png"
            dest.write_bytes(b"png-bytes")
            return dest.name

    redis_client = FakeRedis()
    db_client = FakeDbClient()
    job_id = "job-local"

    main_module.process_job(
        redis_client,
        FakeClient(),
        {
            "job_id": job_id,
            "workflow": "text_to_image",
            "prompt": "test prompt",
        },
        db_client=db_client,
    )

    status_key = f"job:status:{job_id}"
    assert redis_client.hashes[status_key]["status"] == "finished"
    assert redis_client.hashes[status_key]["image_url"] == f"/outputs/{job_id}.png"
    assert db_client.calls[-1] == {
        "job_id": job_id,
        "status": "finished",
        "output_path": f"{job_id}.png",
    }


def test_process_job_fails_when_local_output_file_is_missing(monkeypatch, tmp_path):
    main_module = load_worker_module(monkeypatch, "main.py", "worker_runtime_test_main_missing_output")
    output_dir = tmp_path / "worker-outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main_module, "COMFYUI_OUTPUT_DIR", output_dir, raising=False)
    monkeypatch.setattr(main_module, "parse_workflow", lambda **kwargs: {"1": {"inputs": {}}})

    class FakeRedis:
        def __init__(self):
            self.hashes = {}

        def hset(self, key, mapping):
            self.hashes[key] = dict(mapping)

        def expire(self, key, ttl):
            return None

        def hget(self, key, field):
            return self.hashes.get(key, {}).get(field)

    class FakeDbClient:
        def __init__(self):
            self.calls = []

        def update_job_status(self, job_id, status, output_path=None):
            self.calls.append(
                {
                    "job_id": job_id,
                    "status": status,
                    "output_path": output_path,
                }
            )
            return True

    class FakeClient:
        def check_connection(self):
            return True

        def queue_prompt(self, workflow):
            return "prompt-123"

        def wait_for_completion(self, prompt_id, timeout=None, on_progress=None):
            return {
                "success": True,
                "videos": [],
                "gifs": [],
                "images": [
                    {"filename": "gpu.png", "subfolder": "", "type": "output"},
                ],
            }

        def copy_output_file(self, filename, subfolder="", file_type="output", job_id=None):
            return f"{job_id}.png"

    redis_client = FakeRedis()
    db_client = FakeDbClient()
    job_id = "job-missing"

    main_module.process_job(
        redis_client,
        FakeClient(),
        {
            "job_id": job_id,
            "workflow": "text_to_image",
            "prompt": "test prompt",
        },
        db_client=db_client,
    )

    status_key = f"job:status:{job_id}"
    assert redis_client.hashes[status_key]["status"] == "failed"
    assert "image_url" not in redis_client.hashes[status_key]
    assert db_client.calls[-1] == {
        "job_id": job_id,
        "status": "failed",
        "output_path": None,
    }
