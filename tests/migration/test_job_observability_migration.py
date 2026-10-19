from pathlib import Path


def test_migrations_are_ordered_and_present():
    files = sorted(Path("migrations").glob("*.sql"))
    assert [item.name for item in files] == [
        "001_job_observability.sql", "002_job_dispatches.sql", "003_history_projection.sql",
        "004_dispatch_source_label_index.sql",
    ]
