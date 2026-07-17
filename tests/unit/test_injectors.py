"""Self-check for generalized param_map injection (extra_params).

Run: python worker/test_injectors.py
Covers: ReTake backward compat (sentinel values), Ideogram4 named-param
injection with native types, missing-key preservation, and workflow
template files staying byte-identical on disk.
"""

import hashlib
import sys
from pathlib import Path

WORKER_SRC = Path(__file__).resolve().parents[2] / "worker" / "src"
sys.path.insert(0, str(WORKER_SRC.parent.parent))
sys.path.insert(0, str(WORKER_SRC))

from json_parser import parse_workflow  # noqa: E402
from workflow.node_utils import set_node_input_value  # noqa: E402

PROJECT_ROOT = WORKER_SRC.parent.parent
WORKFLOW_DIR = PROJECT_ROOT / "ComfyUIworkflow"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_retake_sentinel_extra_params():
    workflow = parse_workflow(
        workflow_name="ltx_retake_v2v",
        prompt="test prompt",
        seed=42,
        extra_params={"retake_start": 1.0, "retake_end": 3.5},
    )
    assert workflow["661"]["inputs"]["value"] == 1.0
    assert workflow["662"]["inputs"]["value"] == 3.5
    assert isinstance(workflow["661"]["inputs"]["value"], float)
    assert workflow["115"]["inputs"]["noise_seed"] == 42
    assert workflow["243"]["inputs"]["noise_seed"] == 42
    print("[OK] ReTake sentinel injection via extra_params")


def test_retake_backward_compat_top_level_kwargs():
    workflow = parse_workflow(
        workflow_name="ltx_retake_v2v",
        prompt="test prompt",
        seed=1,
        retake_start=2.0,
        retake_end=5.0,
    )
    assert workflow["661"]["inputs"]["value"] == 2.0
    assert workflow["662"]["inputs"]["value"] == 5.0
    print("[OK] ReTake backward-compat top-level retake_start/retake_end")


def test_extra_params_takes_priority_over_top_level():
    workflow = parse_workflow(
        workflow_name="ltx_retake_v2v",
        prompt="test prompt",
        seed=1,
        retake_start=1.0,
        retake_end=2.0,
        extra_params={"retake_start": 9.0, "retake_end": 9.5},
    )
    assert workflow["661"]["inputs"]["value"] == 9.0
    assert workflow["662"]["inputs"]["value"] == 9.5
    print("[OK] extra_params overrides legacy top-level retake_start/retake_end")


def test_ideogram4_named_param_injection_native_types():
    elements_data = '[{"x":0.1,"y":0.2,"w":0.3,"h":0.4,"type":"obj","text":"","desc":"a box","palette":["#ffffff"]}]'
    workflow = parse_workflow(
        workflow_name="ideogram4_regional_t2i",
        prompt="main description",
        seed=777,
        extra_params={
            "elements_data": elements_data,
            "width": 512,
            "height": 768,
            "background": "a plain background",
        },
    )
    inputs = workflow["178"]["inputs"]
    assert inputs["high_level_description"] == "main description"
    assert inputs["elements_data"] == elements_data
    assert inputs["width"] == 512 and isinstance(inputs["width"], int)
    assert inputs["height"] == 768 and isinstance(inputs["height"], int)
    assert inputs["background"] == "a plain background"
    assert workflow["98:18"]["inputs"]["noise_seed"] == 777
    print("[OK] Ideogram4 param_map injection preserves native types")


def test_ideogram4_missing_key_preserves_template_value():
    workflow = parse_workflow(
        workflow_name="ideogram4_regional_t2i",
        prompt="main description",
        seed=1,
        extra_params={"width": 1080},
    )
    inputs = workflow["178"]["inputs"]
    # background/aesthetics/lighting/elements_data not supplied -> template default ("") kept
    assert inputs["background"] == ""
    assert inputs["aesthetics"] == ""
    assert inputs["elements_data"] == "[]"
    assert inputs["width"] == 1080
    print("[OK] missing extra_params keys preserve template default values")


def test_param_map_missing_node_does_not_crash():
    workflow = {"178": {"inputs": {"foo": "bar"}, "class_type": "X"}}
    ok = set_node_input_value(workflow, "does-not-exist", "value", 1.0, "test")
    assert ok is False
    print("[OK] set_node_input_value on missing node returns False, no crash")


def test_workflow_template_files_untouched_on_disk():
    ltx_path = WORKFLOW_DIR / "LTX2.3_ReTake_V2V.json"
    ideogram_path = WORKFLOW_DIR / "Ideogram4_T2I_Regional_Prompt.json"
    before = {p: file_hash(p) for p in (ltx_path, ideogram_path)}

    parse_workflow(workflow_name="ltx_retake_v2v", prompt="x", seed=1, extra_params={"retake_start": 1.0, "retake_end": 2.0})
    parse_workflow(workflow_name="ideogram4_regional_t2i", prompt="x", seed=1, extra_params={"elements_data": "[]"})

    after = {p: file_hash(p) for p in (ltx_path, ideogram_path)}
    assert before == after
    print("[OK] workflow template JSON files unchanged on disk after parse_workflow()")


if __name__ == "__main__":
    test_retake_sentinel_extra_params()
    test_retake_backward_compat_top_level_kwargs()
    test_extra_params_takes_priority_over_top_level()
    test_ideogram4_named_param_injection_native_types()
    test_ideogram4_missing_key_preserves_template_value()
    test_param_map_missing_node_does_not_crash()
    test_workflow_template_files_untouched_on_disk()
    print("\nAll injector tests passed.")
