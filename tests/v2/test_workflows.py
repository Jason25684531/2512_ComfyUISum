from __future__ import annotations


EXPECTED_TASK_TYPES = {
    "text_to_image",
    "image_edit",
    "multi_image_blend",
    "image_upscale",
    "text_to_video",
    "image_to_video",
    "video_retake",
    "video_upscale",
    "tts",
    "avatar_talk",
}


def test_workflow_catalog_returns_all_mock_manifests(client) -> None:
    response = client.get("/api/v1/workflows")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 10
    assert {item["task_type"] for item in payload["items"]} == EXPECTED_TASK_TYPES
