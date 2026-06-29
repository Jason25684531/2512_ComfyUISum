import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_workflow_catalog():
    module_name = "shared.workflow_catalog"
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def test_workflow_catalog_normalizes_aliases_and_exposes_frontend_metadata():
    workflow_catalog = _load_workflow_catalog()
    catalog = workflow_catalog.WorkflowCatalog.from_paths(
        config_path=PROJECT_ROOT / "ComfyUIworkflow" / "config.json",
        workflow_dir=PROJECT_ROOT / "ComfyUIworkflow",
    )

    image_edit = catalog.resolve("single_image_edit")
    multi_blend = catalog.resolve("multi_blend")

    assert image_edit.workflow_id == "image_edit"
    assert multi_blend.workflow_id == "multi_image_blend"
    assert "single_image_edit" in image_edit.entry.aliases
    assert "multi_blend" in multi_blend.entry.aliases

    frontend_catalog = catalog.frontend_catalog()
    image_edit_meta = next(item for item in frontend_catalog if item["id"] == "image_edit")

    assert image_edit_meta["frontend"]["inputs"] == ["input"]
    assert image_edit_meta["frontend"]["title"]


def test_workflow_catalog_validation_has_no_missing_runtime_files():
    workflow_catalog = _load_workflow_catalog()
    catalog = workflow_catalog.WorkflowCatalog.from_paths(
        config_path=PROJECT_ROOT / "ComfyUIworkflow" / "config.json",
        workflow_dir=PROJECT_ROOT / "ComfyUIworkflow",
    )

    assert catalog.validate() == []
