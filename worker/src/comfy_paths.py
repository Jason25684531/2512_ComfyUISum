"""
Helpers for normalizing ComfyUI workflow model paths before submission.
"""

from __future__ import annotations

import os


BACKSLASH = chr(92)

PATH_REPLACEMENTS = (
    (
        "Qwen" + BACKSLASH + "Qwen-Image-Edit-2509-Q4_K_M.gguf",
        "Qwen_Image_Edit/Qwen-Image-Edit-2509-Q4_K_M.gguf",
    ),
    (
        "Qwen_Image_Edit" + BACKSLASH + "Qwen-Image-Edit-2509-Q4_K_M.gguf",
        "Qwen_Image_Edit/Qwen-Image-Edit-2509-Q4_K_M.gguf",
    ),
    (
        "Qwen" + BACKSLASH + "qwen_image_edit_2511_bf16.safetensors",
        "Qwen/qwen_image_edit_2511_bf16.safetensors",
    ),
    (
        "Qwen" + BACKSLASH + "qwen_image_vae.safetensors",
        "Qwen_Image_Edit/split_files/vae/qwen_image_vae.safetensors",
    ),
    (
        "Qwen_Image_Edit" + BACKSLASH + "qwen_image_vae.safetensors",
        "Qwen_Image_Edit/split_files/vae/qwen_image_vae.safetensors",
    ),
    (
        "Qwen" + BACKSLASH + "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "Qwen_Image_Edit/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
    ),
    (
        "Qwen_Image_Edit" + BACKSLASH + "qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "Qwen_Image_Edit/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
    ),
    (
        "Qwen_Edit" + BACKSLASH + "Lightning" + BACKSLASH + "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
        "Qwen_Edit/Lightning/Qwen-Image-Lightning-4steps-V1.0.safetensors",
    ),
    (
        "Qwen_Image_Edit" + BACKSLASH + "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
        "Qwen_Edit/Lightning/Qwen-Image-Lightning-4steps-V1.0.safetensors",
    ),
    (
        "Qwen_Edit" + BACKSLASH + "bfs_head_v3_qwen_image_edit_2509.safetensors",
        "bfs_head_v3_qwen_image_edit_2509.safetensors",
    ),
    (
        "Qwen_Image_Edit" + BACKSLASH + "bfs_head_v3_qwen_image_edit_2509.safetensors",
        "bfs_head_v3_qwen_image_edit_2509.safetensors",
    ),
    ("Wan2.2" + BACKSLASH, "Wan2.2/"),
    ("Wan2.1" + BACKSLASH, "Wan2.1/"),
    ("wan2.1" + BACKSLASH, "Wan2.1/"),
    ("InfiniTetalk" + BACKSLASH, "InfiniteTalk/"),
)


def _resolve_target_profile() -> str:
    """偵測目標 ComfyUI 平台（windows / linux）"""
    profile = os.getenv("COMFYUI_RUNTIME_PROFILE", "")
    if profile:
        return profile.lower()
    import platform
    return "windows" if platform.system().lower().startswith("win") else "linux"


REVERSE_PATH_REPLACEMENTS = (
    (
        "Qwen_Image_Edit/Qwen-Image-Edit-2509-Q4_K_M.gguf",
        "Qwen_Image_Edit" + BACKSLASH + "Qwen-Image-Edit-2509-Q4_K_M.gguf",
    ),
    (
        "Qwen/qwen_image_edit_2511_bf16.safetensors",
        "Qwen_Image_Edit" + BACKSLASH + "qwen_image_edit_2511_bf16.safetensors",
    ),
    (
        "Qwen_Image_Edit/split_files/vae/qwen_image_vae.safetensors",
        "Qwen_Image_Edit" + BACKSLASH + "qwen_image_vae.safetensors",
    ),
    (
        "Qwen_Image_Edit/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
        "Qwen_Image_Edit" + BACKSLASH + "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    ),
    (
        "Qwen_Edit/Lightning/Qwen-Image-Lightning-4steps-V1.0.safetensors",
        "Qwen_Image_Edit" + BACKSLASH + "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors",
    ),
    (
        "bfs_head_v3_qwen_image_edit_2509.safetensors",
        "Qwen_Image_Edit" + BACKSLASH + "bfs_head_v3_qwen_image_edit_2509.safetensors",
    ),
    ("Wan2.2/", "Wan2.2" + BACKSLASH),
    ("Wan2.1/", "Wan2.1" + BACKSLASH),
    ("InfiniteTalk/", "InfiniTetalk" + BACKSLASH),
)


def normalize_comfy_paths(obj):
    """正規化模型路徑以匹配目標 ComfyUI 平台。

    當目標為 Windows 時，將 Linux 正斜線路徑轉為 Windows 反斜線路徑。
    當目標為 Linux 時，將 Windows 反斜線路徑轉為 Linux 正斜線路徑。
    """
    if _resolve_target_profile() == "windows":
        return _normalize_for_windows(obj)
    return _normalize_for_linux(obj)


def _normalize_for_windows(obj):
    """反向正規化邏輯：將 Linux 正斜線路徑轉為 Windows 反斜線路徑"""
    if isinstance(obj, dict):
        return {key: _normalize_for_windows(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_windows(value) for value in obj]
    if isinstance(obj, str):
        normalized = obj
        for old, new in REVERSE_PATH_REPLACEMENTS:
            normalized = normalized.replace(old, new)
        return normalized
    return obj


def _normalize_for_linux(obj):
    """原始正規化邏輯：將反斜線路徑轉為正斜線（適用於 Linux ComfyUI）"""
    if isinstance(obj, dict):
        return {key: _normalize_for_linux(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_normalize_for_linux(value) for value in obj]
    if isinstance(obj, str):
        normalized = obj
        for old, new in PATH_REPLACEMENTS:
            normalized = normalized.replace(old, new)
        return normalized.replace("\\", "/")
    return obj
