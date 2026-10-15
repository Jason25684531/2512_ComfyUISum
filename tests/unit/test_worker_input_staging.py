import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "worker" / "src"))
import job_processor as processor


def test_failed_image_upload_stops_before_prompt_submission(monkeypatch):
    events = []
    statuses = []

    class ComfyClient:
        def check_connection(self):
            events.append("check_connection")
            return True

        def queue_prompt(self, _workflow):
            events.append("queue_prompt")
            pytest.fail("must not submit a workflow with an unavailable input image")

    entry = SimpleNamespace(enabled=True, version="1.0.0")
    resolution = SimpleNamespace(workflow_id="video_minimax_h3", entry=entry)
    catalog = SimpleNamespace(resolve=lambda _workflow: resolution)

    monkeypatch.setattr(processor, "JOB_OBSERVABILITY_ENABLED", False)
    monkeypatch.setattr(processor, "validate_job_payload", lambda _data: (True, None))
    monkeypatch.setattr(processor, "load_workflow_catalog", lambda: catalog)
    monkeypatch.setattr(processor, "WorkflowAdapter", lambda _entry: object())
    monkeypatch.setattr(processor, "save_base64_image", lambda *_args: "first-frame.png")

    def fail_upload(*_args):
        events.append("upload_image")
        raise ConnectionError("connection refused")

    monkeypatch.setattr(processor, "sync_image_to_comfyui_input", fail_upload)
    monkeypatch.setattr(processor, "parse_workflow", lambda **_kwargs: pytest.fail("must not parse after upload failure"))
    monkeypatch.setattr(processor, "update_job_status", lambda _redis, _job_id, status, **_kwargs: statuses.append(status))

    processor.JobProcessor(object(), ComfyClient(), logger_instance=logging.getLogger("test_worker_input_staging")).process(
        {
            "job_id": "test-job",
            "workflow": "video_minimax_h3",
            "images": {"first_frame": "valid-image-data"},
        }
    )

    assert events == ["check_connection", "upload_image"]
    assert statuses[-1] == "failed"
