from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.job import JobPayload


@dataclass(slots=True)
class EngineResult:
    success: bool
    output_path: str | None = None
    error_message: str | None = None


class EngineAdapter(ABC):
    @abstractmethod
    def execute(self, job_payload: JobPayload) -> EngineResult:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> bool:
        raise NotImplementedError
