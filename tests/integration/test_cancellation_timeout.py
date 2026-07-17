from shared.job_contracts import JobStatus, is_valid_transition


def test_cancelled_is_not_failed_transition():
    assert not is_valid_transition(JobStatus.CANCELLED, JobStatus.FAILED)
