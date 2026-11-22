"""IT-FN-JOB-01: transactional enqueue against a real Postgres (TSK-JOB-01-A).

Completion criterion: a rolled-back request leaves no job. Runs as the application role
app_rw, the role the API uses for domain writes.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import uuid

import psycopg
import pytest

from jude_api.platform.job import NOTIFY_CHANNEL, JobType, enqueue
from jude_platform import correlation

pytestmark = pytest.mark.integration

REGEN = JobType("regenerate.v1", idempotent=True)
EXPORT = JobType("export.release.v1", idempotent=False)
SHA = "cd" * 32
USER = uuid.UUID("00000000-0000-4000-8000-000000000002")


@contextmanager
def app_conn(url: str) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    with psycopg.connect(url) as c:
        c.execute("SET ROLE app_rw")
        c.commit()
        yield c


def jobs(url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(url) as c:
        return c.execute(
            "SELECT type, status, attempts, idempotent, payload, finished_at "
            "FROM ops.job ORDER BY created_at"
        ).fetchall()


@pytest.fixture
def url(migrated_url: str) -> Iterator[str]:
    yield migrated_url
    with psycopg.connect(migrated_url) as c:
        c.execute("DELETE FROM ops.job")


def test_committed_request_leaves_one_queued_job(url: str) -> None:
    with app_conn(url) as c, c.transaction(), correlation.bound("ui-action-12345678"):
        job = enqueue(
            c, REGEN, inputs=[SHA], params={"k": 1}, requested_by=USER, idempotency_key="idem-1"
        )
    rows = jobs(url)
    assert len(rows) == 1
    jtype, status, attempts, idempotent, payload, finished = rows[0]
    assert (jtype, status, attempts, idempotent, finished) == (
        "regenerate.v1",
        "queued",
        0,
        True,
        None,
    )
    assert isinstance(payload, dict)
    assert payload["inputs"] == [SHA] and payload["params"] == {"k": 1}
    assert payload["correlation_id"] == job.correlation_id == "ui-action-12345678"


def test_rolled_back_request_leaves_no_job(url: str) -> None:
    """Completion criterion of TSK-JOB-01-A: the job dies with its transaction."""
    with app_conn(url) as c:
        with pytest.raises(RuntimeError, match="domain change failed"), c.transaction():
            enqueue(c, EXPORT, inputs=[SHA], params={}, requested_by=USER)
            raise RuntimeError("domain change failed")  # e.g. a gate refuses after the enqueue
        with c.transaction():
            enqueue(c, REGEN, inputs=[], params={}, requested_by=USER)
    assert [r[0] for r in jobs(url)] == ["regenerate.v1"]  # only the committed request


def test_failed_statement_after_enqueue_rolls_the_job_back(url: str) -> None:
    with app_conn(url) as c:
        with pytest.raises(psycopg.errors.Error), c.transaction():
            enqueue(c, REGEN, inputs=[SHA], params={}, requested_by=USER)
            c.execute("SELECT 1/0")
    assert jobs(url) == []


def test_notification_only_after_commit(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as listener:
        listener.execute(f"LISTEN {NOTIFY_CHANNEL}")
        with app_conn(url) as c:
            with pytest.raises(RuntimeError), c.transaction():
                enqueue(c, REGEN, inputs=[], params={}, requested_by=USER)
                raise RuntimeError("rollback")
        assert list(listener.notifies(timeout=0.5, stop_after=1)) == []
        with app_conn(url) as c, c.transaction():
            enqueue(c, EXPORT, inputs=[], params={}, requested_by=USER)
        got = list(listener.notifies(timeout=5, stop_after=1))
        assert [(n.channel, n.payload) for n in got] == [(NOTIFY_CHANNEL, "export.release.v1")]


def test_non_idempotent_type_is_recorded(url: str) -> None:
    with app_conn(url) as c, c.transaction():
        enqueue(c, EXPORT, inputs=[], params={}, requested_by=USER)
    assert jobs(url)[0][3] is False


def test_database_rejects_what_the_service_would_too(url: str) -> None:
    """The ops.job CHECK matches TYPE_RE: a bypassing insert of a bad type fails."""
    with app_conn(url) as c, pytest.raises(psycopg.errors.CheckViolation), c.transaction():
        c.execute(
            "INSERT INTO ops.job (type, status, payload, idempotent, requested_by) "
            "VALUES ('regenerate', 'queued', '{}', true, %s)",
            (USER,),
        )
