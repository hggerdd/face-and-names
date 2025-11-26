"""
Background worker implementation for jobs (ingest, clustering, prediction, repairs).
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

ProgressCallback = Callable[[Dict[str, Any], Dict[str, Any] | None], None]
JobCallable = Callable[[threading.Event, ProgressCallback, Dict[str, Any], Dict[str, Any] | None], Any]


@dataclass
class JobRecord:
    """Represents a running or completed job."""

    id: str
    type: str
    priority: str
    payload: Dict[str, Any] | None
    state: str = "queued"  # queued|running|cancelled|completed|failed
    progress: Dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    checkpoint: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    future: Future | None = None


class JobManager:
    """Simple in-process job manager with cancellation, progress, and checkpoints."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def enqueue(
        self,
        job_type: str,
        func: JobCallable,
        payload: Dict[str, Any] | None = None,
        priority: str = "normal",
        checkpoint: Dict[str, Any] | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        record = JobRecord(
            id=job_id, type=job_type, priority=priority, payload=payload, checkpoint=checkpoint or {}
        )
        with self._lock:
            self._jobs[job_id] = record
        record.future = self._executor.submit(self._run_job, record, func)
        return job_id

    def _run_job(self, record: JobRecord, func: JobCallable) -> None:
        record.state = "running"
        record.started_at = time.time()
        try:
            result = func(
                record.cancel_event,
                lambda progress, checkpoint=None: self._update_progress(record.id, progress, checkpoint),
                dict(record.checkpoint),
                record.payload,
            )
            with self._lock:
                if record.cancel_event.is_set():
                    record.state = "cancelled"
                else:
                    record.state = "completed"
                    record.result = result
        except Exception as exc:  # pragma: no cover - safety net
            with self._lock:
                record.state = "failed"
                record.errors.append(str(exc))
        finally:
            record.finished_at = time.time()

    def _update_progress(
        self, job_id: str, progress: Dict[str, Any], checkpoint: Dict[str, Any] | None = None
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            record.progress = progress
            if checkpoint is not None:
                record.checkpoint = checkpoint

    def cancel(self, job_id: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            record.cancel_event.set()
            if record.state == "queued":
                record.state = "cancelled"

    def inspect(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(f"Unknown job {job_id}")
            return {
                "id": record.id,
                "type": record.type,
                "priority": record.priority,
                "state": record.state,
                "progress": dict(record.progress),
                "errors": list(record.errors),
                "checkpoint": dict(record.checkpoint),
                "result": record.result,
                "created_at": record.created_at,
                "started_at": record.started_at,
                "finished_at": record.finished_at,
            }

    def resume(
        self,
        job_id: str,
        func: JobCallable,
        payload: Dict[str, Any] | None = None,
        priority: str = "normal",
    ) -> str:
        """Enqueue a new job using the checkpoint from an existing job."""
        with self._lock:
            record = self._jobs.get(job_id)
            checkpoint = dict(record.checkpoint) if record else {}
        return self.enqueue(job_type=record.type if record else "unknown", func=func, payload=payload, priority=priority, checkpoint=checkpoint)  # type: ignore[arg-type]

    def wait(self, job_id: str, timeout: float | None = None) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            future = record.future if record else None
        if future is None:
            return
        wait([future], timeout=timeout)
