"""IT-FN-JOB-02: the job contract IF-02 end to end on Postgres (TSK-JOB-02-J).

The API enqueues (FN-JOB-01, role app_rw); the worker claims, leases, heartbeats, retries and
records outcomes (FN-JOB-02, role worker_rw). Completion criterion: killing the worker mid-job
re-queues the job after its lease; the retry yields the same geometry hash.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import hashlib
import os
import subprocess
import sys
import textwrap
import threading
import time
from typing import Any
import uuid

import numpy as np
import psycopg
import pytest

from jude_api.platform.job import JobType, enqueue
from jude_kernel.core import Frame, MeshArrays, OpResult, OpStatus
from jude_kernel.core.jarr import encode_mesh
from jude_platform import correlation
from jude_worker.jobs import queue
from jude_worker.jobs.executor import InlineExecutor
from jude_worker.jobs.loop import Worker

pytestmark = pytest.mark.integration

USER = uuid.UUID("00000000-0000-4000-8000-000000000003")
REGEN = JobType("regenerate.v1", idempotent=True)
RELEASE = JobType("export.release.v1", idempotent=False)


@contextmanager
def role_conn(url: str, role: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute(f"SET ROLE {role}")
        c.commit()
        yield c


def put(url: str, job_type: JobType = REGEN, cid: str = "ui-action-12345678") -> uuid.UUID:
    with role_conn(url, "app_rw") as c, c.transaction(), correlation.bound(cid):
        return enqueue(c, job_type, inputs=[], params={"level": 3}, requested_by=USER).job_id


def row(url: str, job_id: uuid.UUID) -> dict[str, Any]:
    with psycopg.connect(url) as c:
        cols = ("status", "attempts", "error_code", "result", "worker_id", "finished_at")
        r = c.execute(
            "SELECT status, attempts, error_code, result, worker_id, finished_at "
            "FROM ops.job WHERE id = %s",
            (job_id,),
        ).fetchone()
        assert r is not None
        return dict(zip(cols, r, strict=True))


def sphere_result(payload: Mapping[str, Any]) -> OpResult:
    """Deterministic geometry job: an octahedron sphere; report carries the geometry hash."""
    level = int(payload["params"]["level"])
    v = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    f = [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]]
    verts, faces = np.array(v, dtype=np.float64), np.array(f)
    for _ in range(level):  # midpoint subdivision, normalised (IEEE ops only)
        mids: dict[tuple[int, int], int] = {}
        out = []
        vl = list(verts)
        for a, b, c in faces.tolist():
            ids = []
            for x, y in ((a, b), (b, c), (c, a)):
                k = (min(x, y), max(x, y))
                if k not in mids:
                    p = vl[x] + vl[y]
                    vl.append(p / np.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2]))
                    mids[k] = len(vl) - 1
                ids.append(mids[k])
            ab, bc, ca = ids
            out += [[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]]
        verts, faces = np.array(vl), np.array(out)
    mesh = MeshArrays.create(verts * 75.0, faces, frame=Frame.F_SCAN)
    sha = hashlib.sha256(encode_mesh(mesh)).hexdigest()
    return OpResult(
        status=OpStatus.OK, op_type="test.sphere", op_version=1, outputs={"mesh": mesh},
        report={"geometry_sha256": sha}, reason_code=None, kernel_version="0.0.0",
        image_digest="sha256:" + "0" * 64, lib_versions={},
    )  # fmt: skip


def rejected(_: Mapping[str, Any]) -> OpResult:
    return OpResult(
        status=OpStatus.REJECTED, op_type="test.op", op_version=1, outputs={}, report={},
        reason_code="SELF_INTERSECTION_CREATED", kernel_version="0.0.0",
        image_digest="sha256:" + "0" * 64, lib_versions={},
    )  # fmt: skip


def flaky(_: Mapping[str, Any]) -> OpResult:
    raise ConnectionError("blob store unreachable")


@pytest.fixture
def url(migrated_url: str, seed_user: Callable[..., None]) -> Iterator[str]:
    seed_user(migrated_url, USER)
    yield migrated_url
    with psycopg.connect(migrated_url) as c:
        c.execute("DELETE FROM ops.job")


def worker(
    c: psycopg.Connection[Any], handlers: Mapping[str, Any], lease_s: float = 60.0, wid: str = "w1"
) -> Worker:
    return Worker(c, wid, handlers, InlineExecutor(), lease_s)


def test_success_records_envelope_with_the_api_correlation_id(url: str) -> None:
    jid = put(url, cid="ui-action-87654321")
    with role_conn(url, "worker_rw") as c:
        assert worker(c, {"regenerate.v1": sphere_result}).run_once() == "succeeded"
    r = row(url, jid)
    assert (r["status"], r["attempts"], r["error_code"]) == ("succeeded", 1, None)
    assert r["result"]["correlation_id"] == "ui-action-87654321"  # UI -> API -> job -> result
    assert (
        r["result"]["report"]["geometry_sha256"]
        == sphere_result({"params": {"level": 3}}).report["geometry_sha256"]
    )


def test_kernel_rejection_fails_without_retry(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as c:
        assert worker(c, {"regenerate.v1": rejected}).run_once() == "failed"
        assert worker(c, {"regenerate.v1": rejected}).run_once() is None  # nothing re-queued
    r = row(url, jid)
    assert (r["status"], r["attempts"], r["error_code"]) == (
        "failed",
        1,
        "SELF_INTERSECTION_CREATED",
    )


def test_infrastructure_error_retries_idempotent_up_to_three_attempts(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as c:
        w = worker(c, {"regenerate.v1": flaky})
        assert [w.run_once() for _ in range(4)] == ["queued", "queued", "failed", None]
    r = row(url, jid)
    assert (r["status"], r["attempts"], r["error_code"]) == ("failed", 3, "JOB_HANDLER_ERROR")


def test_non_idempotent_job_is_never_retried(url: str) -> None:
    jid = put(url, RELEASE)
    with role_conn(url, "worker_rw") as c:
        assert worker(c, {"export.release.v1": flaky}).run_once() == "failed"
    assert row(url, jid)["attempts"] == 1


def test_unknown_type_fails(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as c:
        assert worker(c, {}).run_once() == "failed"
    assert row(url, jid)["error_code"] == "JOB_TYPE_UNKNOWN"


def test_skip_locked_claims_do_not_block_or_collide(url: str) -> None:
    a, b = put(url), put(url)
    with psycopg.connect(url) as holder, role_conn(url, "worker_rw") as c:
        holder.execute("SELECT id FROM ops.job WHERE id = %s FOR UPDATE", (a,))  # row a locked
        t0 = time.monotonic()
        got = queue.claim(c, "w2")
        assert got is not None and got.id == b and time.monotonic() - t0 < 2.0
        holder.rollback()
        again = queue.claim(c, "w2")
        assert again is not None and again.id == a


def test_reaper_requeues_expired_idempotent_and_fails_the_rest(url: str) -> None:
    idem, once = put(url), put(url, RELEASE)
    with role_conn(url, "worker_rw") as c:
        assert queue.claim(c, "dead", lease_s=0.2) is not None
        assert queue.claim(c, "dead", lease_s=0.2) is not None
        time.sleep(0.5)
        assert queue.reap(c) == (1, 1)
    assert row(url, idem)["status"] == "queued"
    assert (row(url, once)["status"], row(url, once)["error_code"]) == (
        "failed",
        "JOB_LEASE_EXPIRED",
    )


def test_heartbeat_keeps_the_lease_and_fencing_drops_late_writes(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as c:
        job = queue.claim(c, "slow", lease_s=3.0)  # generous margins: CI hosts can be slow
        assert job is not None
        for _ in range(3):
            time.sleep(0.5)
            assert queue.heartbeat(c, jid, "slow", lease_s=3.0)
            assert queue.reap(c) == (0, 0)
        time.sleep(3.5)  # missed heartbeats: the lease expires
        assert queue.reap(c) == (1, 0)
        other = queue.claim(c, "fresh")
        assert other is not None and other.id == jid and other.attempts == 2
        assert not queue.heartbeat(c, jid, "slow")
        assert not queue.succeed(c, jid, "slow", {"late": True})  # stale owner: dropped
        assert queue.succeed(c, jid, "fresh", {"ok": True})
    assert row(url, jid)["result"] == {"ok": True}


def test_attempts_exhausted_by_crashes_fail_with_lease_expired(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as c:
        for _ in range(3):
            assert queue.claim(c, "crashy", lease_s=0.1) is not None
            time.sleep(0.3)
            queue.reap(c)
    r = row(url, jid)
    assert (r["status"], r["attempts"], r["error_code"]) == ("failed", 3, "JOB_LEASE_EXPIRED")


_KILLABLE_WORKER = textwrap.dedent(
    """
    import sys, threading, time
    import psycopg
    from jude_worker.jobs.executor import InlineExecutor
    from jude_worker.jobs.loop import Worker

    def stuck(payload):
        print("RUNNING", flush=True)
        time.sleep(3600)  # a long job; the test kills the process here

    with psycopg.connect(sys.argv[1]) as c:
        c.execute("SET ROLE worker_rw")
        c.commit()
        Worker(c, "doomed", {"regenerate.v1": stuck}, InlineExecutor(), lease_s=1.5).run_once()
    """
)


def test_completion_criterion_killed_worker_job_requeued_and_retry_same_hash(url: str) -> None:
    jid = put(url)
    reference = sphere_result({"params": {"level": 3}}).report["geometry_sha256"]
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-c", _KILLABLE_WORKER, url],
        stdout=subprocess.PIPE, text=True, env=dict(os.environ),
    )  # fmt: skip
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "RUNNING"
        assert row(url, jid)["status"] == "running"
        proc.kill()  # the worker dies mid-job: no outcome is written
        proc.wait(10)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert (row(url, jid)["status"], row(url, jid)["worker_id"]) == ("running", "doomed")
    with role_conn(url, "worker_rw") as c:
        w = worker(c, {"regenerate.v1": sphere_result}, wid="survivor")
        deadline = time.monotonic() + 10
        status = None
        while status is None and time.monotonic() < deadline:  # lease 1.5 s, then the reaper
            status = w.run_once()
            if status is None:
                time.sleep(0.25)
    r = row(url, jid)
    assert status == "succeeded" and r["status"] == "succeeded" and r["attempts"] == 2
    assert r["result"]["report"]["geometry_sha256"] == reference


def test_run_forever_wakes_on_notify(url: str) -> None:
    stop = threading.Event()
    with role_conn(url, "worker_rw") as c, psycopg.connect(url, autocommit=True) as listen:
        t = threading.Thread(
            target=worker(c, {"regenerate.v1": sphere_result}).run_forever, args=(stop, listen)
        )
        t.start()
        try:
            jid = put(url)
            deadline = time.monotonic() + 10
            while row(url, jid)["status"] != "succeeded" and time.monotonic() < deadline:
                time.sleep(0.05)
            assert row(url, jid)["status"] == "succeeded"
        finally:
            stop.set()
            t.join(10)
