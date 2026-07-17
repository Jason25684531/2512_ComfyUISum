"""Lazy construction keeps health/admin failures from preventing Flask startup."""
from __future__ import annotations

import uuid
from functools import lru_cache

from shared.config_base import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from shared.job_repository import JobRepository


@lru_cache(maxsize=1)
def job_repository() -> JobRepository:
    return JobRepository(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)


def new_request_id(value: str | None = None) -> str:
    try:
        return str(uuid.UUID(str(value))) if value else str(uuid.uuid4())
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid4())
