import requests
import pytest


def test_real_completed_job_has_timeline():
    jobs = requests.get("http://127.0.0.1:5000/api/admin/jobs?status=completed&page_size=1", timeout=3).json()["items"]
    if not jobs:
        pytest.skip("requires a completed job")
    detail = requests.get(f"http://127.0.0.1:5000/api/admin/jobs/{jobs[0]['job_id']}", timeout=3).json()
    assert detail["job"]["status"] == "completed"
    assert any(e["event_type"] == "job_completed" for e in detail["events"])
