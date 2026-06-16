from __future__ import annotations


LEGACY_STATUS_BY_V2_STATUS = {
    "CREATED": "queued",
    "QUEUED": "queued",
    "RUNNING": "processing",
    "SUCCEEDED": "finished",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}


def map_v2_status_to_legacy(status: str) -> str:
    return LEGACY_STATUS_BY_V2_STATUS.get(str(status), "failed")
