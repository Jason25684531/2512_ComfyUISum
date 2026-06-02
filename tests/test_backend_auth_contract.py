import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from flask_login import UserMixin


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"

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


class FakeUser(UserMixin):
    def __init__(self, user_id, email, password, name="Alice", role="member"):
        self.id = user_id
        self.email = email
        self.password_hash = backend_app.bcrypt.generate_password_hash(password).decode("utf-8")
        self.name = name
        self.role = role
        self.created_at = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class FakeQuery:
    def __init__(self, session, users):
        self.session = session
        self.users = list(users)

    def filter_by(self, **kwargs):
        filtered = self.users
        for key, value in kwargs.items():
            filtered = [user for user in filtered if getattr(user, key, None) == value]
        return FakeQuery(self.session, filtered)

    def first(self):
        return self.users[0] if self.users else None

    def get(self, user_id):
        return self.session.users_by_id.get(int(user_id))


class FakeSession:
    def __init__(self, users=None):
        self.users_by_id = {int(user.id): user for user in (users or [])}
        self.commit_count = 0
        self.deleted = []
        self.next_id = max(self.users_by_id.keys(), default=0) + 1

    @property
    def users(self):
        return list(self.users_by_id.values())

    def query(self, model):
        return FakeQuery(self, self.users)

    def add(self, user):
        if getattr(user, "id", None) is None:
            user.id = self.next_id
            self.next_id += 1
        self.users_by_id[int(user.id)] = user

    def delete(self, user):
        self.deleted.append(user)
        self.users_by_id.pop(int(user.id), None)

    def commit(self):
        self.commit_count += 1

    def close(self):
        return None


def auth_route_methods():
    result = {}
    for rule in backend_app.app.url_map.iter_rules():
        if rule.rule.startswith("/api/user/") or rule.rule in {
            "/api/register",
            "/api/login",
            "/api/logout",
            "/api/me",
        }:
            result[rule.rule] = sorted(rule.methods - {"HEAD", "OPTIONS"})
    return result


def test_auth_member_route_map_contract():
    assert auth_route_methods() == {
        "/api/register": ["POST"],
        "/api/login": ["POST"],
        "/api/logout": ["POST"],
        "/api/me": ["GET"],
        "/api/user/profile": ["PUT"],
        "/api/user/password": ["PUT"],
        "/api/user/delete": ["DELETE"],
    }


def test_login_me_logout_session_contract(monkeypatch):
    user = FakeUser(7, "member@example.com", "password123", name="Alice")
    fake_session = FakeSession([user])
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)
    client = backend_app.app.test_client()

    logged_out = client.get("/api/me")
    assert logged_out.status_code == 200
    assert logged_out.get_json() == {"logged_in": False, "user": None}

    login = client.post(
        "/api/login",
        json={"email": "MEMBER@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert "Set-Cookie" in login.headers
    assert login.get_json() == {
        "success": True,
        "user": user.to_dict(),
    }

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.get_json() == {
        "logged_in": True,
        "user": user.to_dict(),
    }

    logout = client.post("/api/logout")
    assert logout.status_code == 200
    assert "Set-Cookie" in logout.headers
    assert logout.get_json() == {
        "success": True,
        "message": "Logged out successfully",
    }

    after_logout = client.get("/api/me")
    assert after_logout.status_code == 200
    assert after_logout.get_json() == {"logged_in": False, "user": None}


def test_login_validation_and_invalid_credentials_contract(monkeypatch):
    user = FakeUser(7, "member@example.com", "password123")
    monkeypatch.setattr(backend_app, "get_db_session", lambda: FakeSession([user]))
    client = backend_app.app.test_client()

    missing_json = client.post("/api/login", data="null", content_type="application/json")
    assert missing_json.status_code == 400
    assert missing_json.get_json() == {"error": "Missing JSON data"}

    missing_fields = client.post("/api/login", json={"email": "member@example.com"})
    assert missing_fields.status_code == 400
    assert missing_fields.get_json() == {"error": "Email and password are required"}

    invalid = client.post(
        "/api/login",
        json={"email": "member@example.com", "password": "wrong-password"},
    )
    assert invalid.status_code == 401
    assert invalid.get_json() == {"error": "Invalid email or password"}


def test_register_success_and_validation_contract(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)
    client = backend_app.app.test_client()

    registered = client.post(
        "/api/register",
        json={"email": "NEW@example.com", "password": "password123", "name": "New Member"},
    )
    assert registered.status_code == 201
    payload = registered.get_json()
    assert set(payload) == {"success", "user"}
    assert payload["success"] is True
    assert payload["user"]["email"] == "new@example.com"
    assert payload["user"]["name"] == "New Member"
    assert payload["user"]["role"] == "member"
    assert fake_session.commit_count == 1

    duplicate = client.post(
        "/api/register",
        json={"email": "new@example.com", "password": "password123", "name": "Again"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json() == {"error": "Email already registered"}

    short_password = client.post(
        "/api/register",
        json={"email": "short@example.com", "password": "123", "name": "Short"},
    )
    assert short_password.status_code == 400
    assert short_password.get_json() == {"error": "Password must be at least 6 characters"}


def test_member_routes_require_authentication():
    client = backend_app.app.test_client()

    profile = client.put("/api/user/profile", json={"name": "No Session"})
    assert profile.status_code == 401
    assert profile.get_json() == {"error": "Authentication required"}

    password = client.put(
        "/api/user/password",
        json={"old_password": "old", "new_password": "new-password"},
    )
    assert password.status_code == 401
    assert password.get_json() == {"error": "Authentication required"}

    delete = client.delete("/api/user/delete")
    assert delete.status_code == 401
    assert delete.get_json() == {"error": "Authentication required"}


def test_profile_password_and_delete_member_contract(monkeypatch):
    user = FakeUser(7, "member@example.com", "password123", name="Alice")
    fake_session = FakeSession([user])
    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)
    client = backend_app.app.test_client()

    login = client.post(
        "/api/login",
        json={"email": "member@example.com", "password": "password123"},
    )
    assert login.status_code == 200

    profile = client.put(
        "/api/user/profile",
        json={"name": "Updated Alice", "email": "UPDATED@example.com"},
    )
    assert profile.status_code == 200
    assert profile.get_json()["success"] is True
    assert profile.get_json()["user"]["name"] == "Updated Alice"
    assert profile.get_json()["user"]["email"] == "updated@example.com"
    assert user.name == "Updated Alice"
    assert user.email == "updated@example.com"

    password = client.put(
        "/api/user/password",
        json={"old_password": "password123", "new_password": "new-password"},
    )
    assert password.status_code == 200
    assert password.get_json() == {
        "success": True,
        "message": "Password updated successfully",
    }
    assert backend_app.bcrypt.check_password_hash(user.password_hash, "new-password")

    delete = client.delete("/api/user/delete")
    assert delete.status_code == 200
    assert delete.get_json() == {
        "success": True,
        "message": "Account deleted successfully",
    }
    assert fake_session.deleted == [user]

    after_delete = client.get("/api/me")
    assert after_delete.status_code == 200
    assert after_delete.get_json() == {"logged_in": False, "user": None}
