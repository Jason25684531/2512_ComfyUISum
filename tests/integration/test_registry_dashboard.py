import os

import pytest
import requests

from worker.src.workflow_registry import WorkflowRegistry

BASE = os.getenv("STUDIO_TEST_URL", "http://127.0.0.1:5000")


def test_registry_workflows_need_no_admin_route_changes():
    registry = WorkflowRegistry()
    assert all(entry.workflow_id and entry.version and entry.observability for entry in registry.iter_entries())
    for workflow_id in ("ltx_i2v", "ltx_flf"):
        entry = registry.get(workflow_id)
        assert entry.version == "1.0.0"
        assert entry.observability["output"]["strategy"] == "node_output"
    try:
        response = requests.get(f"{BASE}/api/admin/workflows", timeout=3)
    except requests.RequestException:
        pytest.skip("compose stack is not running")
    assert response.status_code == 200
    # The endpoint groups persisted stable IDs; it does not load workflow JSON.
    assert "items" in response.json()
