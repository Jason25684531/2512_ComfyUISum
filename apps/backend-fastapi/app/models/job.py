from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from html import escape
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from shared.v2.path_utils import validate_relative_storage_path


class JobStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobCreateRequest(BaseModel):
    task_type: str
    params: dict = Field(default_factory=dict)
    input_assets: list[str] = Field(default_factory=list)
    priority: int = 0
    session_id: str | None = None
    client_tag: str | None = None

    @field_validator("input_assets")
    @classmethod
    def validate_input_assets(cls, value: list[str]) -> list[str]:
        return [validate_relative_storage_path(item) for item in value]


class JobPayload(BaseModel):
    job_id: UUID = Field(default_factory=uuid4)
    task_type: str
    params: dict = Field(default_factory=dict)
    input_assets: list[str] = Field(default_factory=list)
    priority: int = 0
    session_id: str | None = None
    client_tag: str | None = None
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    output_path: str | None = None
    error_message: str | None = None
    cancel_requested: bool = False

    @field_validator("input_assets")
    @classmethod
    def validate_input_assets(cls, value: list[str]) -> list[str]:
        return [validate_relative_storage_path(item) for item in value]

    @field_validator("output_path")
    @classmethod
    def validate_output_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_relative_storage_path(value)

    @field_validator("error_message")
    @classmethod
    def escape_error_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return escape(value)
