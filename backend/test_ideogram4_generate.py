"""
[TEMP] 测试脚本：验证 /api/generate 对 ideogram4_regional_t2i 的信任邊界驗證
运行方式: python backend/test_ideogram4_generate.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))
from shared.utils import load_env
load_env()

from src.app import app  # noqa: E402

client = app.test_client()

VALID_ELEMENTS = json.dumps([
    {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "type": "obj", "text": "", "desc": "a box", "palette": ["#ffffff"]}
])


def post(payload):
    return client.post("/api/generate", json=payload)


def test_missing_prompt_rejected():
    resp = post({"workflow": "ideogram4_regional_t2i", "elements_data": VALID_ELEMENTS})
    assert resp.status_code == 400, resp.status_code
    assert "error" in resp.get_json()
    print("[OK] missing prompt -> 400")


def test_malformed_elements_data_rejected_no_reflection():
    resp = post({"workflow": "ideogram4_regional_t2i", "prompt": "a cat", "elements_data": "not json"})
    assert resp.status_code == 400, resp.status_code
    body = resp.get_json()
    assert "error" in body
    assert "not json" not in json.dumps(body)
    print("[OK] malformed elements_data -> 400, input not reflected")


def test_oversized_elements_data_rejected():
    many = json.dumps([
        {"x": 0, "y": 0, "w": 0, "h": 0, "type": "obj", "text": "", "desc": "", "palette": []}
    ] * 51)
    resp = post({"workflow": "ideogram4_regional_t2i", "prompt": "a cat", "elements_data": many})
    assert resp.status_code == 400, resp.status_code
    print("[OK] elements_data over max count -> 400")


def test_missing_elements_data_defaults_to_empty_array():
    resp = post({"workflow": "ideogram4_regional_t2i", "prompt": "a cat"})
    assert resp.status_code != 400, resp.get_json()
    print("[OK] missing elements_data does not fail validation (defaults to [])")


def test_width_height_out_of_range_rejected():
    resp = post({
        "workflow": "ideogram4_regional_t2i", "prompt": "a cat",
        "elements_data": VALID_ELEMENTS, "width": 10, "height": 10,
    })
    assert resp.status_code == 400, resp.status_code
    print("[OK] width/height out of [256, 4096] -> 400")


def test_style_field_too_long_rejected():
    resp = post({
        "workflow": "ideogram4_regional_t2i", "prompt": "a cat",
        "elements_data": VALID_ELEMENTS, "background": "x" * 2001,
    })
    assert resp.status_code == 400, resp.status_code
    print("[OK] oversized style field -> 400")


def test_valid_payload_passes_validation():
    resp = post({
        "workflow": "ideogram4_regional_t2i", "prompt": "a cat",
        "elements_data": VALID_ELEMENTS, "width": 1080, "height": 1920,
        "background": "blue wall", "style": "photo",
    })
    assert resp.status_code != 400, resp.get_json()
    print("[OK] valid payload passes ideogram4_regional_t2i validation (no 400)")


def test_existing_workflow_text_to_image_unaffected():
    resp = post({"workflow": "text_to_image", "prompt": "a cat"})
    assert resp.status_code != 400, resp.get_json()
    print("[OK] text_to_image request unaffected by new validation branch")


def test_existing_workflow_ltx_retake_v2v_requires_video():
    resp = post({"workflow": "ltx_retake_v2v", "prompt": "a cat"})
    assert resp.status_code == 400, resp.status_code
    assert "video" in resp.get_json().get("error", "")
    print("[OK] ltx_retake_v2v validation behavior unchanged (still requires video)")


if __name__ == "__main__":
    test_missing_prompt_rejected()
    test_malformed_elements_data_rejected_no_reflection()
    test_oversized_elements_data_rejected()
    test_missing_elements_data_defaults_to_empty_array()
    test_width_height_out_of_range_rejected()
    test_style_field_too_long_rejected()
    test_valid_payload_passes_validation()
    test_existing_workflow_text_to_image_unaffected()
    test_existing_workflow_ltx_retake_v2v_requires_video()
    print("All ideogram4_regional_t2i backend validation tests passed.")
