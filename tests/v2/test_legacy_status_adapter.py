from __future__ import annotations

from datetime import datetime, timezone
from app.models.job import JobStatus

def test_get_status_queued(client):
    # Setup a dummy job
    store = client.app.state.job_store
    job_id = "test-job-queued"
    now = datetime.now(timezone.utc).isoformat()
    store.create_job({
        "job_id": job_id,
        "task_type": "text_to_image",
        "params": {},
        "status": JobStatus.QUEUED.value,
        "created_at": now,
        "updated_at": now,
    })
    
    response = client.get(f"/api/status/{job_id}")
    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "status": "queued",
        "state": "queued",
        "success": False,
    }

def test_get_status_succeeded_returns_output_url(client):
    store = client.app.state.job_store
    job_id = "test-job-succeeded"
    now = datetime.now(timezone.utc).isoformat()
    store.create_job({
        "job_id": job_id,
        "task_type": "text_to_image",
        "params": {},
        "status": JobStatus.SUCCEEDED.value,
        "created_at": now,
        "updated_at": now,
        "output_path": "outputs/job_test-job-succeeded/result.png"
    })
    
    response = client.get(f"/api/status/{job_id}")
    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "status": "finished",
        "state": "finished",
        "success": True,
        "output_url": f"/api/v1/outputs/{job_id}/result.png",
        "image_url": f"/api/v1/outputs/{job_id}/result.png",
        "image_path": f"/api/v1/outputs/{job_id}/result.png",
        "result_url": f"/api/v1/outputs/{job_id}/result.png",
        "output_path": "outputs/job_test-job-succeeded/result.png",
    }

def test_get_status_failed_canned_error(client):
    store = client.app.state.job_store
    job_id = "test-job-failed"
    now = datetime.now(timezone.utc).isoformat()
    store.create_job({
        "job_id": job_id,
        "task_type": "text_to_image",
        "params": {},
        "status": JobStatus.FAILED.value,
        "created_at": now,
        "updated_at": now,
        "error_message": "Actual internal error message that shouldn't be exposed"
    })
    
    response = client.get(f"/api/status/{job_id}")
    assert response.status_code == 200
    assert response.json() == {
        "job_id": job_id,
        "status": "failed",
        "state": "failed",
        "success": False,
        "error_message": "Actual internal error message that shouldn&#x27;t be exposed",
        "error": "Actual internal error message that shouldn&#x27;t be exposed",
    }

def test_get_status_unknown_job(client):
    response = client.get("/api/status/non-existent-job")
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found."}
