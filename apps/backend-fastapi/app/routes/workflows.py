from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/workflows")
def list_workflows(request: Request) -> dict:
    registry = request.app.state.workflow_registry
    return {"items": [manifest.model_dump(mode="json") for manifest in registry.list_all()]}
