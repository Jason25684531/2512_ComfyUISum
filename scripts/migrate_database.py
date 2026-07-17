"""Apply additive MySQL migrations once; run from the repository root."""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.config_base import get_env_int, get_env_str


def main() -> int:
    try:
        import pymysql
    except ImportError:
        print("PyMySQL is required; install requirements.txt first")
        return 2
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    paths = sorted(migration_dir.glob("*.sql"))
    connection = pymysql.connect(host=get_env_str("DB_HOST", "localhost"), port=get_env_int("DB_PORT", 3306),
        user=get_env_str("DB_USER", "studio"), password=get_env_str("DB_PASSWORD", ""), database=get_env_str("DB_NAME", "studio"), autocommit=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 30)", ("studio-job-observability-migration",))
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("could not acquire migration lock")
            cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(128) PRIMARY KEY, checksum CHAR(64) NOT NULL, applied_at DATETIME(6) NOT NULL)")
            for path in paths:
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                cursor.execute("SELECT checksum FROM schema_migrations WHERE version=%s", (path.name,))
                row = cursor.fetchone()
                if row:
                    if row[0] != checksum:
                        raise RuntimeError(f"migration checksum mismatch: {path.name}")
                    continue
                for statement in (part.strip() for part in sql.split(";") if part.strip()):
                    cursor.execute(statement)
                cursor.execute("INSERT INTO schema_migrations (version, checksum, applied_at) VALUES (%s, %s, %s)",
                               (path.name, checksum, datetime.now(timezone.utc).replace(tzinfo=None)))
                print(f"applied {path.name}")
        connection.commit()
        print("migrations ready")
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
