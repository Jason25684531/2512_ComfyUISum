from datetime import datetime, timedelta, timezone

from shared.job_contracts import JobStatus, duration_fields, is_valid_transition


def test_terminal_states_cannot_transition():
    for terminal in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        assert not is_valid_transition(terminal, JobStatus.RUNNING)


def test_duration_fields_reject_negative_clock():
    now = datetime.now(timezone.utc)
    assert duration_fields({"queued_at": now, "started_at": now - timedelta(seconds=1)})["queue_wait_ms"] is None
