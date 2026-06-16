from __future__ import annotations

def test_get_root_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_get_dashboard_returns_200(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_get_dashboard_html_returns_200(client):
    response = client.get("/dashboard.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_static_config_js_accessible(client):
    response = client.get("/frontend/config.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]

def test_nonexistent_static_file_returns_404(client):
    response = client.get("/frontend/nonexistent.js")
    assert response.status_code == 404
