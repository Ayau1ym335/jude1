"""FN-JOB-04 Job completion handler (TSK-JOB-04-J; TD-15, IF-02, FR-120, NFR-07).

Runs in the API (C3): the worker records a job's outcome in ops.job and notifies
``jude_job_finished``; this module turns each finished job into its domain change **and
exactly one audit event, in one transaction** (the worker never writes domain state or audit).

Per job type a ``CompletionHandler`` provides:

- ``inputs_current(job, conn)`` (step 1): are the inputs still current (e.g. the draft
  version unchanged)? If not, the result is discarded: the job is marked
  ``superseded_result``, nothing else changes and no audit event is written (FR-120 logs state
  changes; there is none).
- ``apply(job, conn) -> AuditEvent`` (step 2): write the records / domain state for a succeeded
  or failed job and return the single audit event that describes it. The processor appends it;
  a handler cannot add a second one.

The job is marked ``completed`` in the same transaction (step 3), so an outcome is applied once:
a crash before the commit leaves the job pending, a re-run after it finds nothing to do. A
handler that raises rolls everything back; after ``MAX_COMPLETION_ATTEMPTS`` the job is skipped
and logged rather than blocking the queue.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import logging
import threading
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol
import uuid

import psycopg

from jude_api.platform import aud
from jude_platform import correlation

log = logging.getLogger("jude_api.completion")
FINISHED_CHANNEL: Final = "jude_job_finished"
MAX_COMPLETION_ATTEMPTS: Final = 3
POLL_SECONDS: Final = 1.0


@dataclass(frozen=True)
class FinishedJob:
    id: uuid.UUID
    type: str
    status: Literal["succeeded", "failed"]
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_code: str | None
    requested_by: uuid.UUID
    case_id: str | None


class CompletionHandler(Protocol):
    def inputs_current(self, job: FinishedJob, conn: psycopg.Connection[Any]) -> bool: ...

    def apply(self, job: FinishedJob, conn: psycopg.Connection[Any]) -> aud.AuditEvent: ...


Outcome = Literal["applied", "superseded_result", "handler_error"]

# Job type -> completion handler. Each job type registers its handler with its task (FN-SCN-02,
# FN-DES-03, FN-EXP-02 ...); a finished job without one stays pending and visible.
HANDLERS: Mapping[str, CompletionHandler] = MappingProxyType({})


def complete_one(
    conn: psycopg.Connection[Any],
    handlers: Mapping[str, CompletionHandler],
    now: Callable[[], datetime],
) -> tuple[uuid.UUID, Outcome] | None:
    """Complete the oldest finished, pending job that has a handler; None if there is none."""
    if not handlers:
        return None
    row: tuple[Any, ...] | None = None
    try:
        with conn.transaction():
            row = conn.execute(
                """
                SELECT id, type, status, payload, result, error_code, requested_by, case_id
                  FROM ops.job
                 WHERE status IN ('succeeded', 'failed') AND completed_at IS NULL
                   AND completion_attempts < %s AND type = ANY(%s)
                 ORDER BY finished_at, id
                 LIMIT 1 FOR UPDATE SKIP LOCKED
                """,
                (MAX_COMPLETION_ATTEMPTS, list(handlers)),
            ).fetchone()
            if row is None:
                return None
            job = FinishedJob(*row)
            with correlation.bound(correlation.extract(job.payload)):
                handler = handlers[job.type]
                if not handler.inputs_current(job, conn):
                    outcome: Outcome = "superseded_result"
                else:
                    aud.append(conn, handler.apply(job, conn))  # exactly one event
                    outcome = "applied"
                conn.execute(
                    "UPDATE ops.job SET completion = %s, completed_at = %s WHERE id = %s",
                    (outcome, now(), job.id),
                )
                log.info("job.completed", extra={"job_id": str(job.id), "job_type": job.type,
                                                 "job_status": outcome})  # fmt: skip
            return job.id, outcome
    except Exception:
        if row is None:  # failed before a job was selected: nothing to count
            raise
        log.exception("job.completion_failed", extra={"job_id": str(row[0]), "job_type": row[1]})
        with conn.transaction():
            conn.execute(
                "UPDATE ops.job SET completion_attempts = completion_attempts + 1 WHERE id = %s",
                (row[0],),
            )
        return row[0], "handler_error"


def run_forever(
    connect: Callable[[], psycopg.Connection[Any]],
    handlers: Mapping[str, CompletionHandler],
    now: Callable[[], datetime],
    stop: threading.Event,
) -> None:
    """Process finished jobs until ``stop``: wake on NOTIFY, poll every second as a fallback."""
    with connect() as conn, connect() as listen:
        listen.autocommit = True
        listen.execute(f"LISTEN {FINISHED_CHANNEL}")
        while not stop.is_set():
            if complete_one(conn, handlers, now) is not None:
                continue
            for _ in listen.notifies(timeout=POLL_SECONDS, stop_after=1):
                pass


def run_supervised(
    connect: Callable[[], psycopg.Connection[Any]],
    handlers: Mapping[str, CompletionHandler],
    now: Callable[[], datetime],
    stop: threading.Event,
    backoff_s: float = 5.0,
) -> None:
    """``run_forever`` that survives a lost database: log, wait ``backoff_s``, reconnect."""
    while not stop.is_set():
        try:
            run_forever(connect, handlers, now, stop)
        except Exception:
            log.exception("job.completion_loop_restarting")
            stop.wait(backoff_s)
