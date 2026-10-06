"""Worker loop: claim queued rows one at a time, run the registered handler,
record the terminal state. Crash recovery happens through release_stale()
requeueing RUNNING rows whose lock went stale; every mutating write is
conditional on still owning the lease so a reclaimed job is never overwritten
by a zombie worker."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from uuid import UUID, uuid4

from jobs import registry, repository
from jobs.repository import LockLostError

logger = logging.getLogger(__name__)

LEASE_RENEW_SECONDS = 120


def worker_id_default() -> str:
    """One lease owner per process — hostname alone would let two workers on the
    same host claim each other's jobs after a stale reclaim."""
    return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"


def run_once(*, worker_id: str, batch: int = 8) -> int:
    """One claim+execute pass. Returns the number of jobs processed."""
    released = repository.release_stale()
    if released:
        logger.warning("job worker %s requeued %s stale job(s)", worker_id, released)
    processed = 0
    while processed < batch:
        job = repository.claim_next(worker_id=worker_id)
        if job is None:
            break
        _execute(job, worker_id=worker_id)
        processed += 1
    return processed


def run_forever(*, worker_id: str, batch: int = 8, poll_seconds: float = 2.0) -> None:
    logger.info("job worker %s polling every %.1fs", worker_id, poll_seconds)
    while True:
        try:
            processed = run_once(worker_id=worker_id, batch=batch)
        except Exception:
            logger.exception("job worker %s claim pass failed", worker_id)
            time.sleep(poll_seconds)
            continue
        if processed == 0:
            time.sleep(poll_seconds)


def _execute(job: dict[str, object], *, worker_id: str) -> None:
    job_type = str(job["type"])
    spec = registry.spec_for(job_type)
    job_id = job["id"]
    if spec is None:
        repository.fail_or_retry(
            job_id=job_id,
            worker_id=worker_id,
            error={"code": "job_type_unregistered", "detail": job_type},
            attempt=int(job["attempt"]),
            max_attempts=int(job["max_attempts"]),
        )
        return

    repository.renew_lock(job_id=job_id, worker_id=worker_id)

    def report(progress: float, phase: str | None = None) -> None:
        repository.report_progress(
            job_id=job_id,
            worker_id=worker_id,
            progress=max(0.0, min(progress, 99.0)),
            phase=phase,
        )

    context = registry.JobContext(
        job_id=job_id if isinstance(job_id, UUID) else UUID(str(job_id)),
        org_id=UUID(str(job["org_id"])),
        created_by=UUID(str(job["created_by"])) if job.get("created_by") else None,
        attempt=int(job["attempt"]),
        max_attempts=int(job["max_attempts"]),
        payload=job["payload"] if isinstance(job["payload"], dict) else {},
    )
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat,
        args=(context.job_id, worker_id, stop_heartbeat),
        daemon=True,
    )
    heartbeat.start()
    try:
        result = spec.run(context.payload, context, report)
    except registry.JobPermanentError as error:
        repository.fail_permanent(
            job_id=job_id,
            worker_id=worker_id,
            error={"code": "job_permanent_error", "detail": str(error)[:500]},
        )
        logger.warning("job %s (%s) failed permanently", job_id, job_type)
        return
    except LockLostError:
        logger.warning("job %s (%s) lost its lease; result discarded", job_id, job_type)
        return
    except Exception as error:  # noqa: BLE001 — any handler error becomes job error
        logger.exception("job %s (%s) failed on attempt %s", job_id, job_type, job["attempt"])
        try:
            outcome = repository.fail_or_retry(
                job_id=job_id,
                worker_id=worker_id,
                error={
                    "code": "job_handler_error",
                    "detail": f"{type(error).__name__}: {error}"[:500],
                },
                attempt=int(job["attempt"]),
                max_attempts=int(job["max_attempts"]),
            )
            logger.warning("job %s marked %s", job_id, outcome)
        except LockLostError:
            logger.warning("job %s lost its lease before failure write", job_id)
        return
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=5)
    try:
        repository.succeed(job_id=job_id, worker_id=worker_id, result=result)
    except LockLostError:
        logger.warning("job %s (%s) lost its lease; result discarded", job_id, job_type)
        return
    logger.info("job %s (%s) succeeded", job_id, job_type)


def _heartbeat(job_id: UUID, worker_id: str, stop: threading.Event) -> None:
    """Renew the lease while a handler runs so long jobs without progress
    callbacks keep their lock; a reclaimed job stops being renewable."""
    while not stop.wait(LEASE_RENEW_SECONDS):
        try:
            if not repository.renew_lock(job_id=job_id, worker_id=worker_id):
                logger.warning(
                    "job %s lease lost; terminal write will be rejected", job_id
                )
                return
        except Exception:  # noqa: BLE001 — transient DB blips retry on next tick
            logger.exception("job %s lease renewal failed", job_id)
