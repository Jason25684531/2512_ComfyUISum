from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from shared.v2.path_utils import validate_relative_storage_path


class _SQLiteStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.database_path = self._parse_sqlite_path(database_url)

    @staticmethod
    def _parse_sqlite_path(database_url: str) -> Path:
        prefix = "sqlite:///"
        if not database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported by the v2 skeleton.")

        db_path = database_url[len(prefix) :]
        if db_path == ":memory:":
            return Path(":memory:")
        return Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        if self.database_path != Path(":memory:"):
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            ":memory:" if self.database_path == Path(":memory:") else str(self.database_path),
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        return connection


class JobStore(_SQLiteStore):
    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_jobs (
                    job_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    input_assets_json TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    session_id TEXT,
                    client_tag TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    output_path TEXT,
                    error_message TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def create_job(self, payload: dict[str, Any]) -> None:
        output_path = payload.get("output_path")
        validated_output_path = None if output_path is None else validate_relative_storage_path(output_path)
        validated_input_assets = [
            validate_relative_storage_path(item)
            for item in payload.get("input_assets", [])
        ]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO v2_jobs (
                    job_id, task_type, params_json, input_assets_json, priority,
                    session_id, client_tag, status, created_at, updated_at,
                    output_path, error_message, cancel_requested
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["job_id"],
                    payload["task_type"],
                    json.dumps(payload.get("params", {}), ensure_ascii=False),
                    json.dumps(validated_input_assets, ensure_ascii=False),
                    payload.get("priority", 0),
                    payload.get("session_id"),
                    payload.get("client_tag"),
                    payload["status"],
                    payload["created_at"],
                    payload["updated_at"],
                    validated_output_path,
                    payload.get("error_message"),
                    1 if payload.get("cancel_requested") else 0,
                ),
            )

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        updated_at: str,
        output_path: str | None = None,
        error_message: str | None = None,
        cancel_requested: bool | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [updated_at]

        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if output_path is not None:
            fields.append("output_path = ?")
            values.append(validate_relative_storage_path(output_path))
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(error_message)
        if cancel_requested is not None:
            fields.append("cancel_requested = ?")
            values.append(1 if cancel_requested else 0)

        values.append(job_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE v2_jobs SET {', '.join(fields)} WHERE job_id = ?",
                values,
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM v2_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def delete_job(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM v2_jobs WHERE job_id = ?", (job_id,))

    def list_jobs(self, *, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM v2_jobs
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) FROM v2_jobs").fetchone()[0]
        return [self._row_to_dict(row) for row in rows], total

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "task_type": row["task_type"],
            "params": json.loads(row["params_json"]),
            "input_assets": json.loads(row["input_assets_json"]),
            "priority": row["priority"],
            "session_id": row["session_id"],
            "client_tag": row["client_tag"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "output_path": row["output_path"],
            "error_message": row["error_message"],
            "cancel_requested": bool(row["cancel_requested"]),
        }


class AssetStore(_SQLiteStore):
    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS v2_assets (
                    asset_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    asset_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_asset(
        self,
        filename: str,
        asset_path: str,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "asset_id": str(uuid4()),
            "filename": filename,
            "asset_path": validate_relative_storage_path(asset_path),
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO v2_assets (
                    asset_id, filename, asset_path, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    record["asset_id"],
                    record["filename"],
                    record["asset_path"],
                    record["created_at"],
                ),
            )
        return record

    def list_assets(self, *, offset: int = 0, limit: int = 100) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM v2_assets
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            total = connection.execute("SELECT COUNT(*) FROM v2_assets").fetchone()[0]
        return [self._row_to_dict(row) for row in rows], total

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "asset_id": row["asset_id"],
            "filename": row["filename"],
            "asset_path": row["asset_path"],
            "created_at": row["created_at"],
        }
