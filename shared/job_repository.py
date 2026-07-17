"""Small MySQL repository for durable job state and timelines."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor


class JobRepository:
    def __init__(self, *, host: str, port: int, user: str, password: str, database: str):
        self.connection_args = dict(host=host, port=port, user=user, password=password, database=database,
                                    cursorclass=DictCursor, autocommit=False, charset="utf8mb4")

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        connection = pymysql.connect(**self.connection_args)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION MAX_EXECUTION_TIME=5000")
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_job(self, job: dict[str, Any]) -> None:
        fields = sorted(job)
        with self.transaction() as cursor:
            cursor.execute(f"INSERT INTO jobs ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})", [_database_value(job[field]) for field in fields])

    def create_job_with_dispatch(self, job: dict[str, Any], event: dict[str, Any], payload: dict[str, Any]) -> None:
        """Atomically create the durable summary, submitted event, and dispatch intent."""
        with self.transaction() as cursor:
            fields = sorted(job)
            cursor.execute(f"INSERT INTO jobs ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})", [_database_value(job[field]) for field in fields])
            fields = sorted(event)
            cursor.execute(f"INSERT INTO job_events ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})", [json.dumps(event[field], ensure_ascii=False) if field == "metadata" else _database_value(event[field]) for field in fields])
            now = job["created_at"]
            cursor.execute("INSERT INTO job_dispatches (job_id, payload, created_at, updated_at) VALUES (%s, %s, %s, %s)", (job["job_id"], json.dumps(payload, ensure_ascii=False), _database_value(now), _database_value(now)))

    def create_dispatch(self, job_id: str, payload: dict[str, Any], created_at: Any) -> None:
        with self.transaction() as cursor:
            cursor.execute(
                "INSERT INTO job_dispatches (job_id, payload, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                (job_id, json.dumps(payload, ensure_ascii=False), _database_value(created_at), _database_value(created_at)),
            )

    def pending_dispatches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.transaction() as cursor:
            cursor.execute("SELECT job_id, payload, attempts FROM job_dispatches WHERE state='pending' ORDER BY created_at LIMIT %s", (limit,))
            return [_decode_json_fields(row, fields=("payload",)) for row in cursor.fetchall()]

    def mark_dispatched(self, job_id: str, now: Any, error: str | None = None) -> None:
        with self.transaction() as cursor:
            cursor.execute(
                "UPDATE job_dispatches SET state=%s, attempts=attempts+1, last_error=%s, dispatched_at=%s, updated_at=%s WHERE job_id=%s",
                ("dispatched" if error is None else "pending", error, _database_value(now) if error is None else None, _database_value(now), job_id),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.transaction() as cursor:
            cursor.execute("SELECT * FROM jobs WHERE job_id=%s", (job_id,))
            return cursor.fetchone()

    def transition(self, job_id: str, from_statuses: tuple[str, ...], updates: dict[str, Any]) -> bool:
        if not from_statuses:
            return False
        fields = sorted(updates)
        set_clause = ", ".join(f"{field}=%s" for field in fields) + ", version=version+1"
        placeholders = ", ".join(["%s"] * len(from_statuses))
        with self.transaction() as cursor:
            cursor.execute(f"UPDATE jobs SET {set_clause} WHERE job_id=%s AND status IN ({placeholders})", [_database_value(updates[field]) for field in fields] + [job_id, *from_statuses])
            return cursor.rowcount == 1

    def update_if_status(self, job_id: str, status: str, updates: dict[str, Any]) -> bool:
        fields = sorted(updates)
        if not fields:
            return False
        set_clause = ", ".join(f"{field}=%s" for field in fields) + ", version=version+1"
        with self.transaction() as cursor:
            cursor.execute(f"UPDATE jobs SET {set_clause} WHERE job_id=%s AND status=%s", [_database_value(updates[field]) for field in fields] + [job_id, status])
            return cursor.rowcount == 1

    def add_event(self, event: dict[str, Any]) -> None:
        fields = sorted(event)
        values = [json.dumps(event[field], ensure_ascii=False) if field == "metadata" else _database_value(event[field]) for field in fields]
        with self.transaction() as cursor:
            cursor.execute(f"INSERT IGNORE INTO job_events ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})", values)

    def finalize_completed(self, job_id: str, updates: dict[str, Any], output: dict[str, Any], events: list[dict[str, Any]]) -> bool:
        """Persist the verified output and terminal summary as one transaction."""
        with self.transaction() as cursor:
            fields = sorted(updates)
            set_clause = ", ".join(f"{field}=%s" for field in fields) + ", version=version+1"
            cursor.execute(
                f"UPDATE jobs SET {set_clause} WHERE job_id=%s AND status='running'",
                [_database_value(updates[field]) for field in fields] + [job_id],
            )
            if cursor.rowcount != 1:
                return False
            output_fields = sorted(output)
            cursor.execute(
                f"INSERT INTO job_outputs ({', '.join(output_fields)}) VALUES ({', '.join(['%s'] * len(output_fields))})",
                [json.dumps(output[field], ensure_ascii=False) if field == "metadata" else _database_value(output[field]) for field in output_fields],
            )
            for event in events:
                fields = sorted(event)
                values = [json.dumps(event[field], ensure_ascii=False) if field == "metadata" else _database_value(event[field]) for field in fields]
                cursor.execute(f"INSERT IGNORE INTO job_events ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})", values)
            return True

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        with self.transaction() as cursor:
            cursor.execute("SELECT * FROM job_events WHERE job_id=%s ORDER BY created_at, event_id", (job_id,))
            return [_decode_json_fields(row) for row in cursor.fetchall()]

    def list_outputs(self, job_id: str) -> list[dict[str, Any]]:
        with self.transaction() as cursor:
            cursor.execute("SELECT * FROM job_outputs WHERE job_id=%s ORDER BY output_id", (job_id,))
            return [_decode_json_fields(row) for row in cursor.fetchall()]

    def list_running_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Bounded reconciliation input; terminal jobs are never selected."""
        with self.transaction() as cursor:
            cursor.execute(
                "SELECT * FROM jobs WHERE status='running' ORDER BY started_at LIMIT %s",
                (max(1, min(int(limit), 100)),),
            )
            return cursor.fetchall()


def _database_value(value: Any) -> Any:
    if isinstance(value, str) and value.endswith("Z") and "T" in value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return value


def _decode_json_fields(row: dict[str, Any], fields: tuple[str, ...] = ("metadata",)) -> dict[str, Any]:
    row = dict(row)
    for field in fields:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except ValueError:
                row[field] = {}
    return row
