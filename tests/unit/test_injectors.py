"""Self-check for generalized param_map injection (extra_params).

Run: python worker/test_injectors.py
Covers: ReTake backward compat (sentinel values), Ideogram4 named-param
injection with native types, missing-key preservation, and workflow
template files staying byte-identical on disk.
"""

import hashlib
import json
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


def test_multi_angle_param_map_preserves_native_types():
    workflow = parse_workflow(
        workflow_name="multi_angle",
        prompt="",
        seed=7,
        image_files={"input": "fixture.png"},
        extra_params={"horizontal_angle": 90, "vertical_angle": 30, "zoom": 7.5},
    )
    inputs = workflow["3"]["inputs"]
    assert inputs["horizontal_angle"] == 90 and isinstance(inputs["horizontal_angle"], int)
    assert inputs["vertical_angle"] == 30 and isinstance(inputs["vertical_angle"], int)
    assert inputs["zoom"] == 7.5 and isinstance(inputs["zoom"], float)
    assert workflow["1"]["inputs"]["image"] == "fixture.png"
    assert workflow["4:105"]["inputs"]["seed"] == 7
    print("[OK] Multi-angle param_map and KSampler seed injection")


def test_multi_angle_missing_zoom_preserves_template_value():
    workflow = parse_workflow(
        workflow_name="multi_angle",
        prompt="",
        seed=1,
        extra_params={"horizontal_angle": 180, "vertical_angle": 0},
    )
    assert workflow["3"]["inputs"]["zoom"] == 5
    print("[OK] Multi-angle missing zoom preserves template default")


def test_param_map_missing_node_does_not_crash():
    workflow = {"178": {"inputs": {"foo": "bar"}, "class_type": "X"}}
    ok = set_node_input_value(workflow, "does-not-exist", "value", 1.0, "test")
    assert ok is False
    print("[OK] set_node_input_value on missing node returns False, no crash")


def test_ltx_i2v_template_is_valid_and_image_path_is_enabled():
    template = json.loads((WORKFLOW_DIR / "LTX_2.3_I2V.json").read_text(encoding="utf-8"))
    assert "354" not in template
    assert all(node.get("class_type") for node in template.values())
    assert template["290"]["inputs"]["value"] is False
    print("[OK] LTX I2V template is a valid ComfyUI API payload")


def test_ltx_i2v_injection_and_defaults():
    workflow = parse_workflow(
        workflow_name="ltx_i2v",
        prompt="__PROMPT_OVERRIDE_TEST__",
        seed=12345,
        image_files={"input": "input.png"},
        extra_params={"video_width": 1280, "video_height": 704, "video_duration": 6},
    )
    assert workflow["352"]["inputs"]["value"] == "__PROMPT_OVERRIDE_TEST__"
    assert workflow["167"]["inputs"]["image"] == "input.png"
    assert [workflow[node]["inputs"]["value"] for node in ("292", "293", "291")] == [1280, 704, 6]
    assert all(isinstance(workflow[node]["inputs"]["value"], int) for node in ("292", "293", "291"))
    assert all(workflow[node]["inputs"]["noise_seed"] == 12345 for node in ("114", "115"))

    defaults = parse_workflow(workflow_name="ltx_i2v", prompt="x", seed=1, image_files={"input": "input.png"})
    assert [defaults[node]["inputs"]["value"] for node in ("292", "293", "291")] == [1280, 736, 10]
    print("[OK] LTX I2V injection preserves native values and template defaults")


def test_ltx_flf_injection_and_models_are_not_overridden():
    template = json.loads((WORKFLOW_DIR / "LTX2.3_FLF_api.json").read_text(encoding="utf-8"))
    workflow = parse_workflow(
        workflow_name="ltx_flf",
        prompt="__PROMPT_OVERRIDE_TEST__",
        seed=12345,
        model="turbo_fp8",
        image_files={"first_frame": "start.png", "last_frame": "end.png"},
        extra_params={"video_width": 1024, "video_height": 1024, "video_duration": 4},
    )
    assert workflow["2103"]["inputs"]["value"] == "__PROMPT_OVERRIDE_TEST__"
    assert workflow["45"]["inputs"]["image"] == "start.png"
    assert workflow["47"]["inputs"]["image"] == "end.png"
    assert [workflow[node]["inputs"]["value"] for node in ("2080", "2079", "2078")] == [1024, 1024, 4]
    assert all(workflow[node]["inputs"]["noise_seed"] == 12345 for node in ("14", "15"))
    assert workflow["187"]["inputs"]["unet_name"] == template["187"]["inputs"]["unet_name"]

    i2v = parse_workflow(workflow_name="ltx_i2v", prompt="x", seed=1, model="turbo_fp8", image_files={"input": "input.png"})
    i2v_template = json.loads((WORKFLOW_DIR / "LTX_2.3_I2V.json").read_text(encoding="utf-8"))
    assert i2v["329"]["inputs"]["unet_name"] == i2v_template["329"]["inputs"]["unet_name"]
    print("[OK] LTX FLF injection and protected LTX UNET models")


def test_retired_video_workflows_are_unavailable_and_image_to_video_remains():
    assert not (WORKFLOW_DIR / "T2V.json").exists()
    assert not (WORKFLOW_DIR / "FLF.json").exists()
    assert (WORKFLOW_DIR / "Veo3_VideoConnection.json").exists()
    for workflow_name in ("veo3_long_video", "t2v_veo3", "flf_veo3", "T2V", "FLF"):
        try:
            parse_workflow(workflow_name=workflow_name)
        except KeyError:
            pass
        else:
            raise AssertionError(f"retired workflow remained available: {workflow_name}")

    workflow = parse_workflow(workflow_name="image_to_video", image_files={"shot_0": "fixture.png"})
    assert workflow["6"]["inputs"]["image"] == "fixture.png"
    print("[OK] retired video workflows are unavailable; image_to_video remains")


def test_workflow_template_files_untouched_on_disk():
    ltx_path = WORKFLOW_DIR / "LTX2.3_ReTake_V2V.json"
    ideogram_path = WORKFLOW_DIR / "Ideogram4_T2I_Regional_Prompt.json"
    i2v_path = WORKFLOW_DIR / "LTX_2.3_I2V.json"
    flf_path = WORKFLOW_DIR / "LTX2.3_FLF_api.json"
    before = {p: file_hash(p) for p in (ltx_path, ideogram_path, i2v_path, flf_path)}

    parse_workflow(workflow_name="ltx_retake_v2v", prompt="x", seed=1, extra_params={"retake_start": 1.0, "retake_end": 2.0})
    parse_workflow(workflow_name="ideogram4_regional_t2i", prompt="x", seed=1, extra_params={"elements_data": "[]"})
    parse_workflow(workflow_name="ltx_i2v", prompt="x", seed=1, image_files={"input": "input.png"})
    parse_workflow(workflow_name="ltx_flf", prompt="x", seed=1, image_files={"first_frame": "start.png", "last_frame": "end.png"})

    after = {p: file_hash(p) for p in (ltx_path, ideogram_path, i2v_path, flf_path)}
    assert before == after
    print("[OK] workflow template JSON files unchanged on disk after parse_workflow()")


if __name__ == "__main__":
    test_retake_sentinel_extra_params()
    test_retake_backward_compat_top_level_kwargs()
    test_extra_params_takes_priority_over_top_level()
    test_ideogram4_named_param_injection_native_types()
    test_ideogram4_missing_key_preserves_template_value()
    test_multi_angle_param_map_preserves_native_types()
    test_multi_angle_missing_zoom_preserves_template_value()
    test_param_map_missing_node_does_not_crash()
    test_ltx_i2v_template_is_valid_and_image_path_is_enabled()
    test_ltx_i2v_injection_and_defaults()
    test_ltx_flf_injection_and_models_are_not_overridden()
    test_retired_video_workflows_are_unavailable_and_image_to_video_remains()
    test_workflow_template_files_untouched_on_disk()
    print("\nAll injector tests passed.")
