from pathlib import Path


def test_migrations_are_ordered_and_present():
    files = sorted(Path("migrations").glob("*.sql"))
    assert [item.name for item in files] == ["001_job_observability.sql", "002_job_dispatches.sql"]
