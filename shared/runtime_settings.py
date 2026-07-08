from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import ClassVar, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config_base import (
    COMFYUI_MODELS_DIR,
    COMFYUI_ROOT,
    JOB_QUEUE,
    JOB_STATUS_EXPIRE_SECONDS,
    PROJECT_ROOT,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    STORAGE_DIR,
    STORAGE_INPUT_DIR,
    STORAGE_OUTPUT_DIR,
    WORKFLOW_CONFIG_PATH,
    WORKFLOW_DIR,
    ServiceEndpoint,
    resolve_path_setting,
    resolve_service_endpoint,
)


V2_JOB_QUEUE_KEY = "studio:v2:jobs"


class InvalidStoragePathError(ValueError):
    """Raised when a storage path violates the repo's linux-first contract."""


@dataclass(frozen=True)
class SharedRuntimeSettings:
    project_root: Path
    redis_host: str
    redis_port: int
    redis_password: str | None
    job_queue: str
    storage_dir: Path
    storage_input_dir: Path
    storage_output_dir: Path
    workflow_dir: Path
    workflow_config_path: Path
    job_status_expire_seconds: int
    comfyui_root: Path
    comfyui_models_dir: Path


@dataclass(frozen=True)
class LegacyComfyRuntimeSettings:
    endpoint: ServiceEndpoint
    input_dir: Path
    output_dir: Path
    models_dir: Path


def validate_linux_first_path(value: str, *, key: str) -> str:
    if "\x00" in value:
        raise InvalidStoragePathError(f"{key} contains a null byte.")

    cleaned = value.strip()
    if not cleaned:
        raise InvalidStoragePathError(f"{key} must not be empty.")
    if "\\" in cleaned:
        raise InvalidStoragePathError(f"{key} must use '/' path separators.")
    return cleaned


def validate_relative_storage_path(value: str) -> str:
    cleaned = validate_linux_first_path(value, key="Storage path")
    parsed = PurePosixPath(cleaned)
    if parsed.is_absolute():
        raise InvalidStoragePathError("Persisted storage paths must remain relative to STORAGE_ROOT.")
    if any(part in {"..", ""} for part in parsed.parts):
        raise InvalidStoragePathError("Persisted storage paths must not escape STORAGE_ROOT.")
    return parsed.as_posix()


def resolve_repo_relative_path(raw_value: str, *, repo_root: str | Path) -> str:
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate.resolve().as_posix()
    return (Path(repo_root).resolve() / candidate).resolve().as_posix()


def resolve_v2_repo_root(anchor: str | Path) -> Path:
    return Path(anchor).resolve().parents[3]


def resolve_v2_env_file(repo_root: Path, *, selected_env_var: str = "STUDIO_V2_ENV_FILE") -> Path | None:
    selected = os.getenv(selected_env_var)
    env_file = Path(selected) if selected else repo_root / ".env.local-wsl"
    return env_file if env_file.exists() else None


def resolve_v2_storage_root(value: str, *, repo_root: Path) -> str:
    validate_linux_first_path(value, key="STORAGE_ROOT")
    return resolve_repo_relative_path(value, repo_root=repo_root)


def resolve_v2_relative_root(value: str, *, field_name: str) -> str:
    validate_linux_first_path(value, key=field_name.upper())
    return validate_relative_storage_path(value)


def resolve_v2_database_url(value: str, *, repo_root: Path) -> str:
    prefix = "sqlite:///"
    if not value.startswith(prefix):
        return value

    database_path = value[len(prefix) :]
    if database_path == ":memory:":
        return value
    return f"{prefix}{resolve_repo_relative_path(database_path, repo_root=repo_root)}"


def resolve_v2_comfyui_base_url(value: str | None = None) -> str:
    if value:
        return value.rstrip("/")
    endpoint = resolve_service_endpoint(
        "COMFYUI_SERVER_URL",
        "COMFY_HOST",
        "COMFY_PORT",
        "127.0.0.1",
        8188,
    )
    return endpoint.http_url


def resolve_v2_redis_url(value: str | None = None) -> str:
    if value:
        return value

    auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    return f"redis://{auth}{REDIS_HOST}:{REDIS_PORT}/0"


def build_shared_runtime_settings() -> SharedRuntimeSettings:
    return SharedRuntimeSettings(
        project_root=PROJECT_ROOT,
        redis_host=REDIS_HOST,
        redis_port=REDIS_PORT,
        redis_password=REDIS_PASSWORD,
        job_queue=JOB_QUEUE,
        storage_dir=STORAGE_DIR,
        storage_input_dir=STORAGE_INPUT_DIR,
        storage_output_dir=STORAGE_OUTPUT_DIR,
        workflow_dir=WORKFLOW_DIR,
        workflow_config_path=WORKFLOW_CONFIG_PATH,
        job_status_expire_seconds=JOB_STATUS_EXPIRE_SECONDS,
        comfyui_root=COMFYUI_ROOT,
        comfyui_models_dir=COMFYUI_MODELS_DIR,
    )


def build_legacy_comfy_runtime_settings(shared_settings: SharedRuntimeSettings) -> LegacyComfyRuntimeSettings:
    endpoint = resolve_service_endpoint(
        "COMFYUI_SERVER_URL",
        "COMFY_HOST",
        "COMFY_PORT",
        "127.0.0.1",
        8188,
    )
    input_dir = resolve_path_setting(
        "COMFYUI_INPUT_DIR",
        shared_settings.comfyui_root / "input",
        shared_settings.project_root,
    )
    output_dir = resolve_path_setting(
        "COMFYUI_OUTPUT_DIR",
        shared_settings.comfyui_root / "output",
        shared_settings.project_root,
    )
    models_dir = resolve_path_setting(
        "STORAGE_MODELS_DIR",
        shared_settings.storage_dir / "models",
        shared_settings.project_root,
    )
    input_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    return LegacyComfyRuntimeSettings(
        endpoint=endpoint,
        input_dir=input_dir,
        output_dir=output_dir,
        models_dir=models_dir,
    )


class V2RuntimeSettings(BaseSettings):
    repo_root: ClassVar[Path] = PROJECT_ROOT

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    app_version: str = "0.1.0"
    app_env: str = Field(alias="APP_ENV")
    engine_mode: Literal["mock", "comfyui"] = Field(alias="ENGINE_MODE")
    comfyui_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("COMFYUI_BASE_URL", "COMFYUI_SERVER_URL"),
    )
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")
    storage_root: str = Field(validation_alias=AliasChoices("STORAGE_ROOT", "STORAGE_DIR"))
    asset_root: str = Field(alias="ASSET_ROOT")
    output_root: str = Field(alias="OUTPUT_ROOT")
    allow_external_api: bool = Field(alias="ALLOW_EXTERNAL_API")
    default_tier: str = Field(alias="DEFAULT_TIER")
    comfy_submit_timeout_seconds: float = Field(default=300.0, alias="COMFY_SUBMIT_TIMEOUT_SECONDS")
    comfy_history_timeout_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("COMFYUI_HISTORY_TIMEOUT_SECONDS", "COMFY_HISTORY_TIMEOUT_SECONDS"),
    )
    comfy_polling_interval_seconds: float = Field(default=1.0, alias="COMFY_POLLING_INTERVAL")
    comfy_http_timeout_seconds: float = Field(default=30.0, alias="COMFY_HTTP_TIMEOUT")
    queue_key: str = V2_JOB_QUEUE_KEY

    @field_validator("comfyui_base_url")
    @classmethod
    def validate_comfyui_base_url(cls, value: str) -> str:
        return resolve_v2_comfyui_base_url(value)

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        return resolve_v2_redis_url(value)

    @field_validator("storage_root")
    @classmethod
    def validate_storage_root(cls, value: str) -> str:
        return resolve_v2_storage_root(value, repo_root=cls.repo_root)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        return resolve_v2_database_url(value, repo_root=cls.repo_root)

    @field_validator("asset_root", "output_root")
    @classmethod
    def validate_relative_root(cls, value: str, info) -> str:
        return resolve_v2_relative_root(value, field_name=info.field_name)

    @property
    def storage_root_path(self) -> Path:
        return Path(self.storage_root).resolve()


__all__ = [
    "LegacyComfyRuntimeSettings",
    "SharedRuntimeSettings",
    "V2RuntimeSettings",
    "build_legacy_comfy_runtime_settings",
    "build_shared_runtime_settings",
    "resolve_repo_relative_path",
    "resolve_v2_comfyui_base_url",
    "resolve_v2_database_url",
    "resolve_v2_env_file",
    "resolve_v2_redis_url",
    "resolve_v2_relative_root",
    "resolve_v2_repo_root",
    "resolve_v2_storage_root",
]
