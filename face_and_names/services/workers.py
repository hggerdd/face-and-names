"""
Background worker scaffold for jobs (ingest, clustering, prediction, repairs).
"""

from __future__ import annotations


class JobController:
    """Placeholder worker/job controller."""

    def enqueue(self, job_type: str, payload: dict | None = None, priority: str = "normal") -> str:
        raise NotImplementedError

    def cancel(self, job_id: str) -> None:
        raise NotImplementedError

    def inspect(self, job_id: str) -> dict:
        raise NotImplementedError
