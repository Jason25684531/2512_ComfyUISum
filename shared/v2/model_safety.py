from __future__ import annotations

from copy import deepcopy


DEFAULT_TEXT_TO_IMAGE_MODEL_ENTRY = {
    "id": "",
    "name": "Default ComfyUI workflow model",
    "value": "",
    "type": "text_to_image",
    "description": "Use the checkpoint configured inside workflows/comfyui/text_to_image.basic.json",
}

DEFAULT_TEXT_TO_IMAGE_MODEL_LABELS = {
    "",
    "default comfyui workflow model",
}

UNSAFE_TEXT_TO_IMAGE_MODEL_TOKENS = (
    "wan",
    "infinitetalk",
    "talk",
    "talking",
    "video",
    "image_to_video",
    "avatar_talk",
)


def default_text_to_image_model_entry() -> dict:
    return deepcopy(DEFAULT_TEXT_TO_IMAGE_MODEL_ENTRY)


def text_to_image_model_options() -> list[dict]:
    return [default_text_to_image_model_entry()]


def sanitize_text_to_image_model(value: object) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""

    normalized = cleaned.lower().replace("\\", "/")
    if normalized in DEFAULT_TEXT_TO_IMAGE_MODEL_LABELS:
        return ""
    if any(token in normalized for token in UNSAFE_TEXT_TO_IMAGE_MODEL_TOKENS):
        return ""

    # Local-v2 treats the workflow JSON as the model source of truth; arbitrary
    # frontend model labels must not override ComfyUI loader nodes.
    return ""
