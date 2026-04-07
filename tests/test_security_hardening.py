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

import app as backend_app
from shared import database as shared_database
from shared.security import INTERNAL_SERVER_ERROR_MESSAGE, get_flask_debug_mode


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    monkeypatch.setattr(backend_app, "redis_client", None)
    yield


class FakeUser(UserMixin):
    def __init__(self, user_id, email, password_hash, name, role="member"):
        self.id = user_id
        self.email = email
        self.password_hash = password_hash
        self.name = name
        self.role = role
        self.created_at = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class FakeQuery:
    def __init__(self, users):
        self._users = list(users)

    def filter_by(self, **kwargs):
        filtered = self._users
        for key, value in kwargs.items():
            filtered = [user for user in filtered if getattr(user, key, None) == value]
        return FakeQuery(filtered)

    def first(self):
        return self._users[0] if self._users else None

    def get(self, user_id):
        for user in self._users:
            if int(user.id) == int(user_id):
                return user
        return None


class FakeSession:
    def __init__(self, users):
        self._users = {user.id: user for user in users}
        self.commit_count = 0

    def query(self, model):
        return FakeQuery(self._users.values())

    def add(self, user):
        self._users[user.id] = user

    def commit(self):
        self.commit_count += 1

    def close(self):
        return None


class FakeDbClient:
    def __init__(self, history_jobs):
        self.history_jobs = history_jobs
        self.history_calls = []
        self.status_updates = []

    def get_or_create_user_id(self, ip_address):
        return 1

    def get_history(self, limit=50, offset=0, user_id=None):
        self.history_calls.append({
            "limit": limit,
            "offset": offset,
            "user_id": user_id,
        })
        return self.history_jobs[offset:offset + limit]

    def update_job_status(self, job_id, status, output_path=None):
        self.status_updates.append({
            "job_id": job_id,
            "status": status,
            "output_path": output_path,
        })
        return True

    def check_connection(self):
        return True


class FakeRedis:
    def __init__(self, status_map):
        self.status_map = status_map

    def hgetall(self, key):
        return self.status_map.get(key, {})


def test_status_response_escapes_dynamic_strings(monkeypatch):
    class FakeRedis:
        def hgetall(self, key):
            return {
                "job_id": "job-1<script>",
                "status": "finished<script>",
                "progress": "50",
                "image_url": "/outputs/<img>.png",
                "error": "<script>alert(1)</script>",
            }

    monkeypatch.setattr(backend_app, "redis_client", FakeRedis())
    monkeypatch.setattr(backend_app, "db_client", None)

    client = backend_app.app.test_client()
    response = client.get("/api/status/job-1")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["job_id"] == "job-1&lt;script&gt;"
    assert payload["status"] == "finished&lt;script&gt;"
    assert payload["error"] == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_history_response_escapes_database_strings(monkeypatch):
    class FakeDatabase:
        def get_or_create_user_id(self, ip_address):
            return 1

        def get_history(self, limit=50, offset=0, user_id=None):
            return [{
                "id": "job-1",
                "prompt": "<script>alert(1)</script>",
                "workflow": "text_to_image",
                "model": "model<script>.safetensors",
                "status": "finished",
                "output_path": "/outputs/<img>.png",
                "created_at": "2026-04-07T12:00:00",
                "updated_at": "2026-04-07T12:05:00",
            }]

    monkeypatch.setattr(backend_app, "db_client", FakeDatabase())

    client = backend_app.app.test_client()
    response = client.get("/api/history")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["jobs"][0]["prompt"] == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert payload["jobs"][0]["model"] == "model&lt;script&gt;.safetensors"
    assert payload["jobs"][0]["output_path"] == "/outputs/&lt;img&gt;.png"


def test_serve_static_rejects_traversal():
    with backend_app.app.test_request_context("/../../README.md"):
        response, status_code = backend_app.serve_static("../../README.md")

    assert status_code == 403
    assert response.get_json()["error"] == "Invalid input data"


def test_serve_index_hides_exception_details(monkeypatch):
    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("<script>alert('boom')</script>")

    monkeypatch.setattr(backend_app, "send_from_directory", raise_runtime_error)

    with backend_app.app.test_request_context("/"):
        response, status_code = backend_app.serve_index()

    assert status_code == 500
    assert response.get_json()["error"] == INTERNAL_SERVER_ERROR_MESSAGE


def test_get_db_engine_requires_password(monkeypatch):
    shared_database._engine = None
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "studio_user")
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.setenv("DB_NAME", "studio_db")

    with pytest.raises(ValueError, match="DB_PASSWORD is not set"):
        shared_database.get_db_engine()


def test_debug_mode_reads_environment(monkeypatch):
    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")
    assert get_flask_debug_mode() is True

    monkeypatch.setenv("FLASK_DEBUG", "false")
    assert get_flask_debug_mode() is False


def test_flask_client_authenticated_flow_covers_login_profile_history_status(monkeypatch):
    user = FakeUser(
        user_id=7,
        email="member@example.com",
        password_hash=backend_app.bcrypt.generate_password_hash("password123").decode("utf-8"),
        name="Alice <script>",
    )
    fake_session = FakeSession([user])
    fake_db_client = FakeDbClient([
        {
            "id": "job-123",
            "prompt": "<b>danger prompt</b>",
            "workflow": "text_to_image",
            "model": "model<script>.safetensors",
            "status": "finished",
            "output_path": r"C:\outputs\<final>.png",
            "created_at": "2026-04-07T12:00:00",
            "updated_at": "2026-04-07T12:05:00",
        }
    ])
    fake_redis = FakeRedis({
        "job:status:job-123": {
            "job_id": "job-123",
            "status": "finished",
            "progress": "100",
            "image_url": "/outputs/<final>.png",
            "error": "Operation failed",
        }
    })

    monkeypatch.setattr(backend_app, "get_db_session", lambda: fake_session)
    monkeypatch.setattr(backend_app, "db_client", fake_db_client)
    monkeypatch.setattr(backend_app, "redis_client", fake_redis)

    client = backend_app.app.test_client()

    login_response = client.post(
        "/api/login",
        json={"email": "member@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200
    assert login_response.get_json()["user"]["name"] == "Alice &lt;script&gt;"

    profile_response = client.put(
        "/api/user/profile",
        json={"name": "New <img>", "email": "new@example.com"},
    )
    assert profile_response.status_code == 200
    profile_payload = profile_response.get_json()
    assert profile_payload["user"]["name"] == "New &lt;img&gt;"
    assert profile_payload["user"]["email"] == "new@example.com"
    assert user.name == "New <img>"
    assert user.email == "new@example.com"

    history_response = client.get("/api/history?limit=10&offset=0")
    assert history_response.status_code == 200
    history_payload = history_response.get_json()
    assert history_payload["jobs"][0]["prompt"] == "&lt;b&gt;danger prompt&lt;/b&gt;"
    assert history_payload["jobs"][0]["model"] == "model&lt;script&gt;.safetensors"
    assert history_payload["jobs"][0]["output_path"] == "/outputs/&lt;final&gt;.png"
    assert fake_db_client.history_calls[0]["user_id"] == 7

    status_response = client.get("/api/status/job-123")
    assert status_response.status_code == 200
    status_payload = status_response.get_json()
    assert status_payload["job_id"] == "job-123"
    assert status_payload["status"] == "finished"
    assert status_payload["image_url"] == "/outputs/&lt;final&gt;.png"
    assert status_payload["error"] == "Operation failed"
    assert fake_db_client.status_updates[0] == {
        "job_id": "job-123",
        "status": "finished",
        "output_path": "/outputs/<final>.png",
    }