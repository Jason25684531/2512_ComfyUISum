from datetime import datetime, timedelta, timezone

from shared.error_sanitizer import classify_comfy_error, sanitize_error
from shared.job_contracts import JobStatus, duration_ms, is_valid_transition, success_rate


def test_state_machine_rejects_terminal_overwrite():
    assert is_valid_transition(JobStatus.QUEUED, JobStatus.RUNNING)
    assert not is_valid_transition(JobStatus.COMPLETED, JobStatus.FAILED)


def test_duration_rejects_negative_clock():
    now = datetime.now(timezone.utc)
    assert duration_ms(now, now + timedelta(milliseconds=12)) == 12
    assert duration_ms(now, now - timedelta(seconds=1)) is None


def test_success_rate_excludes_cancelled_by_construction():
    assert success_rate(8, 2) == 0.8
    assert success_rate(0, 0) is None


def test_error_sanitization_and_mapping():
    value = sanitize_error("password=secret C:\\private\\prompt.txt https://host/?token=bad")
    assert "secret" not in value and "private" not in value and "token=bad" not in value
    assert classify_comfy_error("CUDA out of memory") == "GPU_OUT_OF_MEMORY"
