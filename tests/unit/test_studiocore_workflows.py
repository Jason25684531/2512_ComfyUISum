"""StudioCore contracts, using the catalog and real API assets without executing remote jobs."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared.workflow_catalog import WorkflowCatalog

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "worker" / "src"))
from job_service import _normalize_catalog_inputs
from workflow import runtime


@pytest.fixture
def catalog():
    return WorkflowCatalog.from_paths(ROOT / "ComfyUIworkflow/config.json", ROOT / "ComfyUIworkflow")


@pytest.fixture
def candidate_runtime(monkeypatch, catalog):
    raw = copy.deepcopy(catalog.raw_config)
    for name in ("image_gpt25_sunburst", "video_minimax_h3"):
        raw[name]["enabled"] = True
    candidate = WorkflowCatalog(catalog.config_path, catalog.workflow_dir, raw)
    monkeypatch.setattr(runtime, "load_workflow_catalog", lambda: candidate)
    monkeypatch.setattr(runtime, "load_workflow", lambda name: json.loads(
        (ROOT / "ComfyUIworkflow_api" / candidate.entries[name].file).read_text(encoding="utf-8")
    ))
    for setting in ("STUDIOCORE_AZURE_API_KEY", "STUDIOCORE_AZURE_ENDPOINT"):
        monkeypatch.setattr(runtime, setting, "private-test-setting")
    return candidate


@pytest.mark.parametrize("count", [0, 1, 3])
def test_sunburst_reference_modes(catalog, candidate_runtime, capsys, count):
    entry = catalog.entries["image_gpt25_sunburst"]
    extra, images, error = _normalize_catalog_inputs(entry, {
        "images": [f"reference-{index}.png" for index in range(count)],
        "extra_params": {"size": "1536x1024", "background": "transparent", "api_key": "browser-key"},
    }, "a blue bird")
    assert error is None
    assert len(images) == count
    asset = ROOT / "ComfyUIworkflow_api" / entry.file
    before = asset.read_bytes()
    workflow = runtime.parse_workflow("image_gpt25_sunburst", prompt="a blue bird", image_files=images, extra_params=extra)
    assert workflow["37"]["inputs"]["String"] == "a blue bird"
    for index, node in enumerate(("31", "35", "36")):
        assert workflow[node]["inputs"]["image"] == (f"reference-{index}.png" if index < count else "(none)")
    assert workflow["34"]["inputs"]["size"] == "1536x1024"
    assert workflow["34"]["inputs"]["background"] == "transparent"
    assert workflow["34"]["inputs"]["api_key"] == "private-test-setting"
    assert "private-test-setting" not in capsys.readouterr().out
    assert "api_key" not in extra
    assert asset.read_bytes() == before


@pytest.mark.parametrize("data", [
    {"images": ["image.png"] * 4},
    {"images": [{"api_key": "browser-key"}]},
    {"extra_params": {"size": "1x1"}},
    {"extra_params": {"background": "invalid"}},
])
def test_sunburst_invalid_inputs(catalog, data):
    assert _normalize_catalog_inputs(catalog.entries["image_gpt25_sunburst"], data, "bird")[2]


@pytest.mark.parametrize("mode,frames", [
    ("t2v", {}), ("i2v", {"first_frame": "first.png"}),
    ("fl2v", {"first_frame": "first.png", "last_frame": "last.png"}),
    ("l2v", {"last_frame": "last.png"}),
])
def test_minimax_modes(candidate_runtime, mode, frames, capsys):
    workflow = runtime.parse_workflow("video_minimax_h3", prompt="a calm sea", seed=112,
        image_files=frames, video_mode=mode, extra_params={"width": 1344, "height": 768, "duration": 5})
    assert workflow["143"]["inputs"]["String"] == "a calm sea"
    assert workflow["105:15"]["inputs"]["noise_seed"] == 112
    assert workflow["105:111"]["inputs"]["value"] == 5
    for name, node in (("first_frame", "136"), ("last_frame", "135")):
        assert workflow[node]["inputs"]["image"] == frames.get(name, "(none)")
        assert (name in workflow["105:104"]["inputs"]) == (name in frames)
    assert workflow["127"]["inputs"]["format"] == "video/h264-mp4"
    assert workflow["127"]["inputs"]["save_metadata"] is False
    assert "minimax_h3" in workflow["105:6"]["inputs"]["unet_name"]
    assert "private-test-setting" not in capsys.readouterr().out


def test_missing_runtime_credential_fails_without_logging(candidate_runtime, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "STUDIOCORE_AZURE_API_KEY", "")
    with pytest.raises(ValueError, match="not configured"):
        runtime.parse_workflow("image_gpt25_sunburst", prompt="bird")
    assert "private-test-setting" not in capsys.readouterr().out


def test_source_graphs_are_intact_and_credential_widgets_are_empty(catalog):
    for name, count in (("image_gpt25_sunburst", 15), ("video_minimax_h3", 12)):
        source = json.loads(catalog.entries[name].path.read_text(encoding="utf-8"))
        assert len(source["nodes"]) == count
        assert all(node.get("type") for node in source["nodes"])
        nonempty = 0
        for node in source["nodes"]:
            names = [field["name"] for field in node.get("inputs", []) if field.get("widget")]
            nonempty += sum(bool(value) for field, value in zip(names, node.get("widgets_values", [])) if field in {"api_key", "endpoint_url"})
        assert nonempty == 0, "Credential widget remains populated"


def test_credential_submission_requires_disabled_metadata(monkeypatch, capsys):
    import comfy_client
    client = comfy_client.ComfyClient()
    monkeypatch.setattr(comfy_client.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"system": {"argv": []}}))
    def must_not_submit(*args, **kwargs):
        pytest.fail("Unsafe credential prompt reached ComfyUI")
    monkeypatch.setattr(comfy_client.requests, "post", must_not_submit)
    assert client.queue_prompt({"1": {"inputs": {"api_key": "private-test-setting"}}}) is None
    logged = capsys.readouterr().out
    assert "--disable-metadata" in logged
    assert "private-test-setting" not in logged


@pytest.mark.parametrize("node,kind,filename", [
    ("18", "images", "sunburst.png"), ("9", "images", "upscale.png"),
    ("127", "gifs", "minimax.mp4"),
])
def test_existing_history_resolver_handles_studiocore_outputs(monkeypatch, node, kind, filename):
    import comfy_client
    item = {"filename": filename, "subfolder": "StudioCore", "type": "output"}
    monkeypatch.setattr(comfy_client.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        status_code=200, json=lambda: {"prompt": {"outputs": {node: {kind: [item]}}}}))
    outputs = comfy_client.ComfyClient().get_outputs_from_history("prompt")
    assert outputs[kind] == [item]


def test_credential_submission_with_disabled_metadata(monkeypatch, capsys):
    import comfy_client
    monkeypatch.setattr(comfy_client.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"system": {"argv": ["--disable-metadata"]}}))
    monkeypatch.setattr(comfy_client.requests, "post", lambda *args, **kwargs: SimpleNamespace(
        status_code=200, json=lambda: {"prompt_id": "accepted-prompt"}))
    assert comfy_client.ComfyClient().queue_prompt({"1": {"inputs": {"api_key": "private-test-setting"}}}) == "accepted-prompt"
    assert "private-test-setting" not in capsys.readouterr().out


def test_canonical_card_titles_preserve_utf8(catalog):
    expected = {
        "image_gpt25_sunburst": "圖像生成",
        "image_upscale_seedvr2": "圖像放大",
        "video_minimax_h3": "影像生成",
    }
    assert {name: catalog.entries[name].frontend.title for name in expected} == expected


def test_disabled_candidate_cannot_resolve_or_be_published(catalog):
    raw = copy.deepcopy(catalog.raw_config)
    raw["image_gpt25_sunburst"]["enabled"] = False
    candidate = WorkflowCatalog(catalog.config_path, catalog.workflow_dir, raw)
    with pytest.raises(KeyError):
        candidate.resolve("image_gpt25_sunburst")
    assert "image_gpt25_sunburst" not in {entry["id"] for entry in candidate.frontend_catalog()}


@pytest.mark.parametrize("ui_fallback", [False, True])
def test_ui_source_without_valid_api_asset_is_rejected(monkeypatch, tmp_path, ui_fallback):
    from workflow import loader
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"nodes": []}), encoding="utf-8")
    api_dir = tmp_path / "ComfyUIworkflow_api"
    api_dir.mkdir()
    if ui_fallback:
        (api_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(loader, "get_workflow_path", lambda _: source)
    monkeypatch.setattr(loader, "API_WORKFLOW_FALLBACK_DIRS", (api_dir,))
    with pytest.raises(ValueError, match="UI format"):
        loader.load_workflow("test-workflow")


def test_execution_error_does_not_expose_credentials(monkeypatch, capsys):
    import comfy_client
    client = comfy_client.ComfyClient()
    monkeypatch.setattr(client, "get_outputs_from_history", lambda _: {"images": [], "videos": [], "gifs": []})
    message = json.dumps({"type": "execution_error", "data": {
        "prompt_id": "test-prompt", "node": "34", "node_type": "Sunburst",
        "exception_message": "private-test-setting https://private-endpoint.test",
        "current_inputs": {"api_key": "private-test-setting"},
    }})
    monkeypatch.setattr(comfy_client.websocket, "create_connection", lambda *a, **k: SimpleNamespace(
        settimeout=lambda _: None, recv=lambda: message, close=lambda: None))
    events = []
    result = client.wait_for_completion("test-prompt", on_event=lambda name, data: events.append((name, data)))
    assert result["success"] is False
    assert events[0][1]["node"] == "34"
    safe = json.dumps({"result": result, "events": events}) + capsys.readouterr().out
    assert "private-test-setting" not in safe
    assert "private-endpoint" not in safe
    assert "current_inputs" not in safe


def test_submission_exception_does_not_expose_credentials(monkeypatch, capsys):
    import comfy_client
    def fail(*args, **kwargs):
        raise ValueError("private-test-setting https://private-endpoint.test")
    monkeypatch.setattr(comfy_client.requests, "post", fail)
    assert comfy_client.ComfyClient().queue_prompt({"1": {"inputs": {}}}) is None
    logged = capsys.readouterr().out
    assert "private-test-setting" not in logged
    assert "private-endpoint" not in logged


def test_render_timeout_returns_existing_failure_result(monkeypatch):
    import comfy_client
    client = comfy_client.ComfyClient()
    monkeypatch.setattr(client, "get_outputs_from_history", lambda _: {"images": [], "videos": [], "gifs": []})
    monkeypatch.setattr(comfy_client.websocket, "create_connection", lambda *a, **k: SimpleNamespace(
        settimeout=lambda _: None, close=lambda: None))
    clock = iter((0.0, 2.0))
    monkeypatch.setattr(comfy_client.time, "time", lambda: next(clock))
    result = client.wait_for_completion("test-prompt", timeout=1)
    assert result["success"] is False and result["timeout"] is True
    assert result["images"] == result["videos"] == result["gifs"] == []


def test_unresponsive_comfyui_returns_safe_failure(monkeypatch, capsys):
    import comfy_client
    client = comfy_client.ComfyClient()
    monkeypatch.setattr(client, "get_outputs_from_history", lambda _: {"images": [], "videos": [], "gifs": []})
    def fail(*args, **kwargs):
        raise ConnectionError("private-test-setting https://private-endpoint.test")
    monkeypatch.setattr(comfy_client.websocket, "create_connection", fail)
    monkeypatch.setattr(comfy_client.time, "sleep", lambda _: None)
    result = client.wait_for_completion("test-prompt", timeout=1)
    assert result["success"] is False and result["error"]
    safe = json.dumps(result) + capsys.readouterr().out
    assert "private-test-setting" not in safe and "private-endpoint" not in safe


def test_minimax_resolution_choices_are_multiples_of_32(catalog):
    # MiniMax patchifies the first-frame latent (1/16 scale) in pairs; 1080 fails I2V.
    choices = catalog.resolve("video_minimax_h3").entry.choices
    assert all(value % 32 == 0 for value in choices["width"] + choices["height"])
