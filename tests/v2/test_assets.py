from __future__ import annotations


def test_upload_and_list_assets(client, settings) -> None:
    upload = client.post(
        "/api/v1/assets",
        files={"file": ("sample.txt", b"sample", "text/plain")},
    )

    assert upload.status_code == 201
    created = upload.json()
    assert created["filename"] == "sample.txt"
    assert created["asset_path"].startswith("assets/")
    assert "\\" not in created["asset_path"]

    stored_file = settings.storage_root_path / created["asset_path"]
    assert stored_file.is_file()

    listed = client.get("/api/v1/assets?offset=0&limit=10")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["items"][0]["asset_id"] == created["asset_id"]


def test_upload_asset_rejects_invalid_filename(client) -> None:
    response = client.post(
        "/api/v1/assets",
        files={"file": ("../escape.txt", b"sample", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid upload filename."
