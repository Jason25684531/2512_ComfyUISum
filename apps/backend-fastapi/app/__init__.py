from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRA_PATHS = (
    REPO_ROOT,
    REPO_ROOT / "packages" / "workflow_registry",
    REPO_ROOT / "apps" / "worker-v2",
)

for entry in EXTRA_PATHS:
    path_str = str(entry)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
