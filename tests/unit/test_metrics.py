from shared.job_contracts import duration_ms, success_rate


def test_success_rate_excludes_cancelled_and_handles_empty():
    assert success_rate(8, 2) == .8
    assert success_rate(0, 0) is None


def test_missing_duration_is_not_zero():
    assert duration_ms(None, None) is None
