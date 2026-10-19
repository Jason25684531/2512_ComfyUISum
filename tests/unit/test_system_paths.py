"""Exercise file route containment without Redis, MySQL or a live server."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask


def test_system_file_routes(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend/src"))
    from system_routes import create_blueprint

    outputs = tmp_path / "outputs"
    frontend = tmp_path / "frontend"
    outputs.mkdir()
    frontend.mkdir()
    (outputs / "image.png").write_bytes(b"output-data")
    (frontend / "dashboard.html").write_text("dashboard", encoding="utf-8")
    app = Flask(__name__)
    app.extensions["backend_runtime"] = SimpleNamespace(
        storage_output_dir=outputs, project_root=tmp_path,
    )
    app.register_blueprint(create_blueprint(SimpleNamespace(limit=lambda _: lambda fn: fn)))
    client = app.test_client()
    response = client.get("/outputs/image.png")
    assert response.status_code == 200 and response.data == b"output-data"
    assert response.mimetype == "image/png"
    assert client.get("/outputs/missing.png").status_code == 404
    assert client.get("/outputs/...").status_code == 400
    assert client.get("/safe-missing-asset").data == b"dashboard"
    assert client.get("/%2e%2e/outside.txt").status_code == 403

    sibling = tmp_path / "outputs-private"
    sibling.mkdir()
    secret = sibling / "secret.png"
    secret.write_bytes(b"must-not-be-served")
    try:
        (outputs / "external.png").symlink_to(secret)
        (outputs / "internal.png").symlink_to(outputs / "image.png")
        (frontend / "external.png").symlink_to(secret)
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {type(exc).__name__}")
    for url in ("/outputs/external.png", "/external.png"):
        response = client.get(url)
        assert response.status_code == 403
        assert b"must-not-be-served" not in response.data
        assert str(tmp_path).encode() not in response.data
    assert client.get("/outputs/internal.png").data == b"output-data"
