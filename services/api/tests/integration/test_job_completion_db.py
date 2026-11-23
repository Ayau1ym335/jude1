"""IT-FN-JOB-04: job completion in the API with its audit event (TSK-JOB-04-J).

Completion criterion: each kernel job outcome produces exactly one audit event. Exercised with
fake kernel results through the real queue: success, deterministic rejection, retryable failure
(three attempts, one outcome), idempotent re-run of the completion.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
import threading
import time
from typing import Any
import uuid

import numpy as np
import psycopg
import pytest

from jude_api.platform import aud, completion
from jude_api.platform.completion import FinishedJob, complete_one
from jude_api.platform.job import JobType, enqueue
from jude_kernel.core import Frame, MeshArrays, OpResult, OpStatus
from jude_worker.jobs.executor import InlineExecutor
from jude_worker.jobs.loop import Worker

pytestmark = pytest.mark.integration

USER = uuid.UUID("00000000-0000-4000-8000-0000000000cc")
REGEN = JobType("regenerate.v1", idempotent=True)
OTHER = JobType("orphan.v1", idempotent=True)


def now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def role_conn(url: str, role: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute(f"SET ROLE {role}")
        c.commit()
        yield c


@pytest.fixture
def url(empty_db_url: str) -> str:
    from jude_api.db.migrate import upgrade

    upgrade(empty_db_url)
    return empty_db_url


def result(status: OpStatus) -> OpResult:
    mesh = MeshArrays.create(np.eye(3), np.array([[0, 1, 2]]), frame=Frame.F_SCAN)
    return OpResult(
        status=status, op_type="test.op", op_version=1,
        outputs={"mesh": mesh} if status is OpStatus.OK else {}, report={},
        reason_code=None if status is OpStatus.OK else "SELF_INTERSECTION_CREATED",
        kernel_version="0.0.0", image_digest="sha256:" + "0" * 64, lib_versions={},
    )  # fmt: skip


def kernel_ok(_: Mapping[str, Any]) -> OpResult:
    return result(OpStatus.OK)


def kernel_rejects(_: Mapping[str, Any]) -> OpResult:
    return result(OpStatus.REJECTED)


def kernel_flaky(_: Mapping[str, Any]) -> OpResult:
    raise ConnectionError("blob store unreachable")


class Regen:
    """Fake completion handler: one audit event per outcome, as a real job type's would be."""

    def __init__(self, current: bool = True, explode: bool = False) -> None:
        self.current, self.explode, self.applied = current, explode, 0

    def inputs_current(self, job: FinishedJob, conn: psycopg.Connection[Any]) -> bool:
        return self.current

    def apply(self, job: FinishedJob, conn: psycopg.Connection[Any]) -> aud.AuditEvent:
        if self.explode:
            raise RuntimeError("handler bug")
        self.applied += 1
        etype = "design.regenerated" if job.status == "succeeded" else "design.regeneration_failed"
        return aud.AuditEvent(
            etype,
            job.requested_by,
            "technician",
            object_type="job",
            object_id=str(job.id),
            summary_after={"error": job.error_code},
        )


def put(url: str, jt: JobType = REGEN) -> uuid.UUID:
    with role_conn(url, "app_rw") as c, c.transaction():
        return enqueue(c, jt, inputs=[], params={}, requested_by=USER).job_id


def run_worker(url: str, kernel: Any, times: int = 1) -> list[str | None]:
    with role_conn(url, "worker_rw") as w:
        worker = Worker(w, "w1", {"regenerate.v1": kernel, "orphan.v1": kernel}, InlineExecutor())
        return [worker.run_once() for _ in range(times)]


def complete(url: str, handlers: Mapping[str, Any]) -> Any:
    with role_conn(url, "app_rw") as c:
        return complete_one(c, handlers, now)


def events(url: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as c:
        return c.execute("SELECT type, object_id FROM audit.audit_event ORDER BY seq").fetchall()


def job(url: str, jid: uuid.UUID) -> tuple[Any, ...]:
    with psycopg.connect(url) as c:
        row = c.execute(
            "SELECT status, completion, completion_attempts, completed_at FROM ops.job"
            " WHERE id = %s",
            (jid,),
        ).fetchone()
        assert row is not None
        return row


@pytest.mark.parametrize(
    ("kernel", "runs", "status", "event"),
    [
        (kernel_ok, 1, "succeeded", "design.regenerated"),
        (kernel_rejects, 1, "failed", "design.regeneration_failed"),
        (kernel_flaky, 3, "failed", "design.regeneration_failed"),  # 3 attempts, one outcome
    ],
)
def test_completion_criterion_one_audit_event_per_kernel_outcome(
    url: str, kernel: Any, runs: int, status: str, event: str
) -> None:
    jid = put(url)
    run_worker(url, kernel, runs)
    handler = Regen()
    assert complete(url, {"regenerate.v1": handler}) == (jid, "applied")
    assert events(url) == [(event, str(jid))]
    assert job(url, jid)[:3] == (status, "applied", 0)
    # idempotent re-run: nothing left to complete, no second event
    assert complete(url, {"regenerate.v1": handler}) is None
    assert events(url) == [(event, str(jid))] and handler.applied == 1


def test_stale_result_is_discarded_without_event(url: str) -> None:
    jid = put(url)
    run_worker(url, kernel_ok)
    assert complete(url, {"regenerate.v1": Regen(current=False)}) == (jid, "superseded_result")
    assert events(url) == []
    assert job(url, jid)[1] == "superseded_result"


def test_failing_handler_rolls_back_and_is_skipped_after_three_tries(url: str) -> None:
    bad, good = put(url), None
    run_worker(url, kernel_ok)
    boom = Regen(explode=True)
    for attempt in range(1, 4):
        assert complete(url, {"regenerate.v1": boom}) == (bad, "handler_error")
        assert events(url) == [] and job(url, bad)[1:3] == (None, attempt)
    good = put(url)
    run_worker(url, kernel_ok)
    assert complete(url, {"regenerate.v1": Regen()}) == (good, "applied")  # queue not blocked
    assert job(url, bad)[1] is None  # still pending, visible for an operator


def test_job_without_handler_stays_pending(url: str) -> None:
    orphan = put(url, OTHER)
    run_worker(url, kernel_ok)
    assert complete(url, {"regenerate.v1": Regen()}) is None
    assert job(url, orphan)[1] is None and events(url) == []


def test_worker_role_cannot_mark_completion(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as w, pytest.raises(psycopg.errors.InsufficientPrivilege):
        w.execute(
            "UPDATE ops.job SET completion = 'applied', completed_at = now() WHERE id = %s", (jid,)
        )


def test_worker_outcome_wakes_the_completion_loop(url: str) -> None:
    jid = put(url)
    handler = Regen()
    stop = threading.Event()

    def connect() -> psycopg.Connection[Any]:
        c = psycopg.connect(url)
        c.execute("SET ROLE app_rw")
        c.commit()
        return c

    t = threading.Thread(
        target=completion.run_forever, args=(connect, {"regenerate.v1": handler}, now, stop)
    )
    t.start()
    try:
        time.sleep(0.5)  # the loop is listening
        run_worker(url, kernel_ok)
        deadline = time.monotonic() + 10
        while job(url, jid)[1] is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert job(url, jid)[1] == "applied" and len(events(url)) == 1
    finally:
        stop.set()
        t.join(10)
