"""Injection parity checks run before legacy workflow lookup removal."""

import sys
from pathlib import Path

WORKER_SRC = Path(__file__).resolve().parents[2] / "worker" / "src"
sys.path.insert(0, str(WORKER_SRC.parent.parent))
sys.path.insert(0, str(WORKER_SRC))

from workflow.runtime import parse_workflow  # noqa: E402


def test_text_image_prompt_seed_aspect_and_model_injection():
    workflow = parse_workflow(
        workflow_name="text_to_image",
        prompt="catalog parity prompt",
        seed=12345,
        aspect_ratio="16:9",
        model="turbo_fp8",
    )
    assert workflow["33:6"]["inputs"]["text"] == "catalog parity prompt"
    assert workflow["33:3"]["inputs"]["seed"] == 12345
    assert workflow["33:13"]["inputs"]["width"] == 1216
    assert workflow["33:13"]["inputs"]["height"] == 832
    assert workflow["33:16"]["inputs"]["unet_name"].endswith("z-image-turbo-fp8-e4m3fn.safetensors")


def test_image_audio_video_and_extra_parameter_injection():
    image = parse_workflow(
        workflow_name="single_image_edit",
        prompt="edit",
        seed=7,
        image_files={"input": "input.png"},
    )
    assert image["120"]["inputs"]["image"] == "input.png"

    audio = parse_workflow(
        workflow_name="virtual_human",
        prompt="speak",
        seed=7,
        audio_file="audio.wav",
        image_files={"avatar": "avatar.png"},
    )
    assert audio["311"]["inputs"]["audio"] == "audio.wav"
    assert audio["284"]["inputs"]["image"] == "avatar.png"

    video = parse_workflow(
        workflow_name="ltx_retake_v2v",
        prompt="retake",
        seed=7,
        video_file="clip.mp4",
        extra_params={"retake_start": 1.0, "retake_end": 2.0},
    )
    assert video["661"]["inputs"]["value"] == 1.0
    assert video["662"]["inputs"]["value"] == 2.0
