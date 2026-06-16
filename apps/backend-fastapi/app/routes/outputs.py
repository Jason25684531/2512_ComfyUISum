from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.services.path_validator import InvalidStoragePathError
from shared.v2.path_utils import resolve_storage_path


router = APIRouter()

SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_filename_check(filename: str) -> str:
    if ".." in filename or "/" in filename or "\\" in filename or ":" in filename:
        raise InvalidStoragePathError("Invalid output path requested.")
    if not SAFE_FILENAME_PATTERN.fullmatch(filename):
        raise InvalidStoragePathError("Invalid output path requested.")
    return filename


def _safe_job_id_check(job_id: str) -> str:
    if not job_id or ":" in job_id or "\\" in job_id or "/" in job_id or ".." in job_id:
        raise InvalidStoragePathError("Invalid output path requested.")
    return job_id


def _resolve_output_file_path(request: Request, job_id: str, filename: str) -> Path:
    settings = request.app.state.settings
    safe_job_id = _safe_job_id_check(job_id)
    safe_filename = _safe_filename_check(filename)
    relative_path = f"{settings.output_root}/job_{safe_job_id}/{safe_filename}"
    resolved_path = resolve_storage_path(settings.storage_root, relative_path)
    output_root_path = resolve_storage_path(settings.storage_root, settings.output_root)
    if output_root_path != resolved_path and output_root_path not in resolved_path.parents:
        raise InvalidStoragePathError("Invalid output path requested.")
    return resolved_path


@router.get("/outputs/{job_id}/{filename}", include_in_schema=False)
def serve_output_file(job_id: str, filename: str, request: Request):
    try:
        resolved_path = _resolve_output_file_path(request, job_id, filename)
    except InvalidStoragePathError:
        raise HTTPException(status_code=400, detail="Invalid output path requested.") from None

    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found.")

    return FileResponse(resolved_path)
