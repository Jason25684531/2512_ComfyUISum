from __future__ import annotations

def test_valid_output_served(client, settings):
    # Setup dummy file in the proper storage path
    job_id = "test-valid-job"
    filename = "result.png"
    output_dir = settings.storage_root_path / settings.output_root / f"job_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    dummy_file = output_dir / filename
    dummy_file.write_bytes(b"dummy image content")
    
    response = client.get(f"/api/v1/outputs/{job_id}/{filename}")
    assert response.status_code == 200, response.text
    assert response.content == b"dummy image content"

def test_path_traversal_rejected(client):
    response = client.get("/api/v1/outputs/test-job/%2E%2E")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid output path requested."}

def test_backslash_rejected(client):
    response = client.get("/api/v1/outputs/test-job/foo\\bar.png")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid output path requested."}

def test_windows_path_rejected(client):
    response = client.get("/api/v1/outputs/C:/test/result.png")
    assert response.status_code == 404 # FastAPI route fails matching

def test_job_id_with_colon_rejected(client):
    response = client.get("/api/v1/outputs/C:job_id/result.png")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid output path requested."}

def test_missing_file_returns_404(client):
    response = client.get("/api/v1/outputs/non-existent-job/result.png")
    assert response.status_code == 404
    assert response.json() == {"detail": "Output file not found."}
