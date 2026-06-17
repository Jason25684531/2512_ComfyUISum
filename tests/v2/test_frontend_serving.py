from __future__ import annotations

import pytest


@pytest.mark.parametrize("path", ["/", "/index.html", "/dashboard", "/dashboard.html", "/login.html", "/profile.html"])
def test_frontend_entry_pages_return_html(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]


@pytest.mark.parametrize(
    "path, expected_content_type",
    [
        ("/config.js", "javascript"),
        ("/motion-workspace.js", "javascript"),
        ("/image-utils.js", "javascript"),
        ("/build-icons.js", "javascript"),
        ("/tailwind.generated.css", "text/css"),
        ("/vendor/lucide.min.js", "javascript"),
        ("/image/LOGO.png", "image/png"),
        ("/image/Circle.mp4", "video/mp4"),
        ("/front/TT Norms Pro Bold.ttf", None),
    ],
)
def test_root_relative_frontend_assets_are_accessible(client, path, expected_content_type):
    response = client.get(path)
    assert response.status_code == 200, response.text
    if expected_content_type is not None:
        assert expected_content_type in response.headers["content-type"]


def test_frontend_mount_still_serves_original_file_paths(client):
    response = client.get("/frontend/config.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_missing_frontend_mount_file_returns_404(client):
    response = client.get("/frontend/nonexistent.js")
    assert response.status_code == 404


def test_api_routes_remain_available_after_frontend_serving(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_docs_route_remains_available(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
