import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

os.environ.setdefault("STUDIO_ENV_FILE", ".env.local")
os.environ.setdefault("REDIS_CONNECT_RETRIES", "0")
os.environ.setdefault("REDIS_HOST", "127.0.0.1")
os.environ.setdefault("REDIS_PORT", "1")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "1")
os.environ.setdefault("DB_PASSWORD", "test-password")

import app as backend_app


@pytest.fixture(autouse=True)
def isolate_backend_app(monkeypatch):
    monkeypatch.setitem(backend_app.app.config, "TESTING", True)
    monkeypatch.setitem(backend_app.app.config, "RATELIMIT_ENABLED", False)
    monkeypatch.setattr(backend_app.limiter, "enabled", False)
    monkeypatch.setattr(backend_app, "redis_client", None)
    monkeypatch.setattr(backend_app, "db_client", FakeDbClient())
    yield


class FakeDbClient:
    def get_or_create_user_id(self, ip_address):
        return 1


def rule_order():
    return [rule.rule for rule in backend_app.app.url_map.iter_rules()]


def test_static_route_map_keeps_catch_all_after_api_health_and_outputs():
    rules = rule_order()
    catch_all_index = rules.index("/<path:path>")

    assert rules.index("/") < catch_all_index
    assert rules.index("/outputs/<path:filename>") < catch_all_index
    assert rules.index("/health") < catch_all_index
    assert rules.index("/api/health") < catch_all_index

    api_rules = [rule for rule in rules if rule.startswith("/api/")]
    assert api_rules
    assert all(rules.index(rule) < catch_all_index for rule in api_rules)


def test_root_serves_login_html_for_unauthenticated_user():
    response = backend_app.app.test_client().get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.data == (FRONTEND_DIR / "login.html").read_bytes()


def test_known_frontend_pages_follow_current_auth_redirect_contract():
    client = backend_app.app.test_client()

    login = client.get("/login.html")
    assert login.status_code == 200
    assert login.mimetype == "text/html"
    assert login.data == (FRONTEND_DIR / "login.html").read_bytes()

    dashboard = client.get("/dashboard.html")
    assert dashboard.status_code == 302
    assert dashboard.location == "/login.html"

    legacy_index = client.get("/index.html")
    assert legacy_index.status_code == 302
    assert legacy_index.location == "/login.html"


def test_frontend_asset_path_serves_static_file():
    response = backend_app.app.test_client().get("/config.js")

    assert response.status_code == 200
    assert response.data == (FRONTEND_DIR / "config.js").read_bytes()
    assert response.mimetype in {"text/javascript", "application/javascript"}


def test_unknown_non_api_frontend_route_uses_index_html_fallback():
    response = backend_app.app.test_client().get("/workspace/deep-link")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.data == (FRONTEND_DIR / "index.html").read_bytes()


def test_unknown_api_route_is_not_served_as_frontend_html():
    response = backend_app.app.test_client().get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.mimetype == "application/json"
    assert response.get_json() == {"error": "Not found"}
    assert response.data != (FRONTEND_DIR / "index.html").read_bytes()


def test_outputs_route_is_not_swallowed_by_frontend_catch_all(monkeypatch, tmp_path):
    output_file = tmp_path / "route-order.png"
    output_file.write_bytes(b"output-bytes")
    monkeypatch.setenv("STORAGE_OUTPUT_DIR", str(tmp_path))
    client = backend_app.app.test_client()

    valid = client.get("/outputs/route-order.png")
    assert valid.status_code == 200
    assert valid.data == b"output-bytes"
    assert valid.mimetype == "image/png"

    missing = client.get("/outputs/missing-route-order.png")
    assert missing.status_code == 404
    assert missing.mimetype == "text/html"
    assert missing.data != (FRONTEND_DIR / "index.html").read_bytes()

