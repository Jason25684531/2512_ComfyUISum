from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.v2.path_utils import validate_linux_first_path, validate_relative_storage_path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_repo_relative_path(raw_value: str) -> str:
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate.resolve().as_posix()
    return (REPO_ROOT / candidate).resolve().as_posix()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    app_version: str = "0.1.0"
    app_env: str = Field(alias="APP_ENV")
    engine_mode: Literal["mock", "comfyui"] = Field(alias="ENGINE_MODE")
    comfyui_base_url: str = Field(alias="COMFYUI_BASE_URL")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    storage_root: str = Field(alias="STORAGE_ROOT")
    asset_root: str = Field(alias="ASSET_ROOT")
    output_root: str = Field(alias="OUTPUT_ROOT")
    allow_external_api: bool = Field(alias="ALLOW_EXTERNAL_API")
    default_tier: str = Field(alias="DEFAULT_TIER")
    queue_key: str = "studio:v2:jobs"

    @field_validator("storage_root")
    @classmethod
    def validate_storage_root(cls, value: str) -> str:
        validate_linux_first_path(value, key="STORAGE_ROOT")
        return _resolve_repo_relative_path(value)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value

        database_path = value[len(prefix) :]
        if database_path == ":memory:":
            return value
        return f"{prefix}{_resolve_repo_relative_path(database_path)}"

    @field_validator("asset_root", "output_root")
    @classmethod
    def validate_relative_root(cls, value: str, info) -> str:
        validate_linux_first_path(value, key=info.field_name.upper())
        return validate_relative_storage_path(value)

    @property
    def storage_root_path(self) -> Path:
        return Path(self.storage_root).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    selected = os.getenv("STUDIO_V2_ENV_FILE")
    env_file = Path(selected) if selected else REPO_ROOT / ".env.local-wsl"
    return Settings(_env_file=env_file if env_file.exists() else None)
