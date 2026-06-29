from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def test_frontend_config_bootstraps_runtime_catalog_from_backend():
    config_js = (FRONTEND_DIR / "config.js").read_text(encoding="utf-8")

    assert "/api/runtime-config" in config_js
    assert "normalizeStudioWorkflowId" in config_js
    assert "buildStudioImageToolConfig" in config_js
    assert "buildStudioToolInfo" in config_js


def test_frontend_pages_use_shared_workflow_normalization():
    index_html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    dashboard_html = (FRONTEND_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert "window.normalizeStudioWorkflowId(toolId)" in index_html
    assert "window.normalizeStudioWorkflowId(jobData.workflow)" in index_html
    assert "window.normalizeStudioWorkflowId(toolId)" in dashboard_html
