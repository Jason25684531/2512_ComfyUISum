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
    assert len(workflow_raw) == 12
    assert len(catalog.entries) == 12
    assert catalog.validate() == []

    aliases = {alias for entry in catalog.entries.values() for alias in entry.aliases}
    for workflow_id, config in workflow_raw.items():
        resolution = catalog.resolve(workflow_id)
        assert resolution.entry.path == WORKFLOW_DIR / config["file"]
        assert resolution.entry.path.is_file()
        assert isinstance(resolution.entry.to_public_dict(), dict)

    assert catalog.resolve("single_image_edit").workflow_id == "image_edit"
    assert "_runtime" not in {entry["id"] for entry in catalog.frontend_catalog()}
    assert aliases == {alias for entry in catalog.frontend_catalog() for alias in entry["aliases"]}


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
