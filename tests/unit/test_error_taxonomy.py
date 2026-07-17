from shared.error_sanitizer import classify_comfy_error, sanitize_error


def test_sanitizer_hides_sensitive_details():
    text = sanitize_error("prompt=secret password=x C:/private/file.py SELECT * FROM jobs")
    assert "secret" not in text and "password=x" not in text and "C:/private" not in text


def test_comfy_error_mapping():
    assert classify_comfy_error("CUDA out of memory") == "GPU_OUT_OF_MEMORY"
    assert classify_comfy_error("socket timeout") == "COMFYUI_TIMEOUT"
