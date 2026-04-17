import importlib
import sys
from pathlib import Path


ENV_KEYS = (
    "COMFYUI_ROOT",
    "COMFYUI_PATH",
    "MODEL_PATH",
    "STORAGE_DIR",
    "STORAGE_INPUT_DIR",
    "STORAGE_OUTPUT_DIR",
    "WORKFLOW_DIR",
    "STUDIO_ENV",
    "DB_PASSWORD",
)


def load_config_base(monkeypatch, tmp_path, **env_vars):
    env_file = tmp_path / "test.env"
    env_file.write_text("DB_PASSWORD=test-password\n", encoding="utf-8")

    monkeypatch.setenv("STUDIO_ENV_FILE", str(env_file))
    for key in ENV_KEYS:
        if key not in env_vars:
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DB_PASSWORD", env_vars.pop("DB_PASSWORD", "test-password"))

    for key, value in env_vars.items():
        monkeypatch.setenv(key, str(value))

    for module_name in ("shared.config_base", "shared"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("shared.config_base")


def test_storage_and_workflow_paths_follow_env_contract(monkeypatch, tmp_path):
    storage_dir = tmp_path / "mnt" / "studio-storage"
    workflow_dir = tmp_path / "workflow-contract"

    config_base = load_config_base(
        monkeypatch,
        tmp_path,
        STORAGE_DIR=storage_dir,
        WORKFLOW_DIR=workflow_dir,
    )

    assert config_base.STORAGE_DIR == storage_dir.resolve()
    assert config_base.STORAGE_INPUT_DIR == (storage_dir / "inputs").resolve()
    assert config_base.STORAGE_OUTPUT_DIR == (storage_dir / "outputs").resolve()
    assert config_base.WORKFLOW_DIR == workflow_dir.resolve()


def test_comfyui_path_alias_sets_root(monkeypatch, tmp_path):
    comfy_root = tmp_path / "gpu-node" / "comfyui"

    config_base = load_config_base(
        monkeypatch,
        tmp_path,
        COMFYUI_PATH=comfy_root,
    )

    assert config_base.COMFYUI_ROOT == comfy_root.resolve()
    assert config_base.COMFYUI_MODELS_DIR == (comfy_root / "models").resolve()


def test_model_path_overrides_comfyui_models_dir(monkeypatch, tmp_path):
    comfy_root = tmp_path / "gpu-node" / "comfyui"
    model_dir = tmp_path / "shared-models"

    config_base = load_config_base(
        monkeypatch,
        tmp_path,
        COMFYUI_PATH=comfy_root,
        MODEL_PATH=model_dir,
    )

    assert config_base.COMFYUI_MODELS_DIR == model_dir.resolve()