"""Change 2 coverage and parity contracts for the canonical workflow catalog."""

import json
from pathlib import Path

import pytest

from shared.workflow_catalog import WorkflowCatalog
ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / "ComfyUIworkflow"
CONFIG_PATH = WORKFLOW_DIR / "config.json"


@pytest.fixture(scope="module")
def catalog():
    return WorkflowCatalog.from_paths(CONFIG_PATH, WORKFLOW_DIR)


def test_all_config_entries_and_public_metadata_are_covered(catalog):
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    workflow_raw = {key: value for key, value in raw.items() if key != "_runtime"}
    assert len(workflow_raw) == 15
    assert len(catalog.entries) == 15
    assert catalog.validate() == []

    aliases = {alias for entry in catalog.entries.values() if entry.enabled for alias in entry.aliases}
    for workflow_id, config in workflow_raw.items():
        if not config.get("enabled", True):
            with pytest.raises(KeyError):
                catalog.resolve(workflow_id)
            assert workflow_id not in {entry["id"] for entry in catalog.frontend_catalog()}
            continue
        resolution = catalog.resolve(workflow_id)
        assert resolution.entry.path == WORKFLOW_DIR / config["file"]
        assert resolution.entry.path.is_file()
        assert isinstance(resolution.entry.to_public_dict(), dict)

    assert catalog.resolve("single_image_edit").workflow_id == "image_edit"
    assert "_runtime" not in {entry["id"] for entry in catalog.frontend_catalog()}
    assert aliases == {alias for entry in catalog.frontend_catalog() for alias in entry["aliases"]}


def test_seedvr2_catalog_contract(catalog):
    entry = catalog.resolve("image_upscale_seedvr2").entry
    public = entry.to_public_dict()
    api_workflow = json.loads(entry.path.parent.parent.joinpath("ComfyUIworkflow_api", entry.file).read_text(encoding="utf-8"))

    assert entry.category == "image"
    assert entry.required_inputs == ("image",)
    assert entry.optional_inputs == ("scale",)
    assert entry.image_map == {"image": "1"}
    assert entry.mapping["param_map"]["scale"] == {
        "node_id": "83",
        "input_key": "resize_type.multiplier",
    }
    assert entry.mapping["output_node_id"] == "9"
    assert entry.choices["scale"] == [2, 4]
    assert entry.defaults["scale"] == 2
    assert entry.units["scale"] == "x"
    assert public["output_type"] == "image"
    assert public["frontend"]["action_label"] == "放大"
    assert "api_key" not in json.dumps(public).lower()
    assert api_workflow["1"]["inputs"]["image"] == "__STUDIOCORE_IMAGE_INPUT__"


def test_studiocore_workflow_assets_have_no_embedded_credentials():
    import re

    paths = [
        *WORKFLOW_DIR.glob("StudioCore*.json"),
        *(WORKFLOW_DIR.parent / "ComfyUIworkflow_api").glob("StudioCore*.json"),
    ]
    credential_keys = re.compile(r"api[_-]?key|access[_-]?token|credential|authorization", re.I)
    embedded = []

    def inspect(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                location = f"{path}.{key}" if path else key
                if credential_keys.search(str(key)) and child not in (None, "", [], {}):
                    embedded.append(location)
                inspect(child, location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, f"{path}[{index}]")

    for path in paths:
        inspect(json.loads(path.read_text(encoding="utf-8")))
    assert embedded == []


def test_catalog_exposes_canonical_image_mappings(catalog):
    expected_image_maps = {
        "face_swap": {"source": "501", "target": "502"},
        "multi_image_blend": {"source": "78", "target": "436", "extra": "437"},
        "sketch_to_image": {"input": "120"},
        "image_edit": {"input": "120"},
        "text_to_image": {},
        "virtual_human": {"avatar": "284"},
        "image_to_video": {"shot_0": "6"},
    }
    for workflow_id, expected in expected_image_maps.items():
        assert catalog.resolve(workflow_id).entry.image_map == expected


def test_audio_map_has_the_same_virtual_human_semantics(catalog):
    entry = catalog.resolve("virtual_human").entry
    assert entry.audio_map["audio"] == {"node_id": "311", "input_key": "audio"}


def test_runtime_metadata_covers_model_and_aspect_ratio_maps(catalog):
    runtime_raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["_runtime"]
    runtime = catalog.runtime
    assert runtime.model_aliases == runtime_raw["model_aliases"]
    assert runtime.aspect_ratios == runtime_raw["aspect_ratios"]
    assert runtime.default_aspect_ratio == runtime_raw["default_aspect_ratio"]
    assert runtime.default_resolution == runtime_raw["default_resolution"]
    assert catalog.frontend_catalog()
    assert all("_runtime" not in entry for entry in catalog.frontend_catalog())


def test_runtime_metadata_rejects_missing_or_malformed_values():
    valid_entry = {
        "id": "test",
        "file": "test.json",
        "frontend": {},
    }
    missing = {"test": valid_entry}
    with pytest.raises(ValueError, match="_runtime"):
        WorkflowCatalog(CONFIG_PATH, WORKFLOW_DIR, missing)

    malformed = {
        "_runtime": {
            "model_aliases": {"turbo_fp8": ""},
            "aspect_ratios": {"1:1": {"width": 0, "height": 1024}},
            "default_aspect_ratio": "1:1",
        },
        "test": valid_entry,
    }
    with pytest.raises(ValueError, match="model_aliases|aspect_ratios"):
        WorkflowCatalog(CONFIG_PATH, WORKFLOW_DIR, malformed)


def test_catalog_source_contains_no_secret_or_manual_runtime_config():
    source = CONFIG_PATH.read_text(encoding="utf-8")
    assert not any(secret in source for secret in ("DB_PASSWORD", "REDIS_PASSWORD", "SECRET_KEY", "TWCC_API_KEY"))
    assert "_runtime" in json.loads(source)
