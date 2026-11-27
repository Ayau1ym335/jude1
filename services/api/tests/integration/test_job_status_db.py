"""IT-FN-JOB-03: polling a job through the API while a real worker moves it (TSK-JOB-03-A).

Completion criterion: status transitions are visible within one poll interval. Each poll reads
the committed row, so the very next GET after a worker commit shows the new status.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any
import uuid

from fastapi.testclient import TestClient
import numpy as np
import psycopg
import pytest

from jude_api.main import create_app
from jude_api.platform import deps
from jude_api.platform.job import JobType, enqueue
from jude_api.platform.job_routes import JOBS_PREFIX
from jude_kernel.core import Frame, MeshArrays, OpResult, OpStatus
from jude_platform import correlation
from jude_worker.jobs import queue
from jude_worker.jobs.executor import InlineExecutor
from jude_worker.jobs.loop import Worker

pytestmark = pytest.mark.integration

OWNER = uuid.UUID("00000000-0000-4000-8000-00000000000a")
OTHER = uuid.UUID("00000000-0000-4000-8000-00000000000b")
CASE = "J-0123ABCD"
REGEN = JobType("regenerate.v1", idempotent=True)


@contextmanager
def role_conn(url: str, role: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(url) as c:
        c.execute(f"SET ROLE {role}")
        c.commit()
        yield c


def ok(_: Mapping[str, Any]) -> OpResult:
    mesh = MeshArrays.create(np.eye(3), np.array([[0, 1, 2]]), frame=Frame.F_SCAN)
    return OpResult(
        status=OpStatus.OK,
        op_type="test.op",
        op_version=1,
        outputs={"mesh": mesh},
        report={"faces": 1},
        reason_code=None,
        kernel_version="0.0.0",
        image_digest="sha256:" + "0" * 64,
        lib_versions={},
    )


def rejected(_: Mapping[str, Any]) -> OpResult:
    return OpResult(
        status=OpStatus.REJECTED,
        op_type="test.op",
        op_version=1,
        outputs={},
        report={},
        reason_code="SELF_INTERSECTION_CREATED",
        kernel_version="0.0.0",
        image_digest="sha256:" + "0" * 64,
        lib_versions={},
    )


@pytest.fixture
def url(migrated_url: str, seed_user: Callable[..., None]) -> Iterator[str]:
    seed_user(migrated_url, OWNER, OTHER)
    with psycopg.connect(migrated_url) as c:
        c.execute(
            """INSERT INTO clinical."case" (case_id, status, created_by) VALUES (%s, 'active', %s)
               ON CONFLICT DO NOTHING""",
            (CASE, OWNER),
        )
    yield migrated_url
    with psycopg.connect(migrated_url) as c:
        c.execute("DELETE FROM ops.job")


def api(url: str, who: uuid.UUID, cases: frozenset[str] = frozenset()) -> TestClient:
    app = create_app(db_check=lambda: None, readiness_checks={})

    def db() -> Iterator[psycopg.Connection[Any]]:
        with role_conn(url, "app_rw") as c:
            yield c

    app.dependency_overrides[deps.db] = db
    app.dependency_overrides[deps.requester] = lambda: deps.Requester(
        user_id=who, role="technician", session_id="0" * 64, ui_session_id=None
    )
    app.dependency_overrides[deps.case_access] = lambda: lambda w, case_id: case_id in cases
    return TestClient(app)


def put(url: str, case_id: str | None = None) -> uuid.UUID:
    with role_conn(url, "app_rw") as c, c.transaction(), correlation.bound("ui-action-11112222"):
        return enqueue(c, REGEN, inputs=[], params={}, requested_by=OWNER, case_id=case_id).job_id


def test_completion_criterion_each_transition_is_visible_on_the_next_poll(url: str) -> None:
    jid = put(url)
    client = api(url, OWNER)
    first = client.get(f"{JOBS_PREFIX}/{jid}")
    assert first.status_code == 200 and first.json()["status"] == "queued"
    assert first.headers["Cache-Control"] == "no-store"
    with role_conn(url, "worker_rw") as w:
        job = queue.claim(w, "w1")
        assert job is not None
        assert client.get(f"{JOBS_PREFIX}/{jid}").json()["status"] == "running"  # next poll
        queue.succeed(w, job.id, "w1", {"ignored": "not an envelope"})
    body = client.get(f"{JOBS_PREFIX}/{jid}").json()
    assert (body["status"], body["attempts"], body["result"]) == ("succeeded", 1, None)
    assert body["finished_at"] is not None


def test_success_shows_the_kernel_summary_and_correlation_id(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as w:
        assert Worker(w, "w1", {"regenerate.v1": ok}, InlineExecutor()).run_once() == "succeeded"
    body = api(url, OWNER).get(f"{JOBS_PREFIX}/{jid}").json()
    assert body["result"] == {
        "op_type": "test.op",
        "op_version": 1,
        "status": "ok",
        "reason_code": None,
        "output_names": ["mesh"],
        "report": {"faces": 1},
    }
    assert body["correlation_id"] == "ui-action-11112222"
    assert body["error_code"] is None and body["message_ru"] is None and body["progress"] is None
    assert body["step"] is None


def test_failed_job_shows_code_and_russian_message(url: str) -> None:
    jid = put(url)
    with role_conn(url, "worker_rw") as w:
        Worker(w, "w1", {"regenerate.v1": rejected}, InlineExecutor()).run_once()
    body = api(url, OWNER).get(f"{JOBS_PREFIX}/{jid}").json()
    assert body["status"] == "failed" and body["error_code"] == "SELF_INTERSECTION_CREATED"
    assert body["message_ru"] and body["result"]["reason_code"] == "SELF_INTERSECTION_CREATED"
    assert body["step"] == "S8"  # IT-FN-UIX-03: the view links to the design step on completion


def test_unknown_and_invisible_jobs_are_indistinguishable_404(url: str) -> None:
    jid = put(url)
    unknown = api(url, OWNER).get(f"{JOBS_PREFIX}/{uuid.uuid4()}")
    stranger = api(url, OTHER).get(f"{JOBS_PREFIX}/{jid}")
    assert unknown.status_code == stranger.status_code == 404
    assert unknown.json()["error"] == stranger.json()["error"] == "NOT_FOUND"
    assert {k: v for k, v in unknown.json().items() if k != "correlation_id"} == {
        k: v for k, v in stranger.json().items() if k != "correlation_id"
    }


def test_case_access_grants_visibility_to_others(url: str) -> None:
    jid = put(url, case_id=CASE)
    assert api(url, OTHER).get(f"{JOBS_PREFIX}/{jid}").status_code == 404
    assert api(url, OTHER, frozenset({CASE})).get(f"{JOBS_PREFIX}/{jid}").status_code == 200
