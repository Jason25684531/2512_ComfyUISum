"""Workflow resolution, loading, and API-payload construction."""
from __future__ import annotations

from shared.workflow_catalog import WorkflowCatalog, WorkflowResolution

from config import (
    COMFYUI_RUNTIME_PROFILE, WORKFLOW_CONFIG_PATH, WORKFLOW_DIR,
    STUDIOCORE_AZURE_API_KEY, STUDIOCORE_AZURE_ENDPOINT,
)
from workflow.injectors import apply_runtime_credentials, apply_workflow_injections
from workflow.loader import get_workflow_path, load_workflow


def load_workflow_catalog() -> WorkflowCatalog:
    return WorkflowCatalog.from_paths(WORKFLOW_CONFIG_PATH, WORKFLOW_DIR)


def resolve_workflow(workflow_name: str) -> WorkflowResolution:
    return load_workflow_catalog().resolve(workflow_name)


def parse_workflow(
    workflow_name: str = None,
    prompt: str = "",
    prompts: list = None,
    seed: int = -1,
    aspect_ratio: str = "1:1",
    model: str = "turbo_fp8",
    batch_size: int = 1,
    image_files: dict = None,
    audio_file: str = None,
    video_file: str = None,
    video_mode: str = None,
    retake_start: float = None,
    retake_end: float = None,
    extra_params: dict = None,
    **kwargs,
) -> dict:
    """Build a ComfyUI API workflow payload from catalog metadata."""
    if workflow_name is None:
        workflow_name = kwargs.pop("workflow_type", None)
    else:
        kwargs.pop("workflow_type", None)
    if not workflow_name:
        raise TypeError("parse_workflow() missing required workflow_name or workflow_type")

    catalog = load_workflow_catalog()
    workflow_entry = catalog.resolve(workflow_name).entry
    runtime_model_overrides = workflow_entry.model_overrides.get(COMFYUI_RUNTIME_PROFILE, [])
    if not isinstance(runtime_model_overrides, list):
        runtime_model_overrides = []

    workflow = load_workflow(workflow_name)
    merged_extra_params = {}
    if retake_start is not None:
        merged_extra_params["retake_start"] = retake_start
    if retake_end is not None:
        merged_extra_params["retake_end"] = retake_end
    if extra_params:
        merged_extra_params.update(extra_params)

    workflow = apply_workflow_injections(
        workflow=workflow,
        workflow_name=workflow_name,
        workflow_entry=workflow_entry,
        registry=catalog,
        config_path=catalog.config_path,
        runtime_profile=COMFYUI_RUNTIME_PROFILE,
        runtime_model_overrides=[item for item in runtime_model_overrides if isinstance(item, dict)],
        prompt=prompt,
        prompts=prompts or [],
        seed=seed,
        aspect_ratio=aspect_ratio,
        model=model,
        batch_size=batch_size,
        image_files=image_files or {},
        audio_file=audio_file,
        video_file=video_file,
        video_mode=video_mode,
        extra_params=merged_extra_params,
    )
    apply_runtime_credentials(
        workflow,
        workflow_entry.mapping.get("runtime_credentials", {}),
        {
            "STUDIOCORE_AZURE_API_KEY": STUDIOCORE_AZURE_API_KEY,
            "STUDIOCORE_AZURE_ENDPOINT": STUDIOCORE_AZURE_ENDPOINT,
        },
    )
    return workflow


__all__ = [
    "get_workflow_path",
    "load_workflow",
    "load_workflow_catalog",
    "parse_workflow",
    "resolve_workflow",
]
