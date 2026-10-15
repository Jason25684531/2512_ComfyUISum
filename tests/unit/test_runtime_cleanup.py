"""Compatibility checks for configuration ownership and fresh workflow payloads."""
import json
import runpy
from pathlib import Path

import pytest

from shared import config_base


ROOT = Path(__file__).resolve().parents[2]


def test_worker_config_preserves_endpoint_paths_and_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(config_base, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_base, "COMFYUI_ROOT", tmp_path / "comfy")
    monkeypatch.setattr(config_base, "STORAGE_DIR", tmp_path / "storage")
    settings = ("COMFYUI_SERVER_URL", "COMFY_HOST", "COMFY_PORT", "COMFYUI_INPUT_DIR",
                "COMFYUI_OUTPUT_DIR", "STORAGE_MODELS_DIR")
    for name in settings:
        monkeypatch.delenv(name, raising=False)

    def load():
        return runpy.run_path(str(ROOT / "worker/src/config.py"))

    defaults = load()
    assert defaults["COMFY_HTTP_URL"] == defaults["COMFYUI_SERVER_URL"] == "http://127.0.0.1:8188"
    assert defaults["COMFY_WS_URL"] == "ws://127.0.0.1:8188/ws"
    assert defaults["COMFYUI_INPUT_DIR"] == tmp_path / "comfy/input"
    assert defaults["COMFYUI_OUTPUT_DIR"] == tmp_path / "comfy/output"
    assert defaults["STORAGE_MODELS_DIR"] == tmp_path / "storage/models"

    for name, value in zip(settings, ("https://engine.example:8443/base/", "ignored", "9999",
                                      "relative/input", "relative/output", "relative/models")):
        monkeypatch.setenv(name, value)
    explicit = load()
    assert explicit["COMFY_HOST"] == "engine.example"
    assert explicit["COMFY_PORT"] == 8443
    assert explicit["COMFY_HTTP_URL"] == "https://engine.example:8443/base"
    assert explicit["COMFY_WS_URL"] == "wss://engine.example:8443/base/ws"
    for name, suffix in (("COMFYUI_INPUT_DIR", "input"), ("COMFYUI_OUTPUT_DIR", "output"),
                         ("STORAGE_MODELS_DIR", "models")):
        assert explicit[name] == tmp_path / "relative" / suffix
    assert explicit["COMFYUI_INPUT_DIR"].is_dir()
    assert explicit["STORAGE_MODELS_DIR"].is_dir()
    assert not explicit["COMFYUI_OUTPUT_DIR"].exists()

    monkeypatch.delenv("COMFYUI_SERVER_URL")
    host_only = load()
    assert host_only["COMFY_HTTP_URL"] == "http://ignored:9999"
    monkeypatch.setenv("COMFYUI_SERVER_URL", "http://")
    with pytest.raises(ValueError):
        load()


def test_parsed_workflows_are_isolated_and_aliases_preserved(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "worker/src"))
    from workflow import runtime

    catalog = runtime.load_workflow_catalog()
    monkeypatch.setattr(runtime, "load_workflow_catalog", lambda: catalog)
    metadata_before = json.dumps(catalog.raw_config, sort_keys=True)
    template = catalog.resolve("single_image_edit").entry.path
    bytes_before = template.read_bytes()
    options = dict(prompt="isolation", seed=7, image_files={"input": "input.png"})
    first = runtime.parse_workflow("single_image_edit", **options)
    expected = json.dumps(first, sort_keys=True)
    first["120"]["inputs"]["image"] = "mutated.png"
    second = runtime.parse_workflow("image_edit", **options)
    assert json.dumps(second, sort_keys=True) == expected
    assert second["120"]["inputs"]["image"] == "input.png"
    assert json.dumps(catalog.raw_config, sort_keys=True) == metadata_before
    assert template.read_bytes() == bytes_before
    assert catalog.resolve("single_image_edit").alias_hit
    assert not catalog.resolve("image_edit").alias_hit
    with pytest.raises(KeyError):
        runtime.parse_workflow("unknown-cleanup-workflow")
