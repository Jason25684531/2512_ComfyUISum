from datetime import datetime, timedelta, timezone

from shared.error_sanitizer import classify_comfy_error, sanitize_error
from shared.job_contracts import JobStatus, canonical_status, duration_ms, is_valid_transition, public_status, success_rate


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


def test_public_and_canonical_status_conversion_is_shared():
    assert public_status(JobStatus.RUNNING) == "processing"
    assert public_status(JobStatus.COMPLETED) == "finished"
    assert canonical_status("processing") == JobStatus.RUNNING.value
    assert canonical_status("finished") == JobStatus.COMPLETED.value
    assert canonical_status("queued") == JobStatus.QUEUED.value


def test_error_sanitization_and_mapping():
    value = sanitize_error("password=secret C:\\private\\prompt.txt https://host/?token=bad")
    assert "secret" not in value and "private" not in value and "token=bad" not in value
    assert classify_comfy_error("CUDA out of memory") == "GPU_OUT_OF_MEMORY"
