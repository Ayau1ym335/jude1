"""The worker loop (FN-JOB-02; EH-JOB).

Each iteration: reap expired leases, claim the oldest queued job, run its handler, record the
outcome. Outcome rules (EH-JOB):

| Outcome | Job |
|---|---|
| kernel OK | succeeded, result = job-result/1 envelope (completion handler: TSK-JOB-04-J) |
| kernel REJECTED / FAILED | failed with the kernel reason code; never retried (deterministic) |
| handler exception | idempotent and attempts < 3 -> queued again, else failed JOB_HANDLER_ERROR |
| CPU / memory limit | failed JOB_RESOURCE_LIMIT (no retry) |
| no handler for the type | failed JOB_TYPE_UNKNOWN |
| lease lost while running | nothing written: the reaper / another worker owns the job now |
| worker died (lease expired) | reaper: idempotent, attempts < 3 -> queued; else JOB_LEASE_EXPIRED |
"""

from collections.abc import Mapping
import logging
import threading
from typing import Any, Protocol

import psycopg

from jude_worker.jobs import queue
from jude_worker.jobs.context import job_context
from jude_worker.jobs.executor import Handler, Outcome, Tick

log = logging.getLogger("jude_worker.loop")
POLL_SECONDS = 0.25  # FN-JOB-02: poll at least every 250 ms
HANDLER_ERROR = "JOB_HANDLER_ERROR"
TYPE_UNKNOWN = "JOB_TYPE_UNKNOWN"


class Executor(Protocol):
    def run(
        self, handler: Handler, payload: Mapping[str, Any], correlation_id: str, tick: Tick
    ) -> Outcome: ...


class Worker:
    def __init__(
        self,
        conn: psycopg.Connection[Any],
        worker_id: str,
        handlers: Mapping[str, Handler],
        executor: Executor,
        lease_s: float = queue.LEASE_SECONDS,
    ) -> None:
        self.conn, self.worker_id, self.handlers = conn, worker_id, handlers
        self.executor, self.lease_s = executor, lease_s

    def run_once(self) -> str | None:
        """One iteration; returns the job's resulting status, or None if the queue was empty."""
        requeued, expired = queue.reap(self.conn)
        if requeued or expired:
            log.warning(
                "job.leases_reaped", extra={"component": f"requeued={requeued} failed={expired}"}
            )
        job = queue.claim(self.conn, self.worker_id, self.lease_s)
        if job is None:
            return None
        extra = {"job_id": str(job.id), "job_type": job.type, "attempts": job.attempts}
        with job_context(str(job.id), job.type, job.payload) as cid:
            handler = self.handlers.get(job.type)
            if handler is None:
                queue.fail(self.conn, job.id, self.worker_id, TYPE_UNKNOWN)
                status = "failed"
            else:

                def tick() -> bool:
                    return queue.heartbeat(self.conn, job.id, self.worker_id, self.lease_s)

                status = self._record(job, self.executor.run(handler, job.payload, cid, tick))
            log.info("job.outcome", extra={**extra, "job_status": status})
        return status

    def _record(self, job: queue.ClaimedJob, out: Outcome) -> str:
        if out.kind == "ok":
            assert out.envelope is not None  # noqa: S101 - executor contract
            return (
                "succeeded"
                if queue.succeed(self.conn, job.id, self.worker_id, out.envelope)
                else "lost"
            )
        if out.kind in ("rejected", "failed"):
            code = out.code or HANDLER_ERROR
            return (
                "failed"
                if queue.fail(self.conn, job.id, self.worker_id, code, out.envelope)
                else "lost"
            )
        if out.kind == "resource_limit":
            queue.fail(self.conn, job.id, self.worker_id, "JOB_RESOURCE_LIMIT")
            return "failed"
        if out.kind == "lease_lost":
            return "lost"
        return queue.retry_or_fail(self.conn, job, self.worker_id, HANDLER_ERROR)

    def run_forever(
        self, stop: threading.Event, listen: psycopg.Connection[Any] | None = None
    ) -> None:
        """Loop until ``stop``; wake on NOTIFY jude_job_queued, poll every <= 250 ms anyway."""
        if listen is not None:
            listen.execute("LISTEN jude_job_queued")
        while not stop.is_set():
            if self.run_once() is not None:
                continue
            if listen is not None:
                for _ in listen.notifies(timeout=POLL_SECONDS, stop_after=1):
                    pass
            else:
                stop.wait(POLL_SECONDS)
