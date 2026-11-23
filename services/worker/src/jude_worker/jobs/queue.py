"""ops.job queue operations of the worker (FN-JOB-02; TD-15, IF-02, DS-17).

Every function is one short transaction on the given connection (it commits). The worker
role needs only SELECT and UPDATE on ops.job (worker_rw).

Fencing: a worker writes heartbeats and outcomes only for rows it still owns
(``worker_id`` matches and ``status = 'running'``). If its lease expired and the reaper
re-queued the job, its late writes match no row and are dropped, so a job never gets two
outcomes.
"""

from dataclasses import dataclass
from typing import Any, Final
import uuid

import psycopg
from psycopg.types.json import Jsonb

LEASE_SECONDS: Final = 60.0  # L (FN-JOB-02)
MAX_ATTEMPTS: Final = 3  # idempotent jobs: at most 3 attempts (FN-JOB-02, EH-JOB)
LEASE_EXPIRED: Final = "JOB_LEASE_EXPIRED"
# Wakes the completion handler in the API (FN-JOB-04); delivered on commit only.
FINISHED_CHANNEL: Final = "jude_job_finished"


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    type: str
    payload: dict[str, Any]
    attempts: int
    idempotent: bool


def claim(
    conn: psycopg.Connection[Any], worker_id: str, lease_s: float = LEASE_SECONDS
) -> ClaimedJob | None:
    """Claim the oldest queued job (FOR UPDATE SKIP LOCKED) and start its lease."""
    with conn.transaction():
        row = conn.execute(
            """
            UPDATE ops.job
               SET status = 'running', attempts = attempts + 1, worker_id = %s,
                   lease_until = now() + make_interval(secs => %s), heartbeat_at = now()
             WHERE id = (SELECT id FROM ops.job WHERE status = 'queued'
                          ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING id, type, payload, attempts, idempotent
            """,
            (worker_id, lease_s),
        ).fetchone()
    if row is None:
        return None
    return ClaimedJob(id=row[0], type=row[1], payload=row[2], attempts=row[3], idempotent=row[4])


def heartbeat(
    conn: psycopg.Connection[Any], job_id: uuid.UUID, worker_id: str, lease_s: float = LEASE_SECONDS
) -> bool:
    """Extend the lease. False means the lease was lost: stop and drop the result."""
    with conn.transaction():
        cur = conn.execute(
            """
            UPDATE ops.job SET lease_until = now() + make_interval(secs => %s), heartbeat_at = now()
             WHERE id = %s AND worker_id = %s AND status = 'running'
            """,
            (lease_s, job_id, worker_id),
        )
    return cur.rowcount == 1


def succeed(
    conn: psycopg.Connection[Any], job_id: uuid.UUID, worker_id: str, result: dict[str, Any]
) -> bool:
    with conn.transaction():
        cur = conn.execute(
            """
            UPDATE ops.job SET status = 'succeeded', result = %s, finished_at = now(),
                               lease_until = NULL
             WHERE id = %s AND worker_id = %s AND status = 'running'
            """,
            (Jsonb(result), job_id, worker_id),
        )
        if cur.rowcount == 1:
            conn.execute("SELECT pg_notify(%s, %s)", (FINISHED_CHANNEL, str(job_id)))
    return cur.rowcount == 1


def fail(
    conn: psycopg.Connection[Any],
    job_id: uuid.UUID,
    worker_id: str,
    error_code: str,
    result: dict[str, Any] | None = None,
) -> bool:
    with conn.transaction():
        cur = conn.execute(
            """
            UPDATE ops.job SET status = 'failed', error_code = %s, result = %s,
                               finished_at = now(), lease_until = NULL
             WHERE id = %s AND worker_id = %s AND status = 'running'
            """,
            (error_code, Jsonb(result) if result is not None else None, job_id, worker_id),
        )
        if cur.rowcount == 1:
            conn.execute("SELECT pg_notify(%s, %s)", (FINISHED_CHANNEL, str(job_id)))
    return cur.rowcount == 1


def retry_or_fail(
    conn: psycopg.Connection[Any], job: ClaimedJob, worker_id: str, error_code: str
) -> str:
    """Infrastructure error: re-queue an idempotent job with attempts left, else fail it."""
    if job.idempotent and job.attempts < MAX_ATTEMPTS:
        with conn.transaction():
            conn.execute(
                """
                UPDATE ops.job SET status = 'queued', worker_id = NULL, lease_until = NULL
                 WHERE id = %s AND worker_id = %s AND status = 'running'
                """,
                (job.id, worker_id),
            )
        return "queued"
    fail(conn, job.id, worker_id, error_code)
    return "failed"


def reap(conn: psycopg.Connection[Any]) -> tuple[int, int]:
    """Expired leases (worker died): idempotent with attempts left -> queued, else failed.

    Returns (re-queued, failed).
    """
    with conn.transaction():
        rows = conn.execute(
            """
            UPDATE ops.job
               SET status = CASE WHEN idempotent AND attempts < %(max)s
                                 THEN 'queued' ELSE 'failed' END,
                   error_code = CASE WHEN idempotent AND attempts < %(max)s
                                     THEN NULL ELSE %(code)s END,
                   finished_at = CASE WHEN idempotent AND attempts < %(max)s
                                      THEN NULL ELSE now() END,
                   worker_id = NULL, lease_until = NULL
             WHERE status = 'running' AND lease_until < now()
            RETURNING status
            """,
            {"max": MAX_ATTEMPTS, "code": LEASE_EXPIRED},
        ).fetchall()
        if any(s == "failed" for (s,) in rows):
            conn.execute("SELECT pg_notify(%s, %s)", (FINISHED_CHANNEL, "reaped"))
    requeued = sum(1 for (s,) in rows if s == "queued")
    return requeued, len(rows) - requeued
