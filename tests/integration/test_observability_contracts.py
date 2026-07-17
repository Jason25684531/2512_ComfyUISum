"""Contract checks that run against the real Flask/Redis/Worker stack when present."""
import os

import pytest
import requests

from shared.job_contracts import JobStatus, LEGACY_STATUS, validate_job_payload

BASE = os.getenv("STUDIO_TEST_URL", "http://127.0.0.1:5000")


def _get(path):
    try:
        response = requests.get(f"{BASE}{path}", timeout=3)
    except requests.RequestException:
        pytest.skip("compose stack is not running")
    return response


def test_real_stack_keeps_legacy_status_and_admin_routes_separate():
    jobs = _get("/api/admin/jobs?page_size=1")
    assert jobs.status_code == 200
    assert _get("/admin").status_code == 200
    assert _get("/admin/jobs").status_code == 200
    completed = _get("/api/admin/jobs?status=completed&page_size=1").json()["items"]
    if completed:
        status = _get(f"/api/status/{completed[0]['job_id']}").json()
        assert status["status"] == LEGACY_STATUS[JobStatus.COMPLETED]


def test_payload_mixed_deployment_contract_and_dead_letter_rejection():
    job_id = "00000000-0000-4000-8000-000000000000"
    assert validate_job_payload({"job_id": job_id})[0]  # old producer
    assert validate_job_payload({"schema_version": 2, "job_id": job_id, "request_id": "request", "workflow": "text_to_image", "submitted_at": "2026-01-01T00:00:00Z"})[0]
    assert not validate_job_payload({"schema_version": 99, "job_id": job_id})[0]
