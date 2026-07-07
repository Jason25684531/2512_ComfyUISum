"""Workflow injection helpers for prompt, media, model, and runtime values."""

import json
import random
from pathlib import Path
from typing import Any, Callable

try:
    from .legacy_maps import (
        ASPECT_RATIO_MAP,
        AUDIO_NODE_MAP,
        DEFAULT_RESOLUTION,
        IMAGE_NODE_MAP,
        MODEL_MAP,
    )
    from .node_utils import (
        safe_log_value,
        safe_print as print,
        set_configured_prompt_value,
        set_node_input_value,
        set_node_prompt_value,
    )
except ImportError:
    from workflow.legacy_maps import (
        ASPECT_RATIO_MAP,
        AUDIO_NODE_MAP,
        DEFAULT_RESOLUTION,
        IMAGE_NODE_MAP,
        MODEL_MAP,
    )
    from workflow.node_utils import (
        safe_log_value,
        safe_print as print,
        set_configured_prompt_value,
        set_node_input_value,
        set_node_prompt_value,
    )


def find_node_by_class(workflow: dict, class_type: str) -> tuple:
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and node_data.get("class_type") == class_type:
            return node_id, node_data
    return None, None


def find_nodes_by_class(workflow: dict, class_type: str) -> list:
    nodes = []
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and node_data.get("class_type") == class_type:
            nodes.append((node_id, node_data))
    return nodes


def apply_prompt_map_if_configured(workflow: dict, workflow_config, prompt: str) -> bool:
    if not prompt:
        return False

    prompt_map_config = getattr(workflow_config, "prompt_map", None)
    if prompt_map_config is None and isinstance(workflow_config, dict):
        prompt_map_config = workflow_config.get("prompt_map", {})
    if not prompt_map_config:
        return False

    for prompt_name, target in prompt_map_config.items():
        if not isinstance(target, dict):
            print(f"[Parser] Warning: prompt_map.{prompt_name} is not a target object")
            continue
        node_id = target.get("node_id")
        input_key = target.get("input_key", "prompt")
        if not node_id:
            print(f"[Parser] Warning: prompt_map.{prompt_name} missing node_id")
            continue
        if set_configured_prompt_value(
            workflow,
            str(node_id),
            input_key,
            prompt,
            f"prompt_map.{prompt_name}",
        ):
            return True

    return False


def apply_model_overrides(workflow: dict, overrides: list[dict], profile: str) -> int:
    applied_count = 0

    for target in overrides:
        node_id = str(target.get("node_id", "")).strip()
        input_key = str(target.get("input_key", "")).strip()
        value = target.get("value")

        if not node_id or not input_key or not isinstance(value, str):
            print(f"[Parser] Skipping invalid model override target for profile {profile!r}")
            continue

        if set_node_input_value(
            workflow,
            node_id,
            input_key,
            value,
            f"Runtime model override ({profile})",
        ):
            applied_count += 1
        else:
            print(f"[Parser] Runtime model override target missing: {node_id}.{input_key}")

    if applied_count:
        print(f"[Parser] Applied {applied_count} runtime model override(s) for profile {profile!r}")

    return applied_count


def _read_workflow_config(config_path: Path, workflow_entry, workflow_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config_data = getattr(workflow_entry, "_config", None) or {}
    workflow_config = {}

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

    if isinstance(config_data, dict):
        workflow_config = config_data.get(workflow_entry.name, {})
        if not workflow_config:
            workflow_config = config_data.get(workflow_name, {})

    return config_data if isinstance(config_data, dict) else {}, workflow_config


def apply_workflow_injections(
    *,
    workflow: dict,
    workflow_name: str,
    workflow_entry,
    registry,
    config_path: Path,
    runtime_profile: str,
    runtime_model_overrides: list[dict],
    prompt: str,
    prompts: list,
    seed: int,
    aspect_ratio: str,
    model: str,
    batch_size: int,
    image_files: dict,
    audio_file: str,
    video_file: str = None,
    retake_start: float = None,
    retake_end: float = None,
    trim_veo3_workflow: Callable[[dict, dict], dict],
) -> dict:
    config_data = registry._config
    workflow_config = config_data.get(workflow_entry.name, {})
    image_map_config = workflow_entry.image_map

    try:
        config_data, workflow_config = _read_workflow_config(config_path, workflow_entry, workflow_name)
        image_map_config = workflow_entry.image_map
        print(f"[Parser] 載入 config.json for {workflow_name}")
        if image_map_config:
            print(f"[Parser] 偵測到 image_map 設定: {image_map_config}")
    except Exception as e:
        print(f"[Parser] Warning: failed to read config.json; using fallback: {e}")

    if workflow_name == "veo3_long_video":
        workflow = trim_veo3_workflow(workflow, image_files)

    resolution = ASPECT_RATIO_MAP.get(aspect_ratio, DEFAULT_RESOLUTION)
    width = resolution["width"]
    height = resolution["height"]

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    print(f"[Parser] 生成設定: {width}x{height}, Seed: {seed}, Model: {model}")

    if workflow_name == "virtual_human" and prompt:
        text_node_id = workflow_config.get("mapping", {}).get("text_node_id")
        if text_node_id and text_node_id in workflow:
            if set_node_input_value(workflow, text_node_id, "text", prompt, "virtual_human text 注入"):
                print(f"[Parser] virtual_human: text injected into Node {text_node_id}")
                prompt_preview = prompt[:100] if len(prompt) > 100 else prompt
                print(f"[Parser] text preview: {safe_log_value(prompt_preview)}...")
        else:
            tts_nodes = find_nodes_by_class(workflow, "IndexTTS2BaseNode")
            if tts_nodes:
                node_id, _ = tts_nodes[0]
                if set_node_input_value(workflow, node_id, "text", prompt, "virtual_human text fallback"):
                    print(f"[Parser] virtual_human: text injected into IndexTTS2BaseNode {node_id} (fallback)")

    prompt_injected = apply_prompt_map_if_configured(workflow, workflow_entry, prompt)

    positive_nodes = [] if prompt_injected else find_nodes_by_class(workflow, "CLIPTextEncode")
    for node_id, node in positive_nodes:
        title = node.get("_meta", {}).get("title", "")
        if "Positive" in title or "positive" in title.lower():
            set_node_input_value(workflow, node_id, "text", prompt, "CLIPTextEncode Prompt 注入")
            print(f"[Parser] Prompt injected into CLIPTextEncode node {node_id}")
            prompt_injected = True
            break
    else:
        if positive_nodes:
            first_node_id, _ = positive_nodes[0]
            if set_node_input_value(workflow, first_node_id, "text", prompt, "First CLIPTextEncode Prompt 注入"):
                print(f"[Parser] Prompt injected into first CLIPTextEncode node {first_node_id}")
                prompt_injected = True

    if not prompt_injected:
        string_nodes = find_nodes_by_class(workflow, "StringConstantMultiline")
        for node_id, node in string_nodes:
            title = node.get("_meta", {}).get("title", "").lower()
            if "trigger" not in title:
                if set_node_input_value(workflow, node_id, "string", prompt, "StringConstantMultiline Prompt 注入"):
                    print(f"[Parser] Prompt injected into StringConstantMultiline node {node_id}")
                    prompt_injected = True
                    break

    if not prompt_injected:
        qwen_nodes = find_nodes_by_class(workflow, "TextEncodeQwenImageEditPlus")
        for node_id, node in qwen_nodes:
            title = node.get("_meta", {}).get("title", "").lower()
            if "negative" not in title:
                if set_node_input_value(workflow, node_id, "prompt", prompt, "Qwen Prompt 注入"):
                    print(f"[Parser] Prompt injected into TextEncodeQwenImageEditPlus node {node_id}")
                    prompt_injected = True
                    break

        if not prompt_injected and qwen_nodes:
            for node_id, node in qwen_nodes:
                if isinstance(node.get("inputs"), dict) and "prompt" in node["inputs"]:
                    if node["inputs"]["prompt"] or node["inputs"]["prompt"] == "":
                        set_node_input_value(workflow, node_id, "prompt", prompt, "Qwen Prompt fallback 注入")
                        print(f"[Parser] Prompt injected into TextEncodeQwenImageEditPlus node {node_id} (fallback)")
                        prompt_injected = True
                        break

    if not prompt_injected:
        veo_classes = ["VeoVideoGenerator", "Veo3StartEndVideoGenerator"]
        for veo_class in veo_classes:
            veo_nodes = find_nodes_by_class(workflow, veo_class)
            for node_id, _ in veo_nodes:
                if set_node_input_value(workflow, node_id, "prompt", prompt, f"{veo_class} Prompt 注入"):
                    print(f"[Parser] Prompt injected into {veo_class} node {node_id}")
                    prompt_injected = True
                    break
            if prompt_injected:
                break

    if not prompt_injected and config_path.exists():
        workflow_config_for_name = config_data.get(workflow_name, workflow_config)
        mapping = workflow_config_for_name.get("mapping", {})
        prompt_node_id = mapping.get("prompt_node_id")

        if prompt_node_id and prompt_node_id in workflow:
            if set_node_input_value(workflow, prompt_node_id, "prompt", prompt, "Config Prompt 注入"):
                print(f"[Parser] Config prompt injected into Node {prompt_node_id}")
                prompt_injected = True

    if not prompt_injected:
        print("[Parser] Warning: no injectable prompt node found")

    workflow_config_for_segments = config_data.get(workflow_name, workflow_config)
    mapping = workflow_config_for_segments.get("mapping", {})
    prompt_segments_config = mapping.get("prompt_segments", {})

    if prompt_segments_config:
        print(f"[Parser] Found prompt_segments config: {len(prompt_segments_config)} segment(s)")
        injected_count = 0
        skipped_count = 0
        for segment_index_str, node_id_str in prompt_segments_config.items():
            segment_index = int(segment_index_str)

            if node_id_str not in workflow:
                print(f"[Parser] Skipping removed segment node {node_id_str} (segment {segment_index})")
                skipped_count += 1
                continue

            if segment_index < len(prompts) and prompts[segment_index]:
                user_prompt = prompts[segment_index]
            else:
                user_prompt = ""

            prompt_preview = user_prompt[:40] if user_prompt else "(empty)"
            print(f"[Parser] Segment {segment_index}: Node {node_id_str} = {safe_log_value(prompt_preview)}...")

            if set_node_prompt_value(workflow, node_id_str, user_prompt, f"Prompt Segment {segment_index}"):
                print(f"[Parser] Segment prompt injected into Node {node_id_str}")
                injected_count += 1

        print(f"[Parser] prompt segments injected: {injected_count}; skipped: {skipped_count}")

    sampler_id, sampler_node = find_node_by_class(workflow, "KSampler")
    if sampler_node:
        if set_node_input_value(workflow, sampler_id, "seed", seed, "Seed 注入"):
            print(f"[Parser] Seed injected into KSampler node {sampler_id}")

    latent_classes = ["EmptySD3LatentImage", "EmptyLatentImage"]
    for class_type in latent_classes:
        latent_id, latent_node = find_node_by_class(workflow, class_type)
        if latent_node:
            width_ok = set_node_input_value(workflow, latent_id, "width", width, f"{class_type} width 注入")
            height_ok = set_node_input_value(workflow, latent_id, "height", height, f"{class_type} height 注入")
            batch_ok = set_node_input_value(workflow, latent_id, "batch_size", batch_size, f"{class_type} batch_size 注入")
            if width_ok and height_ok and batch_ok:
                print(f"[Parser] Resolution injected: {width}x{height} into {class_type} node {latent_id}")
                break

    model_filename = MODEL_MAP.get(model)
    skip_generic_model_injection = bool(workflow_entry.model_overrides) and not runtime_model_overrides

    if skip_generic_model_injection:
        print(
            f"[Parser] Skipping generic model injection for profile {runtime_profile!r}; "
            "no runtime model override profile matched"
        )

    if model_filename and not skip_generic_model_injection:
        unet_id, unet_node = find_node_by_class(workflow, "UNETLoader")
        if unet_node:
            if set_node_input_value(workflow, unet_id, "unet_name", model_filename, "UNET model 注入"):
                print(f"[Parser] Model {model_filename} injected into UNETLoader node {unet_id}")

        ckpt_id, ckpt_node = find_node_by_class(workflow, "CheckpointLoaderSimple")
        if ckpt_node:
            if set_node_input_value(workflow, ckpt_id, "ckpt_name", model_filename, "Checkpoint model 注入"):
                print(f"[Parser] Model {model_filename} injected into CheckpointLoaderSimple node {ckpt_id}")
    elif not skip_generic_model_injection:
        print(f"[Parser] Warning: unknown model: {model}")

    if runtime_model_overrides:
        apply_model_overrides(workflow, runtime_model_overrides, runtime_profile)

    images_injected = False

    if image_map_config and image_files:
        print(f"[Parser] Using config-driven image injection: {image_map_config}")
        for field_name, node_id in image_map_config.items():
            if field_name in image_files:
                filename = image_files[field_name]
                if set_node_input_value(workflow, node_id, "image", filename, f"Config image 注入 {field_name}"):
                    images_injected = True
            else:
                print(f"[Parser] Warning: missing configured image field: {field_name}")

    if not images_injected:
        node_map = IMAGE_NODE_MAP.get(workflow_name, {})
        if node_map and image_files:
            print(f"[Parser] Using fallback image injection (IMAGE_NODE_MAP): {node_map}")
            for node_id, field_name in node_map.items():
                if field_name in image_files:
                    filename = image_files[field_name]
                    if set_node_input_value(workflow, node_id, "image", filename, f"Fallback image 注入 {field_name}"):
                        print(f"[Parser] Fallback node {node_id}: {filename!r}")
                else:
                    print(f"[Parser] Warning: missing image field: {field_name}")
        elif node_map:
            print(f"[Parser] Warning: workflow expects image fields but none were provided: {list(node_map.values())}")

    audio_injected = False

    audio_node_id = workflow_config.get("mapping", {}).get("audio_node_id")
    if audio_node_id and audio_file:
        if set_node_input_value(workflow, audio_node_id, "audio", audio_file, "Config audio 注入"):
            print(f"[Parser] Config audio injected into Node {audio_node_id}")
            audio_injected = True

    if not audio_injected:
        audio_config = AUDIO_NODE_MAP.get(workflow_name)

        if audio_config and audio_file:
            node_id = audio_config.get("node_id")
            input_key = audio_config.get("input_key", "audio")

            if node_id and set_node_input_value(workflow, node_id, input_key, audio_file, "Fallback audio 注入"):
                print(f"[Parser] Fallback audio injected: {audio_file} into node {node_id}")
            elif node_id:
                print(f"[Parser] Warning: audio target node missing: {node_id}")
        elif audio_config and not audio_file:
            print(f"[Parser] Info: workflow {workflow_name} supports audio injection but no audio file was provided")

    video_node_id = workflow_config.get("mapping", {}).get("video_node_id")
    if video_node_id and video_file:
        if set_node_input_value(workflow, video_node_id, "video", video_file, "Config video 注入"):
            print(f"[Parser] Config video injected into Node {video_node_id}")
    elif video_node_id and not video_file:
        print(f"[Parser] Info: workflow {workflow_name} supports video injection but no video file was provided")

    param_map = workflow_config.get("mapping", {}).get("param_map", {})
    param_values = {"retake_start": retake_start, "retake_end": retake_end}
    for param_name, target in param_map.items():
        param_value = param_values.get(param_name)
        if param_value is None or not target:
            continue
        node_id = target.get("node_id")
        input_key = target.get("input_key", "value")
        if node_id:
            set_node_input_value(workflow, node_id, input_key, float(param_value), f"Config param_map[{param_name}] 注入")

    seed_node_ids = workflow_config.get("mapping", {}).get("seed_node_ids", [])
    for seed_node_id in seed_node_ids:
        set_node_input_value(workflow, seed_node_id, "noise_seed", seed, "Config seed_node_ids 注入")

    return workflow
