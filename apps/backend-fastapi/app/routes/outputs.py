from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.services.path_validator import InvalidStoragePathError
from shared.v2.errors import INVALID_PATH, OUTPUT_NOT_FOUND
from shared.v2.output_paths import build_output_relative_path
from shared.v2.path_utils import resolve_storage_path


router = APIRouter()


def _resolve_output_file_path(request: Request, job_id: str, filename: str):
    settings = request.app.state.settings
    relative_path = build_output_relative_path(job_id, filename, output_root=settings.output_root)
    resolved_path = resolve_storage_path(settings.storage_root, relative_path)
    output_root_path = resolve_storage_path(settings.storage_root, settings.output_root)
    if output_root_path != resolved_path and output_root_path not in resolved_path.parents:
        raise InvalidStoragePathError(INVALID_PATH)
    return resolved_path


@router.api_route("/outputs/{job_id}/{filename}", methods=["GET", "HEAD"], include_in_schema=False)
def serve_output_file(job_id: str, filename: str, request: Request):
    try:
        resolved_path = _resolve_output_file_path(request, job_id, filename)
    except InvalidStoragePathError:
        raise HTTPException(status_code=400, detail=INVALID_PATH) from None

    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail=OUTPUT_NOT_FOUND)

    return FileResponse(resolved_path)
