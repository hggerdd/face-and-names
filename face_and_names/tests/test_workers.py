from __future__ import annotations

import time

from face_and_names.services.workers import JobManager


def test_job_manager_records_progress_and_result() -> None:
    jm = JobManager(max_workers=1)

    def job(cancel_event, progress_cb, checkpoint, payload):
        progress_cb({"step": 1}, {"cursor": 1})
        return payload["value"]

    job_id = jm.enqueue("demo", job, payload={"value": 42})
    jm.wait(job_id, timeout=2.0)
    info = jm.inspect(job_id)

    assert info["state"] == "completed"
    assert info["progress"]["step"] == 1
    assert info["checkpoint"]["cursor"] == 1
    assert info["result"] == 42


def test_job_manager_cancellation() -> None:
    jm = JobManager(max_workers=1)

    def job(cancel_event, progress_cb, checkpoint, payload):
        for i in range(5):
            if cancel_event.is_set():
                return "stopped"
            progress_cb({"i": i}, {"cursor": i})
            time.sleep(0.01)
        return "done"

    job_id = jm.enqueue("demo", job)
    time.sleep(0.02)
    jm.cancel(job_id)
    jm.wait(job_id, timeout=2.0)
    info = jm.inspect(job_id)

    assert info["state"] in {"cancelled", "completed"}
    assert info["checkpoint"]["cursor"] >= 0
