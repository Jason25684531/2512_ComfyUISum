"""
Helpers for normalizing ComfyUI workflow model paths before submission.
"""

from __future__ import annotations


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


def normalize_comfy_paths(obj):
    if isinstance(obj, dict):
        return {key: normalize_comfy_paths(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [normalize_comfy_paths(value) for value in obj]
    if isinstance(obj, str):
        normalized = obj
        for old, new in PATH_REPLACEMENTS:
            normalized = normalized.replace(old, new)
        return normalized.replace("\\", "/")
    return obj
