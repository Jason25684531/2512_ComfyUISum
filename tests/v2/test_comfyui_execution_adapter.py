from __future__ import annotations

import json
from pathlib import Path

import httpx


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


def _response(method: str, url: str, *, status_code: int = 200, json_data=None, content: bytes = b"") -> httpx.Response:
    kwargs = {"request": httpx.Request(method, url)}
    if json_data is not None:
        kwargs["json"] = json_data
    else:
        kwargs["content"] = content
    return httpx.Response(status_code, **kwargs)


def _build_engine(settings):
    from worker.engines.comfyui_engine import ComfyUIEngine

    comfy_settings = settings.model_copy(
        update={
            "engine_mode": "comfyui",
            "comfy_history_timeout_seconds": 1.0,
            "comfy_polling_interval_seconds": 0.0,
            "comfy_http_timeout_seconds": 5.0,
            "comfy_submit_timeout_seconds": 5.0,
        }
    )
    return ComfyUIEngine(settings=comfy_settings)


def test_comfyui_execute_writes_relative_output_and_injects_bindings(settings, monkeypatch):
    from app.models.job import JobPayload

    engine = _build_engine(settings)
    captured_prompt = {}

    def fake_post(url: str, *, json=None, timeout=None):
        captured_prompt["payload"] = json["prompt"]
        return _response("POST", url, json_data={"prompt_id": "prompt-1"})

    def fake_get(url: str, *, timeout=None, params=None):
        if url.endswith("/history/prompt-1"):
            return _response(
                "GET",
                url,
                json_data={
                    "prompt-1": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "result_real.png",
                                        "subfolder": "studio_v2",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        if url.endswith("/view"):
            assert params == {"filename": "result_real.png", "subfolder": "studio_v2", "type": "output"}
            return _response("GET", url, content=PNG_BYTES)
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setattr("httpx.get", fake_get)

    job = JobPayload(
        task_type="text_to_image",
        params={
            "prompt": "a calm lake at sunrise",
            "negative_prompt": "blurry",
            "width": 768,
            "height": 1344,
            "seed": 42,
            "steps": 12,
            "batch_size": 2,
            "model": "z-image/z-image-turbo-fp8-e4m3fn.safetensors",
        },
    )

    result = engine.execute(job)

    assert result.success is True
    assert result.output_path == f"outputs/job_{job.job_id}/result.png"
    assert "\\" not in result.output_path
    written = Path(settings.storage_root) / result.output_path
    assert written.read_bytes() == PNG_BYTES

    prompt = captured_prompt["payload"]
    assert prompt["3"]["inputs"]["text"] == "a calm lake at sunrise"
    assert prompt["4"]["inputs"]["text"] == "blurry"
    assert prompt["5"]["inputs"]["width"] == 768
    assert prompt["5"]["inputs"]["height"] == 1344
    assert prompt["5"]["inputs"]["batch_size"] == 2
    assert prompt["6"]["inputs"]["seed"] == 42
    assert prompt["6"]["inputs"]["steps"] == 12
    assert prompt["1"]["inputs"]["unet_name"] == "z-image\\z-image-turbo-fp8-e4m3fn.safetensors"
    assert prompt["2"]["inputs"]["clip_name"] == "z-image\\qwen_3_4b.safetensors"
    assert prompt["7"]["inputs"]["vae_name"] == "z-image\\ae.safetensors"


def test_comfyui_execute_returns_workflow_missing_when_contract_files_absent(settings, monkeypatch, tmp_path):
    from app.models.job import JobPayload
    from shared.v2.errors import WORKFLOW_NOT_FOUND

    engine = _build_engine(settings)
    engine.workflow_dir = tmp_path

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "missing"}))

    assert result.success is False
    assert result.error_message == WORKFLOW_NOT_FOUND


def test_comfyui_execute_returns_binding_error_for_invalid_binding(settings, tmp_path):
    from app.models.job import JobPayload
    from shared.v2.errors import WORKFLOW_BINDING_INVALID

    workflow_dir = tmp_path / "comfyui"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "text_to_image.basic.json").write_text(
        json.dumps({"1": {"inputs": {"text": "hello"}, "class_type": "CLIPTextEncode"}}),
        encoding="utf-8",
    )
    (workflow_dir / "text_to_image.basic.bindings.json").write_text(
        json.dumps({"prompt_binding": {"node_id": "999", "input_key": "text"}}),
        encoding="utf-8",
    )

    engine = _build_engine(settings)
    engine.workflow_dir = workflow_dir

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "binding"}))

    assert result.success is False
    assert result.error_message == WORKFLOW_BINDING_INVALID


def test_comfyui_execute_returns_timeout_when_history_never_finishes(settings, monkeypatch):
    from app.models.job import JobPayload

    engine = _build_engine(settings)
    timeline = iter([0.0, 0.0, 2.0])

    monkeypatch.setattr("worker.engines.comfyui_engine.time.monotonic", lambda: next(timeline))
    monkeypatch.setattr("worker.engines.comfyui_engine.time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("httpx.post", lambda url, **kwargs: _response("POST", url, json_data={"prompt_id": "prompt-1"}))
    monkeypatch.setattr("httpx.get", lambda url, **kwargs: _response("GET", url, json_data={}))

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "timeout"}))

    assert result.success is False
    assert result.error_message == "ComfyUI history polling timed out."


def test_comfyui_execute_fails_when_submit_has_no_prompt_id(settings, monkeypatch):
    from app.models.job import JobPayload

    engine = _build_engine(settings)
    monkeypatch.setattr("httpx.post", lambda url, **kwargs: _response("POST", url, json_data={"ok": True}))

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "missing prompt id"}))

    assert result.success is False
    assert result.error_message == "ComfyUI model validation failed. The selected model is not compatible with text_to_image."


def test_comfyui_execute_returns_output_missing_when_history_has_no_images(settings, monkeypatch):
    from app.models.job import JobPayload

    engine = _build_engine(settings)
    monkeypatch.setattr("httpx.post", lambda url, **kwargs: _response("POST", url, json_data={"prompt_id": "prompt-1"}))
    monkeypatch.setattr(
        "httpx.get",
        lambda url, **kwargs: _response(
            "GET",
            url,
            json_data={"prompt-1": {"outputs": {"9": {"videos": [], "gifs": []}}}},
        ),
    )

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "missing image"}))

    assert result.success is False
    assert result.error_message == "ComfyUI completed but no image output was found."


def test_comfyui_execute_fails_when_view_returns_non_image_payload(settings, monkeypatch):
    from app.models.job import JobPayload

    engine = _build_engine(settings)
    monkeypatch.setattr("httpx.post", lambda url, **kwargs: _response("POST", url, json_data={"prompt_id": "prompt-1"}))

    def fake_get(url: str, **kwargs):
        if url.endswith("/history/prompt-1"):
            return _response(
                "GET",
                url,
                json_data={
                    "prompt-1": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "result.txt",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        return _response("GET", url, content=b"not an image")

    monkeypatch.setattr("httpx.get", fake_get)

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "bad download"}))

    assert result.success is False
    assert result.error_message == "ComfyUI output download failed."


def test_comfyui_execute_normalizes_negative_seed_for_comfyui(settings, monkeypatch):
    from app.models.job import JobPayload

    engine = _build_engine(settings)
    captured_prompt = {}

    def fake_post(url: str, *, json=None, timeout=None):
        captured_prompt["payload"] = json["prompt"]
        return _response("POST", url, json_data={"prompt_id": "prompt-1"})

    monkeypatch.setattr(
        "httpx.get",
        lambda url, **kwargs: _response(
            "GET",
            url,
            json_data={
                "prompt-1": {
                    "outputs": {
                        "9": {
                            "images": [
                                {"filename": "result.png", "subfolder": "studio_v2", "type": "output"}
                            ]
                        }
                    }
                }
            },
        )
        if url.endswith("/history/prompt-1")
        else _response("GET", url, content=PNG_BYTES),
    )
    monkeypatch.setattr("httpx.post", fake_post)

    result = engine.execute(JobPayload(task_type="text_to_image", params={"prompt": "seed test", "seed": -1}))

    assert result.success is True
    assert isinstance(captured_prompt["payload"]["6"]["inputs"]["seed"], int)
    assert captured_prompt["payload"]["6"]["inputs"]["seed"] >= 0
