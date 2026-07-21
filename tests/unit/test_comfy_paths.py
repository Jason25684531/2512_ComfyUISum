from worker.src.comfy_paths import normalize_comfy_paths


def test_windows_keeps_prefixed_face_swap_lora(monkeypatch):
    monkeypatch.setenv("COMFYUI_RUNTIME_PROFILE", "windows")
    path = "qwen_image_edit_2509\\bfs_head_v3_qwen_image_edit_2509.safetensors"
    assert normalize_comfy_paths(path) == path
