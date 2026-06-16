from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.models.asset import AssetRecord, sanitize_upload_filename
from app.services.path_validator import resolve_storage_path, validate_relative_storage_path


router = APIRouter()


def _clamp_limit(limit: int) -> int:
    if limit <= 0:
        return 1
    if limit <= 100:
        return limit
    return 100


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def create_asset(request: Request, file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Invalid upload filename.")

    try:
        safe_filename = sanitize_upload_filename(file.filename)
        stored_filename = f"{uuid4().hex}_{safe_filename}"
        asset_path = validate_relative_storage_path(
            f"{request.app.state.settings.asset_root}/{stored_filename}"
        )
        destination = resolve_storage_path(
            request.app.state.settings.storage_root,
            asset_path,
        )
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(await file.read())
        record = request.app.state.asset_store.create_asset(
            filename=safe_filename,
            asset_path=asset_path,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid upload filename.") from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Asset upload failed.") from None
    finally:
        await file.close()

    return AssetRecord.model_validate(record).model_dump(mode="json")


@router.get("/assets")
def list_assets(request: Request, offset: int = 0, limit: int = 20) -> dict:
    items, total = request.app.state.asset_store.list_assets(offset=offset, limit=_clamp_limit(limit))
    payload = [AssetRecord.model_validate(item).model_dump(mode="json") for item in items]
    return {
        "items": payload,
        "total": total,
        "offset": offset,
        "limit": _clamp_limit(limit),
    }
