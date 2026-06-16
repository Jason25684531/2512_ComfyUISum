from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_DOC = REPO_ROOT / "docs" / "architecture-cleanup-inventory.md"
SCAN_REPORT = REPO_ROOT / "reports" / "runtime-reference-scan.txt"


def test_cleanup_inventory_document_exists_and_lists_required_runtime_surfaces() -> None:
    assert INVENTORY_DOC.is_file(), "inventory document must exist"

    content = INVENTORY_DOC.read_text(encoding="utf-8")

    required_sections = [
        "## Runtime Components",
        "## Duplicate Or Overlapping Areas",
        "## Ownership Labels",
        "## Cleanup Review Policy",
    ]
    required_surfaces = [
        "backend/",
        "worker/",
        "apps/backend-fastapi/",
        "apps/worker-v2/",
        "frontend/",
        "ComfyUIworkflow/",
        "ComfyUIworkflow_api/",
        "shared/v2/",
        "storage/",
        "scripts/",
    ]
    required_labels = [
        "keep",
        "legacy-owned",
        "v2-owned",
        "shared-candidate",
        "archive-candidate",
        "delete-later",
        "unknown",
    ]

    for section in required_sections:
        assert section in content
    for surface in required_surfaces:
        assert surface in content
    for label in required_labels:
        assert label in content


def test_runtime_reference_scan_report_exists_and_mentions_key_overlap_areas() -> None:
    assert SCAN_REPORT.is_file(), "scan report must exist"

    content = SCAN_REPORT.read_text(encoding="utf-8")
    assert "apps/backend-fastapi" in content
    assert "apps/worker-v2" in content
    assert "ComfyUIworkflow" in content
    assert "storage/outputs" in content


def test_legacy_critical_files_still_exist() -> None:
    critical_files = [
        REPO_ROOT / "backend" / "src" / "app.py",
        REPO_ROOT / "worker" / "src" / "main.py",
        REPO_ROOT / "frontend" / "index.html",
        REPO_ROOT / "frontend" / "dashboard.html",
    ]

    for path in critical_files:
        assert path.is_file(), f"missing required legacy-critical file: {path}"
