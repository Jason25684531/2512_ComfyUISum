from __future__ import annotations

import json

import redis


class QueueUnavailableError(RuntimeError):
    """Raised when the Redis queue cannot accept jobs."""


class RedisQueueClient:
    def __init__(self, *, redis_url: str, queue_key: str) -> None:
        self.redis_url = redis_url
        self.queue_key = queue_key
        self._client: redis.Redis | None = None

    def _client_or_connect(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=1,
                socket_connect_timeout=1,
            )
        return self._client

    def health_check(self) -> bool:
        try:
            return bool(self._client_or_connect().ping())
        except Exception:
            return False

    def enqueue_job(self, payload: str) -> None:
        try:
            json.loads(payload)
            self._client_or_connect().lpush(self.queue_key, payload)
        except Exception as exc:
            raise QueueUnavailableError("queue unavailable") from exc

    def request_cancel(self, job_id: str) -> None:
        try:
            self._client_or_connect().set(f"studio:v2:cancel:{job_id}", "1", ex=3600)
        except Exception as exc:
            raise QueueUnavailableError("queue unavailable") from exc

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
