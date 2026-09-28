from datetime import datetime, timezone
from pathlib import Path

from shared.runtime_services import build_job_data


ROOT = Path(__file__).resolve().parents[2]


def test_build_job_data_preserves_the_v2_generate_payload_contract():
    created_at = datetime(2026, 9, 28, 4, 21, 16, 437780, tzinfo=timezone.utc)
    resolution, payload = build_job_data(
        project_root=ROOT,
        data={
            "workflow": "single_image_edit",
            "prompt": "payload parity",
            "seed": 7,
            "model": "turbo_fp8",
            "aspect_ratio": "1:1",
            "batch_size": 1,
            "images": {"input": "staged.png"},
            "audio": "audio.wav",
            "video": "video.mp4",
            "retake_start": 1.0,
            "retake_end": 2.0,
            "extra_params": {"width": 512},
        },
        job_id="8f74745d-e4ba-4e34-8ad5-769032503aaf",
        user_id=None,
        user_label="anonymous",
        created_at=created_at,
        request_id="request-1",
        submitted_at="2026-09-28T04:21:16.437791Z",
    )

    assert resolution.workflow_id == "image_edit"
    assert payload["workflow"] == "image_edit"
    assert payload["workflow_requested"] == "single_image_edit"
    assert payload["workflow_resolution"] == "alias"
    assert payload["schema_version"] == 2
    assert payload["request_id"] == "request-1"
    assert payload["created_at"] == "2026-09-28T04:21:16.437780Z"
    assert payload["submitted_at"] == "2026-09-28T04:21:16.437791Z"
    assert payload["workflow_version"] == "1.0.0"
    assert payload["workflow_category"] == "image"
    assert payload["images"] == {"input": "staged.png"}
    assert payload["audio"] == "audio.wav"
    assert payload["video"] == "video.mp4"
    assert payload["extra_params"] == {"width": 512}
