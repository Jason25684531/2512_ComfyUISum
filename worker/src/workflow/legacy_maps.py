"""Legacy workflow constants kept for backward-compatible parser behavior."""

import os


DEFAULT_UNET_MODEL = os.getenv(
    "DEFAULT_UNET_MODEL",
    "z-image\\z-image-turbo-fp8-e4m3fn.safetensors",
)

ASPECT_RATIO_MAP = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1216, "height": 832},
    "9:16": {"width": 832, "height": 1216},
    "2:3": {"width": 832, "height": 1248},
}
DEFAULT_RESOLUTION = {"width": 1024, "height": 1024}

MODEL_MAP = {
    "turbo_fp8": DEFAULT_UNET_MODEL,
    "z_image_turbo": DEFAULT_UNET_MODEL,
}

WORKFLOW_MAP = {
    "text_to_image": "text_to_image_z_image_turbo_fp8_260720_api.json",
    "face_swap": "face_swap_qwen_2509_260720_api.json",
    "multi_image_blend": "multi_image_blend_qwen_2509_260720_api.json",
    "single_image_edit": "single_image_edit_qwen_2509_260720_api.json",
    "sketch_to_image": "sketch_to_image_qwen_2509_260720_api.json",
    "virtual_human": "InfiniteTalk_IndexTTS_2.json",
    "image_to_video": "Veo3_VideoConnection.json",
}

IMAGE_NODE_MAP = {
    "face_swap": {
        "501": "source",
        "502": "target",
    },
    "multi_image_blend": {
        "78": "source",
        "436": "target",
        "437": "extra",
    },
    "sketch_to_image": {
        "120": "input",
    },
    "single_image_edit": {
        "120": "input",
    },
    "text_to_image": {},
    "virtual_human": {
        "284": "avatar",
    },
    "image_to_video": {
        "6": "shot_0",
    },
}

AUDIO_NODE_MAP = {
    "virtual_human": {
        "node_id": "311",
        "input_key": "audio",
    }
}

