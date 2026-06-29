"""Tests for specs/workflow-alias-consolidation/spec.md.

- Backend (WorkflowCatalog) and worker (WorkflowRegistry) resolve the same canonical id.
- Legacy aliases (folded into config.json) still resolve.
- Worker no longer keeps an independent alias map and does not touch catalog._raw_config.
- Public catalog accessor exists; unknown-id path preserved.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# WorkflowRegistry.__init__ eagerly resolves default paths via worker config,
# which imports shared.config_base (requires DB_PASSWORD at import time).
os.environ.setdefault("DB_PASSWORD", "test-password")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = PROJECT_ROOT / "worker" / "src"
for path in (PROJECT_ROOT, WORKER_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

CONFIG_PATH = PROJECT_ROOT / "ComfyUIworkflow" / "config.json"
WORKFLOW_DIR = PROJECT_ROOT / "ComfyUIworkflow"

from shared.workflow_catalog import WorkflowCatalog  # noqa: E402


def _registry():
    module = importlib.import_module("workflow_registry")
    return module.WorkflowRegistry(config_path=CONFIG_PATH, workflow_dir=WORKFLOW_DIR)


def _catalog():
    return WorkflowCatalog.from_paths(CONFIG_PATH, WORKFLOW_DIR)


LEGACY_ALIAS_CASES = [
    ("multi_blend", "multi_image_blend"),
    ("single_image_edit", "image_edit"),
    ("single_edit", "image_edit"),
    ("sketch", "sketch_to_image"),
    ("T2V", "t2v_veo3"),
    ("FLF", "flf_veo3"),
]


@pytest.mark.parametrize("alias,canonical", LEGACY_ALIAS_CASES)
def test_legacy_alias_resolves_through_single_source(alias, canonical):
    catalog = _catalog()
    registry = _registry()
    assert catalog.resolve(alias).workflow_id == canonical
    # Backend and worker agree on the same canonical id
    assert registry.resolve_name(alias) == canonical


def test_worker_has_no_independent_alias_map():
    module = importlib.import_module("workflow_registry")
    assert not hasattr(module, "LEGACY_ALIASES")


def test_public_catalog_accessor_used_instead_of_private_attribute():
    catalog = _catalog()
    # Public accessor exists and returns the config dict
    assert isinstance(catalog.raw_config, dict)
    assert "text_to_image" in catalog.raw_config

    registry = _registry()
    # Registry's _config contract is preserved via the public accessor
    assert registry._config == catalog.raw_config


def test_unknown_workflow_fallback_preserved():
    registry = _registry()
    # resolve_name returns the name unchanged for unknown ids
    assert registry.resolve_name("does_not_exist") == "does_not_exist"
    # get() on a truly unknown id still raises (existing exception path)
    with pytest.raises(KeyError):
        registry.get("does_not_exist")
