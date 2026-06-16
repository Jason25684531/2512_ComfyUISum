from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator
from werkzeug.utils import secure_filename

from shared.v2.path_utils import WINDOWS_DRIVE_PATTERN, validate_relative_storage_path


def sanitize_upload_filename(filename: str) -> str:
    raw = filename.strip()
    if not raw:
        raise ValueError("Filename must not be empty.")
    if "\x00" in raw:
        raise ValueError("Filename must not contain null bytes.")
    if "\\" in raw:
        raise ValueError("Filename must not contain backslashes.")
    if WINDOWS_DRIVE_PATTERN.match(raw):
        raise ValueError("Filename must not use Windows absolute paths.")
    if raw.startswith("//"):
        raise ValueError("Filename must not use UNC paths.")

    posix_path = PurePosixPath(raw)
    if posix_path.is_absolute():
        raise ValueError("Filename must not use absolute paths.")
    if any(part in {"..", "."} for part in posix_path.parts):
        raise ValueError("Filename must not traverse directories.")

    cleaned = secure_filename(escape(raw))
    if not cleaned:
        raise ValueError("Filename must not be empty.")
    return cleaned


class AssetRecord(BaseModel):
    asset_id: UUID = Field(default_factory=uuid4)
    filename: str
    asset_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        return sanitize_upload_filename(value)

    @field_validator("asset_path")
    @classmethod
    def validate_asset_path(cls, value: str) -> str:
        return validate_relative_storage_path(value)
