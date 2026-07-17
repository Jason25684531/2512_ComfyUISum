"""Live Flask integration smoke; run with the compose stack already started."""
import os

import pytest
import requests


BASE = os.getenv("STUDIO_TEST_URL", "http://127.0.0.1:5000")


def test_admin_health_and_jobs_are_bounded():
    try:
        health = requests.get(f"{BASE}/api/admin/system/health", timeout=3)
    except requests.RequestException:
        pytest.skip("compose stack is not running")
    assert health.status_code == 200
    response = requests.get(f"{BASE}/api/admin/jobs?page_size=1", timeout=3)
    assert response.status_code == 200
    assert response.json()["page_size"] == 1
