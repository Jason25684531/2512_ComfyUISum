import importlib
import sys
from pathlib import Path


def test_cached_execution_recovers_before_websocket(monkeypatch):
    worker_src = Path(__file__).resolve().parents[2] / "worker" / "src"
    monkeypatch.syspath_prepend(str(worker_src))
    sys.modules.pop("config", None)
    comfy_client = importlib.import_module("comfy_client")

    client = comfy_client.ComfyClient()
    monkeypatch.setattr(
        client,
        "get_outputs_from_history",
        lambda _prompt_id: {
            "images": [{"filename": "cached.png", "type": "output"}],
            "videos": [],
            "gifs": [],
        },
    )

    def websocket_must_not_connect(*_args, **_kwargs):
        raise AssertionError("cached execution must not open a WebSocket")

    monkeypatch.setattr(comfy_client.websocket, "create_connection", websocket_must_not_connect)

    result = client.wait_for_completion("cached-prompt", timeout=1)

    assert result["success"] is True
    assert result["recovered_from_history"] is True
    assert result["images"][0]["filename"] == "cached.png"
