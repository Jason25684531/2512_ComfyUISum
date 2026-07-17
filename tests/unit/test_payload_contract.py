from shared.job_contracts import validate_job_payload


GOOD_ID = "00000000-0000-4000-8000-000000000000"


def test_payload_versions_and_identity():
    assert validate_job_payload({"job_id": GOOD_ID})[0]
    assert validate_job_payload({"schema_version": 2, "job_id": GOOD_ID, "request_id": "r", "workflow": "w", "submitted_at": "2026-01-01T00:00:00Z"})[0]
    assert not validate_job_payload({"schema_version": 3, "job_id": GOOD_ID})[0]
    assert not validate_job_payload({"job_id": "missing"})[0]
