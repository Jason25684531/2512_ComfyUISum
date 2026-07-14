"""Deterministic Node 178 caption regression and live schema witness."""

import hashlib
import json
import sys
from pathlib import Path

WORKER_SRC = Path(__file__).resolve().parent / "src"
sys.path[:0] = [str(WORKER_SRC.parent.parent), str(WORKER_SRC)]

from comfy_client import ComfyClient  # noqa: E402
from json_parser import parse_workflow  # noqa: E402
from regional_prompt import SAFE_ERROR, verify_regional_caption_contract  # noqa: E402


FIXTURES = [
    [{"x": .1, "y": .2, "w": .3, "h": .4, "type": "obj", "text": "", "desc": "fixture object", "palette": ["#abcdef"]}],
    [{"x": .55, "y": .1, "w": .2, "h": .15, "type": "text", "text": "fixture text", "desc": "fixture label", "palette": ["#123456"]}],
]


def build(elements):
    return parse_workflow("ideogram4_regional_t2i", prompt="fixture prompt", seed=7, extra_params={"elements_data": json.dumps(elements), "background": "fixture background"})


def test_two_bbox_fixtures_live_schema():
    client = ComfyClient()
    response = __import__("requests").get(f"{client.http_url}/object_info/Ideogram4PromptBuilderKJ", timeout=10)
    assert response.status_code == 200
    captions = [client.verify_regional_caption_contract(build(elements)) for elements in FIXTURES]
    obj, text = (caption["compositional_deconstruction"]["elements"][0] for caption in captions)
    assert obj["bbox"] == [200, 100, 600, 400] and obj["desc"] == "fixture object"
    assert text["bbox"] == [100, 550, 250, 750] and text["text"] == "fixture text"
    assert captions[0] != captions[1]
    for caption in captions:
        encoded = json.dumps(caption, sort_keys=True).encode()
        print(f"witness count=1 schema=Ideogram4PromptBuilderKJ sha256={hashlib.sha256(encoded).hexdigest()}")


def test_incompatible_schema_fails_closed():
    try:
        verify_regional_caption_contract(build(FIXTURES[0]), {})
    except RuntimeError as exc:
        assert str(exc) == SAFE_ERROR
    else:
        raise AssertionError("incompatible schema must fail")


if __name__ == "__main__":
    test_two_bbox_fixtures_live_schema()
    test_incompatible_schema_fails_closed()
    print("Regional prompt regression checks passed.")
