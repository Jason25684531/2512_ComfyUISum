import os
import platform
import sys
from pathlib import Path
from typing import Any

from shared.workflow_catalog import WorkflowCatalog, can_inject_prompt, find_workflow_node, has_input_key


# 注意：所有歷史別名（multi_blend、single_image_edit、sketch、T2V、FLF …）
# 已統一收斂至 ComfyUIworkflow/config.json 的 ``aliases`` 欄位，並由 WorkflowCatalog
# 的單一 alias 索引解析。此處不再維護獨立的別名表，避免兩處不同步。

_CONFIG_MODULE = sys.modules.get("config")
_CACHED_DEFAULT_PATHS = None
if _CONFIG_MODULE is not None and hasattr(_CONFIG_MODULE, "WORKFLOW_CONFIG_PATH") and hasattr(_CONFIG_MODULE, "WORKFLOW_DIR"):
    _CACHED_DEFAULT_PATHS = (
        Path(_CONFIG_MODULE.WORKFLOW_CONFIG_PATH),
        Path(_CONFIG_MODULE.WORKFLOW_DIR),
    )


def _default_workflow_paths() -> tuple[Path, Path]:
    if _CACHED_DEFAULT_PATHS is not None:
        return _CACHED_DEFAULT_PATHS

    try:
        from .config import WORKFLOW_CONFIG_PATH, WORKFLOW_DIR
    except ImportError:
        from config import WORKFLOW_CONFIG_PATH, WORKFLOW_DIR

    return Path(WORKFLOW_CONFIG_PATH), Path(WORKFLOW_DIR)


class WorkflowRegistry:
    def __init__(self, config_path: Path = None, workflow_dir: Path = None):
        default_config_path, default_workflow_dir = _default_workflow_paths()
        self.config_path = Path(config_path) if config_path is not None else default_config_path
        self.workflow_dir = Path(workflow_dir) if workflow_dir is not None else default_workflow_dir
        self._catalog = WorkflowCatalog.from_paths(self.config_path, self.workflow_dir)
        self._config = self._catalog.raw_config

    def resolve_name(self, workflow_name: str) -> str:
        try:
            return self._catalog.resolve(workflow_name).workflow_id
        except KeyError:
            # 未知 workflow：維持原樣回傳，由下游 get() 觸發既有的錯誤處理路徑。
            return workflow_name

    def get(self, workflow_name: str):
        try:
            resolution = self._catalog.resolve(workflow_name)
        except KeyError:
            resolution = self._catalog.resolve(self.resolve_name(workflow_name))

        return resolution.entry

    def resolve_runtime_profile(self) -> str:
        configured_profile = os.getenv("COMFYUI_RUNTIME_PROFILE", "").strip()
        if configured_profile:
            return configured_profile.lower()

        system_name = platform.system().strip().lower()
        if system_name.startswith("win"):
            return "windows"
        return "linux"

    def get_model_overrides(self, workflow_name: str) -> tuple[str, list[dict[str, Any]]]:
        entry = self.get(workflow_name)
        profile = self.resolve_runtime_profile()
        profile_overrides = entry.model_overrides.get(profile, [])
        if not isinstance(profile_overrides, list):
            return profile, []
        return profile, [item for item in profile_overrides if isinstance(item, dict)]

    def iter_entries(self):
        for workflow_id in self._catalog.entries:
            yield self.get(workflow_id)

    def validate_configured_workflows(self) -> list[str]:
        return self._catalog.validate()
