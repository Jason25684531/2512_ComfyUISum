"""Trust-boundary validator for Ideogram4 regional-prompt bbox payloads.

Canonicalizes untrusted `elements_data` JSON strings before they enter the
Redis job queue, so downstream (worker/ComfyUI) never sees raw client input.
"""

from __future__ import annotations

import json
import re
from typing import Any


class ElementsDataValidator:
    """Validates and re-serializes the `elements_data` bbox array."""

    MAX_ELEMENTS = 50
    MAX_STRING_LENGTH = 2000
    ALLOWED_FIELDS = {"x", "y", "w", "h", "type", "text", "desc", "palette"}
    ALLOWED_TYPES = {"obj", "text"}
    COORD_FIELDS = ("x", "y", "w", "h")
    HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

    @classmethod
    def validate(cls, raw: str) -> str:
        """Parse, whitelist-check and re-serialize `raw` into canonical JSON.

        Raises ValueError (message contains no user input) on any violation.
        """
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("elements_data must be valid JSON")

        if not isinstance(parsed, list):
            raise ValueError("elements_data must be a JSON array")
        if len(parsed) > cls.MAX_ELEMENTS:
            raise ValueError(f"elements_data exceeds max element count ({cls.MAX_ELEMENTS})")

        canonical_elements = [cls._validate_element(item) for item in parsed]
        return json.dumps(canonical_elements, ensure_ascii=False)

    @classmethod
    def _validate_element(cls, item: Any) -> dict:
        if not isinstance(item, dict):
            raise ValueError("elements_data item must be an object")

        unknown_fields = set(item.keys()) - cls.ALLOWED_FIELDS
        if unknown_fields:
            raise ValueError("elements_data item contains unknown field(s)")

        for field in cls.COORD_FIELDS:
            value = item.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not (0 <= value <= 1):
                raise ValueError(f"elements_data.{field} must be a number in [0, 1]")

        element_type = item.get("type")
        if element_type not in cls.ALLOWED_TYPES:
            raise ValueError("elements_data.type must be 'obj' or 'text'")

        text = cls._validate_string(item.get("text", ""), "text")
        desc = cls._validate_string(item.get("desc", ""), "desc")
        palette = cls._validate_palette(item.get("palette", []))

        return {
            "x": item["x"],
            "y": item["y"],
            "w": item["w"],
            "h": item["h"],
            "type": element_type,
            "text": text,
            "desc": desc,
            "palette": palette,
        }

    @classmethod
    def _validate_string(cls, value: Any, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"elements_data.{field_name} must be a string")
        if len(value) > cls.MAX_STRING_LENGTH:
            raise ValueError(f"elements_data.{field_name} exceeds max length ({cls.MAX_STRING_LENGTH})")
        return value

    @classmethod
    def _validate_palette(cls, value: Any) -> list:
        if not isinstance(value, list):
            raise ValueError("elements_data.palette must be an array")
        for color in value:
            if not isinstance(color, str) or not cls.HEX_COLOR_RE.match(color):
                raise ValueError("elements_data.palette must contain #RRGGBB hex color strings")
        return value


if __name__ == "__main__":
    valid = ElementsDataValidator.validate(
        '[{"x":0.1,"y":0.2,"w":0.3,"h":0.4,"type":"obj","text":"","desc":"a box","palette":["#ffffff"]}]'
    )
    assert json.loads(valid) == [
        {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "type": "obj", "text": "", "desc": "a box", "palette": ["#ffffff"]}
    ]
    assert ElementsDataValidator.validate("[]") == "[]"

    for bad in [
        "not json",
        "{}",
        '[{"x":0.1,"y":0.2,"w":0.3,"h":0.4,"type":"obj","text":"","desc":"a","palette":[],"extra":1}]',
        '[{"x":2,"y":0.2,"w":0.3,"h":0.4,"type":"obj","text":"","desc":"a","palette":[]}]',
        '[{"x":0.1,"y":0.2,"w":0.3,"h":0.4,"type":"bad","text":"","desc":"a","palette":[]}]',
        '[{"x":0.1,"y":0.2,"w":0.3,"h":0.4,"type":"obj","text":"","desc":"a","palette":["red"]}]',
        "[" + ",".join(['{"x":0,"y":0,"w":0,"h":0,"type":"obj","text":"","desc":"","palette":[]}'] * 51) + "]",
    ]:
        try:
            ElementsDataValidator.validate(bad)
            raise AssertionError(f"expected ValueError for: {bad[:60]}")
        except ValueError:
            pass

    print("ElementsDataValidator self-check passed.")
