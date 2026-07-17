from datetime import datetime, timezone

from shared.job_tracker import JobTracker


class ReceiptRepository:
    def __init__(self):
        self.allow_finalize = False
        self.jobs = {"job": {"submitted_at": datetime.now(timezone.utc), "queued_at": datetime.now(timezone.utc), "started_at": datetime.now(timezone.utc)}}
        self.finalized = []

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def finalize_completed(self, job_id, updates, output, events):
        if not self.allow_finalize:
            return False
        self.finalized.append((job_id, updates, output, events))
        return True


def test_output_receipt_retries_metadata_without_gpu_rerun(tmp_path):
    output = tmp_path / "result.png"
    output.write_bytes(b"real persisted output")
    repository = ReceiptRepository()
    tracker = JobTracker(repository)
    assert not tracker.complete_with_output("job", path=output, storage_uri="/outputs/result.png", filename=output.name, output_type="image")
    assert (tmp_path / ".receipts" / "job.json").exists()
    repository.allow_finalize = True
    assert tracker.replay_output_receipts(tmp_path) == 1
    assert len(repository.finalized) == 1
    assert not (tmp_path / ".receipts" / "job.json").exists()
