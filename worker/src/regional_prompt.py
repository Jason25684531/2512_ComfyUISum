"""Deterministic contract checks for the legacy Ideogram regional workflow."""

import json


NODE_ID = "178"
NODE_CLASS = "Ideogram4PromptBuilderKJ"
SAFE_ERROR = "Regional prompt node is unavailable or incompatible"
REQUIRED_INPUTS = {"width", "height", "high_level_description", "background", "style", "aesthetics", "lighting", "medium", "elements_data"}


def _bbox(box: dict) -> list[int]:
    x, y, w, h = (box[key] for key in ("x", "y", "w", "h"))
    xmin, ymin = round(x * 1000), round(y * 1000)
    xmax, ymax = round((x + w) * 1000), round((y + h) * 1000)
    return [min(ymin, ymax), min(xmin, xmax), max(ymin, ymax), max(xmin, xmax)]


def resolved_caption(workflow: dict) -> dict:
    """Mirror the Node 178 canonical regional caption without exposing it in logs."""
    node = workflow.get(NODE_ID, {})
    inputs = node.get("inputs", {})
    try:
        elements_data = json.loads(inputs.get("elements_data", "[]"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(SAFE_ERROR) from exc
    if node.get("class_type") != NODE_CLASS or not isinstance(elements_data, list):
        raise RuntimeError(SAFE_ERROR)

    elements = []
    for box in elements_data:
        if not isinstance(box, dict):
            raise RuntimeError(SAFE_ERROR)
        element = {"type": "text" if box.get("type") == "text" else "obj", "bbox": _bbox(box)}
        if element["type"] == "text":
            element["text"] = box.get("text", "")
        element["desc"] = box.get("desc", "")
        palette = [color.upper() for color in box.get("palette", []) if color]
        if palette:
            element["color_palette"] = palette[:5]
        elements.append(element)

    caption = {"compositional_deconstruction": {"background": inputs.get("background", ""), "elements": elements}}
    if inputs.get("high_level_description", "").strip():
        caption = {"high_level_description": inputs["high_level_description"], **caption}
    return caption


def verify_regional_caption_contract(workflow: dict, object_info: dict) -> dict:
    """Fail closed unless the live Node 178 schema can produce a caption string."""
    node_info = object_info.get(NODE_CLASS, {}) if isinstance(object_info, dict) else {}
    required = node_info.get("input", {}).get("required", {})
    output_names = node_info.get("output_name", [])
    outputs = node_info.get("output", [])
    if not REQUIRED_INPUTS.issubset(required) or not outputs or outputs[0] != "STRING" or not output_names or output_names[0] != "prompt":
        raise RuntimeError(SAFE_ERROR)
    return resolved_caption(workflow)
