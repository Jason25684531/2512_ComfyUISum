from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WorkflowInputSpec(BaseModel):
    name: str
    type: str


class WorkflowManifest(BaseModel):
    task_type: str
    display_name: str
    description: str
    version: str
    required_inputs: list[WorkflowInputSpec]
    optional_inputs: list[WorkflowInputSpec] = []
    default_params: dict = {}
    output_type: Literal["image", "video", "audio"]
    mock_output_filename: str
