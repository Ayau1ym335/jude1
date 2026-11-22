"""FN-JOB-01 Enqueue job transactionally (TSK-JOB-01-A; TD-15, ADR-007, IF-02, DS-17).

Long or untrusted work is handed to the worker *in the caller's transaction*: the job row is
inserted next to the domain change, so either both commit or neither exists. A rolled-back
request therefore leaves no job (completion criterion), and the worker can never see a job
whose domain change was not committed.

- ``enqueue`` refuses to run outside an open transaction (a programming error: an autocommit
  insert would outlive a later rollback).
- Payload (DS-17, ``job/1``): input artifact SHA-256s, validated params, requested_by,
  idempotency_key, and the request's correlation ID (XC-FND-11) so the worker logs and the
  job result carry it.
- ``pg_notify('jude_job_queued', <type>)`` wakes idle workers (TD-15 LISTEN/NOTIFY, poll
  fallback in TSK-JOB-02-J). Postgres delivers notifications only on COMMIT, so a rollback
  wakes nobody.
- ``idempotent`` comes from the job type (the op registry flag, FN-KRP-04): only idempotent
  types are ever retried by the worker (DS-17).

The API answers such a request with 202 and ``{"job_id": ...}`` (``accepted``).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
from typing import Any, Final
import uuid

from fastapi.responses import JSONResponse
import psycopg
from psycopg import pq
from psycopg.types.json import Jsonb

from jude_platform import correlation

PAYLOAD_SCHEMA: Final = "job/1"
NOTIFY_CHANNEL: Final = "jude_job_queued"
TYPE_RE: Final = re.compile(r"^[a-z][a-z0-9_.]*\.v[0-9]+$")  # same rule as the ops.job CHECK
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
MAX_PARAMS_BYTES: Final = 64 * 1024


@dataclass(frozen=True)
class JobType:
    """A versioned job type and whether the worker may retry it (op registry flag)."""

    name: str
    idempotent: bool

    def __post_init__(self) -> None:
        if not TYPE_RE.fullmatch(self.name):
            raise ValueError(f"job type {self.name!r} must look like 'regenerate.v1'")
        if not isinstance(self.idempotent, bool):
            raise ValueError("idempotent must be a bool")


@dataclass(frozen=True)
class EnqueuedJob:
    job_id: uuid.UUID
    type: str
    correlation_id: str


def build_payload(
    inputs: Sequence[str],
    params: Mapping[str, Any],
    requested_by: uuid.UUID,
    idempotency_key: str | None,
) -> dict[str, Any]:
    """DS-17 payload; validates shapes so the worker never receives a malformed job."""
    bad = [s for s in inputs if not isinstance(s, str) or not SHA256_RE.fullmatch(s)]
    if bad:
        raise ValueError("inputs must be lower-case hex SHA-256 digests")
    try:
        encoded = json.dumps(params, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("params must be finite, JSON-serialisable values") from exc
    if len(encoded.encode()) > MAX_PARAMS_BYTES:
        raise ValueError("params too large")
    if idempotency_key is not None and not (1 <= len(idempotency_key) <= 255):
        raise ValueError("idempotency_key must be 1..255 characters")
    payload = {
        "schema": PAYLOAD_SCHEMA,
        "inputs": list(inputs),
        "params": json.loads(encoded),
        "requested_by": str(requested_by),
        "idempotency_key": idempotency_key,
    }
    return correlation.inject(payload)


def enqueue(
    conn: psycopg.Connection[Any],
    job_type: JobType,
    *,
    inputs: Sequence[str],
    params: Mapping[str, Any],
    requested_by: uuid.UUID,
    idempotency_key: str | None = None,
    case_id: str | None = None,
) -> EnqueuedJob:
    """Insert a queued job in the caller's open transaction and return its id."""
    if conn.info.transaction_status != pq.TransactionStatus.INTRANS:
        raise RuntimeError("enqueue needs an open transaction (insert it with the domain change)")
    payload = build_payload(inputs, params, requested_by, idempotency_key)
    row = conn.execute(
        """
        INSERT INTO ops.job (type, status, payload, idempotent, case_id, requested_by,
                             idempotency_key)
        VALUES (%s, 'queued', %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (job_type.name, Jsonb(payload), job_type.idempotent, case_id, requested_by,
         idempotency_key),
    ).fetchone()  # fmt: skip
    if row is None:  # pragma: no cover - INSERT ... RETURNING always returns the row
        raise RuntimeError("job insert returned no id")
    conn.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, job_type.name))
    return EnqueuedJob(job_id=row[0], type=job_type.name, correlation_id=payload["correlation_id"])


def accepted(job: EnqueuedJob) -> JSONResponse:
    """202 response of a request that queued work (FN-JOB-01 step 2)."""
    return JSONResponse(status_code=202, content={"job_id": str(job.job_id)})
