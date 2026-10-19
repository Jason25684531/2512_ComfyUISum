import io
import json
from urllib.error import URLError

from scripts import validate_local_startup as startup


def test_readiness_checks_are_read_only_and_fail_closed(monkeypatch):
    health = {"status": "ok", "redis": "healthy", "mysql": "healthy", "worker": "online"}
    seen = []

    def respond(url, timeout):
        seen.append((url, timeout))
        payload = {"system": {}} if url.endswith("/system_stats") else health
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(startup.urllib.request, "urlopen", respond)
    assert all(ok for _, ok in startup._check_backend("http://backend"))
    assert startup._check_comfyui("http://engine")
    health.update(status="degraded", redis="unavailable", worker="offline")
    assert dict(startup._check_backend("http://backend")) == {
        "Backend": False, "Redis": False, "MySQL": True, "Worker": False,
    }
    assert all(timeout == 5 for _, timeout in seen)

    def unavailable(*args, **kwargs):
        raise URLError("private detail")

    monkeypatch.setattr(startup.urllib.request, "urlopen", unavailable)
    assert not any(ok for _, ok in startup._check_backend("http://backend"))
    assert not startup._check_comfyui("http://engine")
    monkeypatch.setattr(startup.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"invalid"))
    assert not any(ok for _, ok in startup._check_backend("http://backend"))
