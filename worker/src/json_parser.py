"""
Compatibility facade for ComfyUI workflow parsing.

The public worker contract stays here for legacy imports:
- parse_workflow()
- load_workflow()
- get_workflow_path()

Implementation details live in worker/src/workflow/ modules.
"""

import copy
import json

try:
    from .workflow.injectors import apply_workflow_injections
    from .workflow.loader import get_workflow_path, load_workflow
    from .workflow.video_trim import trim_veo3_workflow
    from .workflow_registry import WorkflowRegistry
except ImportError:
    from workflow.injectors import apply_workflow_injections
    from workflow.loader import get_workflow_path, load_workflow
    from workflow.video_trim import trim_veo3_workflow
    from workflow_registry import WorkflowRegistry


__all__ = ["parse_workflow", "load_workflow", "get_workflow_path"]


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
    retake_start: float = None,
    retake_end: float = None,
    extra_params: dict = None,
    **kwargs,
) -> dict:
    """Build a ComfyUI API workflow payload from a configured workflow template."""
    if workflow_name is None:
        workflow_name = kwargs.pop("workflow_type", None)
    else:
        kwargs.pop("workflow_type", None)
    if not workflow_name:
        raise TypeError("parse_workflow() missing required workflow_name or workflow_type")

    registry = WorkflowRegistry()
    workflow_entry = registry.get(workflow_name)
    config_path = registry.config_path
    runtime_profile, runtime_model_overrides = registry.get_model_overrides(workflow_name)

    if image_files is None:
        image_files = {}
    if prompts is None:
        prompts = []

    workflow = copy.deepcopy(load_workflow(workflow_name))

    merged_extra_params = {}
    if retake_start is not None:
        merged_extra_params["retake_start"] = retake_start
    if retake_end is not None:
        merged_extra_params["retake_end"] = retake_end
    if extra_params:
        merged_extra_params.update(extra_params)

    return apply_workflow_injections(
        workflow=workflow,
        workflow_name=workflow_name,
        workflow_entry=workflow_entry,
        registry=registry,
        config_path=config_path,
        runtime_profile=runtime_profile,
        runtime_model_overrides=runtime_model_overrides,
        prompt=prompt,
        prompts=prompts,
        seed=seed,
        aspect_ratio=aspect_ratio,
        model=model,
        batch_size=batch_size,
        image_files=image_files,
        audio_file=audio_file,
        video_file=video_file,
        extra_params=merged_extra_params,
        trim_veo3_workflow=trim_veo3_workflow,
    )


if __name__ == "__main__":
    try:
        workflow = parse_workflow(
            workflow_name="text_to_image",
            prompt="A beautiful sunset over mountains",
            seed=12345,
            aspect_ratio="16:9",
            model="turbo_fp8",
            batch_size=1,
        )
        print("\n[Test] Workflow generated successfully:")
        print(json.dumps(workflow, indent=2, ensure_ascii=False)[:500] + "...")
    except Exception as e:
        print(f"[Test] Error: {e}")
