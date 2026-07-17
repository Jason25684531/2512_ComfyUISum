"""Bounded read-only observability queries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.job_contracts import ERROR_CODES, ERROR_STAGES, JobStatus, success_rate

MAX_RANGE = timedelta(days=31)
DEFAULT_RANGE = timedelta(days=1)
SORT_COLUMNS = {"submitted_at", "started_at", "completed_at", "execution_ms", "status"}


def parse_filters(args):
    now = datetime.now(timezone.utc)
    def timestamp(name, default):
        value = args.get(name)
        if not value:
            return default
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    start, end = timestamp("from", now - DEFAULT_RANGE), timestamp("to", now)
    if start > end or end - start > MAX_RANGE:
        raise ValueError("time range must be between zero and 31 days")
    status = args.get("status")
    if status and status not in {item.value for item in JobStatus}:
        raise ValueError("invalid status")
    for key, values in (("error_stage", ERROR_STAGES), ("error_code", ERROR_CODES)):
        if args.get(key) and args.get(key) not in values:
            raise ValueError(f"invalid {key}")
    page = max(1, int(args.get("page", 1)))
    requested_size = int(args.get("page_size", 50))
    if requested_size > 200 or requested_size < 1:
        raise ValueError("page_size must be between 1 and 200")
    page_size = requested_size
    sort = args.get("sort", "submitted_at")
    if sort not in SORT_COLUMNS:
        raise ValueError("invalid sort")
    direction = args.get("direction", "desc").lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("invalid direction")
    return start, end, status, page, page_size, sort, direction


class AdminQueries:
    def __init__(self, repository):
        self.repository = repository

    def jobs(self, args):
        start, end, status, page, page_size, sort, direction = parse_filters(args)
        where, values = ["submitted_at >= %s", "submitted_at <= %s"], [start.replace(tzinfo=None), end.replace(tzinfo=None)]
        for query, column in (("status", "status"), ("workflow_id", "workflow_id"), ("workflow_version", "workflow_version"),
                              ("model", "model_name"), ("worker_id", "worker_id"), ("error_stage", "error_stage"), ("error_code", "error_code")):
            if args.get(query):
                where.append(f"{column}=%s"); values.append(args[query])
        clause = " AND ".join(where)
        with self.repository.transaction() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM jobs WHERE {clause}", values)
            total = cursor.fetchone()["total"]
            cursor.execute(f"SELECT * FROM jobs WHERE {clause} ORDER BY {sort} {direction} LIMIT %s OFFSET %s", values + [page_size, (page - 1) * page_size])
            rows = list(cursor.fetchall())
        return {"items": rows, "page": page, "page_size": page_size, "total": total, "output_encoded": False}

    def summary(self, args):
        start, end, *_ = parse_filters(args)
        with self.repository.transaction() as cursor:
            cursor.execute("SELECT status, COUNT(*) AS count FROM jobs WHERE submitted_at BETWEEN %s AND %s GROUP BY status", (start.replace(tzinfo=None), end.replace(tzinfo=None)))
            counts = {row["status"]: row["count"] for row in cursor.fetchall()}
            cursor.execute("SELECT AVG(queue_wait_ms) AS queue_wait_ms, AVG(execution_ms) AS execution_ms FROM jobs WHERE submitted_at BETWEEN %s AND %s", (start.replace(tzinfo=None), end.replace(tzinfo=None)))
            times = cursor.fetchone()
            # MySQL 8 window functions calculate a percentile without fetching all 31d samples.
            cursor.execute("""WITH ranked AS (
              SELECT execution_ms, ROW_NUMBER() OVER (ORDER BY execution_ms) AS rn,
                     COUNT(*) OVER () AS total FROM jobs
              WHERE submitted_at BETWEEN %s AND %s AND execution_ms IS NOT NULL
            ) SELECT MAX(CASE WHEN rn=CEIL(total*.50) THEN execution_ms END) AS p50,
                     MAX(CASE WHEN rn=CEIL(total*.95) THEN execution_ms END) AS p95 FROM ranked""",
                           (start.replace(tzinfo=None), end.replace(tzinfo=None)))
            percentiles = cursor.fetchone()
        return {"counts": counts, "success_rate": success_rate(counts.get("completed", 0), counts.get("failed", 0)), "average_queue_wait_ms": times["queue_wait_ms"], "average_execution_ms": times["execution_ms"], "p50_execution_ms": percentiles["p50"], "p95_execution_ms": percentiles["p95"], "output_encoded": False}

    def timeseries(self, args):
        start, end, *_ = parse_filters(args)
        with self.repository.transaction() as cursor:
            # PyMySQL uses %-formatting for parameters, so DATE_FORMAT tokens
            # must be escaped before the query reaches MySQL.
            cursor.execute("SELECT DATE_FORMAT(submitted_at, '%%Y-%%m-%%d %%H:00:00') AS bucket, status, COUNT(*) AS count FROM jobs WHERE submitted_at BETWEEN %s AND %s GROUP BY bucket, status ORDER BY bucket", (start.replace(tzinfo=None), end.replace(tzinfo=None)))
            return {"items": list(cursor.fetchall()), "output_encoded": False}

    def grouped(self, args, column):
        if column not in {"error_code", "workflow_id", "worker_id"}:
            raise ValueError("invalid grouping")
        start, end, *_ = parse_filters(args)
        with self.repository.transaction() as cursor:
            cursor.execute(f"SELECT COALESCE({column}, 'unknown') AS value, COUNT(*) AS count FROM jobs WHERE submitted_at BETWEEN %s AND %s GROUP BY {column} ORDER BY count DESC LIMIT 50", (start.replace(tzinfo=None), end.replace(tzinfo=None)))
            return {"items": list(cursor.fetchall()), "output_encoded": False}
