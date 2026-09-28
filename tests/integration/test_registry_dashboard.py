import os

import pytest
import requests

from pathlib import Path

from shared.workflow_catalog import WorkflowCatalog

BASE = os.getenv("STUDIO_TEST_URL", "http://127.0.0.1:5000")


def test_catalog_workflows_need_no_admin_route_changes():
    root = Path(__file__).resolve().parents[2]
    catalog = WorkflowCatalog.from_paths(root / "ComfyUIworkflow" / "config.json", root / "ComfyUIworkflow")
    assert all(entry.workflow_id and entry.version and entry.observability for entry in catalog.entries.values())
    for workflow_id in ("ltx_i2v", "ltx_flf"):
        entry = catalog.resolve(workflow_id).entry
        assert entry.version == "1.0.0"
        assert entry.observability["output"]["strategy"] == "node_output"
    try:
        response = requests.get(f"{BASE}/api/admin/workflows", timeout=3)
    except requests.RequestException:
        pytest.skip("compose stack is not running")
    assert response.status_code == 200
    # The endpoint groups persisted stable IDs; it does not load workflow JSON.
    assert "items" in response.json()
