from __future__ import annotations

import json


def test_enqueued_payload_is_json_and_matches_job_contract(client, fake_queue) -> None:
    response = client.post(
        "/api/v1/jobs",
        json={"task_type": "text_to_video", "params": {"prompt": "demo"}},
    )

    assert response.status_code == 201
    raw_payload = fake_queue.payloads[0]
    parsed = json.loads(raw_payload)

    from app.models.job import JobPayload

    validated = JobPayload.model_validate(parsed)
    assert validated.task_type == "text_to_video"
    assert "user_id" not in parsed
