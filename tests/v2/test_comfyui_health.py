from __future__ import annotations

from pathlib import Path

import pytest


def test_comfyui_engine_health_check_handles_success_and_failure(settings, monkeypatch) -> None:
    from worker.engines.comfyui_engine import ComfyUIEngine

    engine = ComfyUIEngine(settings=settings)
    calls: list[str] = []

    class HealthyResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs):
        calls.append(url)
        return HealthyResponse()

    monkeypatch.setattr("httpx.get", fake_get)
    assert engine.health_check() is True
    assert calls == ["http://comfyui.internal:8188/system_stats"]

    def raise_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("httpx.get", raise_error)
    assert engine.health_check() is False


def test_comfyui_engine_execute_is_not_implemented(settings) -> None:
    from app.models.job import JobPayload
    from worker.engines.comfyui_engine import ComfyUIEngine

    engine = ComfyUIEngine(settings=settings)
    with pytest.raises(NotImplementedError):
        engine.execute(JobPayload(task_type="text_to_image"))


def test_comfyui_engine_source_has_no_local_filesystem_dependency() -> None:
    source = (Path(__file__).resolve().parents[2] / "apps" / "worker-v2" / "worker" / "engines" / "comfyui_engine.py").read_text(
        encoding="utf-8"
    )

    assert "windows_portable" not in source
    assert "C:\\" not in source
    assert "D:\\" not in source
    assert "http://" not in source
    assert "pathlib" not in source
    assert "Path(" not in source
