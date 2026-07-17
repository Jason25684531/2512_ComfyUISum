from pathlib import Path


def test_jobs_schema_allows_unknown_legacy_dimensions():
    schema = Path("migrations/001_job_observability.sql").read_text(encoding="utf-8")
    for column in ("workflow_version", "worker_id", "started_at", "completed_at"):
        assert f"{column} " in schema
        assert f"{column} VARCHAR" in schema or f"{column} DATETIME" in schema
    assert " NULL" in schema
