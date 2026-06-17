from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path

import httpx

from app.models.job import JobPayload
from shared.v2.errors import (
    COMFYUI_OUTPUT_MISSING,
    COMFYUI_TIMEOUT,
    COMFYUI_UNAVAILABLE,
    ENGINE_EXECUTION_FAILED,
    WORKFLOW_BINDING_INVALID,
    WORKFLOW_NOT_FOUND,
)
from shared.v2.output_paths import build_output_relative_path
from shared.v2.path_utils import ensure_storage_layout, resolve_storage_path
from worker.engines.base import EngineAdapter, EngineResult


class ComfyUIEngine(EngineAdapter):
    MODEL_INPUT_KEYS = {"unet_name", "clip_name", "vae_name", "ckpt_name"}

    def __init__(self, *, settings) -> None:
        self.settings = settings
        self.workflow_dir = Path(__file__).resolve().parents[4] / "workflows" / "comfyui"
        ensure_storage_layout(
            self.settings.storage_root,
            asset_root=self.settings.asset_root,
            output_root=self.settings.output_root,
        )

    def execute(self, job_payload: JobPayload) -> EngineResult:
        if job_payload.task_type != "text_to_image":
            return EngineResult(success=False, error_message=ENGINE_EXECUTION_FAILED)

        try:
            workflow, bindings = self._load_workflow_contract(job_payload.task_type)
            prompt_payload = self._apply_bindings(workflow, bindings, job_payload.params)
            prompt_id = self._submit_prompt(prompt_payload)
            if not prompt_id:
                return EngineResult(success=False, error_message=COMFYUI_UNAVAILABLE)

            output_metadata = self._wait_for_output(prompt_id)
            if output_metadata is None:
                return EngineResult(success=False, error_message=COMFYUI_TIMEOUT)
            if output_metadata == "missing":
                return EngineResult(success=False, error_message=COMFYUI_OUTPUT_MISSING)

            image_bytes = self._download_output(output_metadata)
            if image_bytes is None:
                return EngineResult(success=False, error_message=COMFYUI_OUTPUT_MISSING)

            preferred_filename = (
                (bindings.get("output") or {}).get("preferred_filename")
                or "result.png"
            )
            relative_path = build_output_relative_path(
                str(job_payload.job_id),
                preferred_filename,
                output_root=self.settings.output_root,
            )
            destination = resolve_storage_path(self.settings.storage_root, relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image_bytes)
            return EngineResult(success=True, output_path=relative_path)
        except FileNotFoundError:
            return EngineResult(success=False, error_message=WORKFLOW_NOT_FOUND)
        except ValueError:
            return EngineResult(success=False, error_message=WORKFLOW_BINDING_INVALID)
        except httpx.HTTPError:
            return EngineResult(success=False, error_message=COMFYUI_UNAVAILABLE)
        except Exception:
            return EngineResult(success=False, error_message=ENGINE_EXECUTION_FAILED)

    def health_check(self) -> bool:
        try:
            response = httpx.get(
                f"{self.settings.comfyui_base_url.rstrip('/')}/system_stats",
                timeout=3.0,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

    def _load_workflow_contract(self, task_type: str) -> tuple[dict, dict]:
        if task_type != "text_to_image":
            raise FileNotFoundError(task_type)

        bindings_path = self.workflow_dir / "text_to_image.basic.bindings.json"
        if not bindings_path.is_file():
            raise FileNotFoundError(bindings_path)

        bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
        workflow_path = self.workflow_dir / "text_to_image.basic.json"
        configured_workflow_path = bindings.get("workflow_file")
        if configured_workflow_path:
            workflow_path = self.workflow_dir.parents[1] / configured_workflow_path

        if not workflow_path.is_file():
            raise FileNotFoundError(workflow_path)

        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        return workflow, bindings

    def _apply_bindings(self, workflow: dict, bindings: dict, params: dict) -> dict:
        prompt = copy.deepcopy(workflow)
        binding_map = {
            "prompt_binding": ("prompt", True),
            "negative_prompt_binding": ("negative_prompt", False),
            "width_binding": ("width", False),
            "height_binding": ("height", False),
            "seed_binding": ("seed", False),
            "steps_binding": ("steps", False),
            "batch_size_binding": ("batch_size", False),
            "model_binding": ("model", False),
        }

        for binding_key, (param_key, required) in binding_map.items():
            binding = bindings.get(binding_key)
            if binding is None:
                if required:
                    raise ValueError(binding_key)
                continue

            value = params.get(param_key)
            if value in (None, ""):
                continue

            node_id = str(binding.get("node_id", "")).strip()
            input_key = str(binding.get("input_key", "")).strip()
            if not node_id or not input_key:
                raise ValueError(binding_key)

            node = prompt.get(node_id)
            if not isinstance(node, dict):
                raise ValueError(binding_key)
            inputs = node.get("inputs")
            if not isinstance(inputs, dict) or input_key not in inputs:
                raise ValueError(binding_key)

            inputs[input_key] = self._normalize_bound_value(param_key, value)

        self._normalize_model_inputs(prompt)
        return prompt

    @staticmethod
    def _normalize_bound_value(param_key: str, value):
        if param_key == "seed" and isinstance(value, int) and value < 0:
            return random.SystemRandom().randint(0, 2**63 - 1)
        return value

    @classmethod
    def _normalize_model_inputs(cls, prompt: dict) -> None:
        for node in prompt.values():
            if not isinstance(node, dict):
                continue

            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue

            for key in cls.MODEL_INPUT_KEYS:
                value = inputs.get(key)
                if isinstance(value, str) and "/" in value and "\\" not in value:
                    inputs[key] = value.replace("/", "\\")

    def _submit_prompt(self, prompt_payload: dict) -> str | None:
        response = httpx.post(
            f"{self.settings.comfyui_base_url.rstrip('/')}/prompt",
            json={"prompt": prompt_payload},
            timeout=self.settings.comfy_submit_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        prompt_id = payload.get("prompt_id")
        return str(prompt_id) if prompt_id else None

    def _wait_for_output(self, prompt_id: str) -> dict | str | None:
        deadline = time.monotonic() + self.settings.comfy_history_timeout_seconds
        base_url = self.settings.comfyui_base_url.rstrip("/")

        while time.monotonic() < deadline:
            response = httpx.get(
                f"{base_url}/history/{prompt_id}",
                timeout=self.settings.comfy_http_timeout_seconds,
            )
            response.raise_for_status()
            history = response.json()

            image = self._extract_first_image(history, prompt_id)
            if image is not None:
                return image

            if self._history_completed_without_image(history, prompt_id):
                return "missing"

            time.sleep(max(self.settings.comfy_polling_interval_seconds, 0.0))

        return None

    @staticmethod
    def _extract_first_image(history: dict, prompt_id: str) -> dict | None:
        record = history.get(prompt_id)
        if not isinstance(record, dict):
            return None

        outputs = record.get("outputs")
        if not isinstance(outputs, dict):
            return None

        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get("images")
            if not isinstance(images, list):
                continue
            for item in images:
                if isinstance(item, dict) and item.get("filename"):
                    return {
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                    }
        return None

    @staticmethod
    def _history_completed_without_image(history: dict, prompt_id: str) -> bool:
        record = history.get(prompt_id)
        if not isinstance(record, dict):
            return False
        outputs = record.get("outputs")
        return isinstance(outputs, dict) and bool(outputs)

    def _download_output(self, output_metadata: dict) -> bytes | None:
        response = httpx.get(
            f"{self.settings.comfyui_base_url.rstrip('/')}/view",
            params={
                "filename": output_metadata["filename"],
                "subfolder": output_metadata.get("subfolder", ""),
                "type": output_metadata.get("type", "output"),
            },
            timeout=self.settings.comfy_http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content or None
