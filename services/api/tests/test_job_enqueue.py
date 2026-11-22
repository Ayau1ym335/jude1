"""UT-FN-JOB-01: job type and payload validation; enqueue refuses to run outside a transaction."""

from types import SimpleNamespace
from typing import Any
import uuid

from psycopg import pq
import pytest

from jude_api.platform.job import EnqueuedJob, JobType, accepted, build_payload, enqueue
from jude_platform import correlation

SHA = "ab" * 32
USER = uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.mark.parametrize("name", ["regenerate", "Regenerate.v1", "regenerate.v", "a b.v1", ".v1"])
def test_bad_job_type_names(name: str) -> None:
    with pytest.raises(ValueError):
        JobType(name, idempotent=True)


def test_payload_shape_and_correlation() -> None:
    with correlation.bound("ui-action-12345678"):
        p = build_payload([SHA], {"radius_mm": 2.5, "z": [1, 2]}, USER, "key-1")
    assert p == {
        "schema": "job/1",
        "inputs": [SHA],
        "params": {"radius_mm": 2.5, "z": [1, 2]},
        "requested_by": str(USER),
        "idempotency_key": "key-1",
        "correlation_id": "ui-action-12345678",
    }
    assert len(build_payload([], {}, USER, None)["correlation_id"]) == 32  # fresh id if none


@pytest.mark.parametrize(
    ("inputs", "params", "key"),
    [
        (["ABC"], {}, None),
        (["ab" * 31], {}, None),
        ([SHA], {"x": float("nan")}, None),
        ([SHA], {"x": object()}, None),
        ([SHA], {"x": "y" * 70_000}, None),
        ([SHA], {}, ""),
    ],
)
def test_payload_rejects_bad_input(
    inputs: list[str], params: dict[str, Any], key: str | None
) -> None:
    with pytest.raises(ValueError):
        build_payload(inputs, params, USER, key)


@pytest.mark.parametrize("status", [pq.TransactionStatus.IDLE, pq.TransactionStatus.INERROR])
def test_enqueue_needs_an_open_transaction(status: pq.TransactionStatus) -> None:
    fake = SimpleNamespace(info=SimpleNamespace(transaction_status=status))
    with pytest.raises(RuntimeError, match="open transaction"):
        enqueue(fake, JobType("regenerate.v1", True), inputs=[], params={}, requested_by=USER)  # type: ignore[arg-type]


def test_accepted_is_202_with_job_id() -> None:
    job = EnqueuedJob(uuid.UUID(int=7), "regenerate.v1", "c" * 32)
    resp = accepted(job)
    assert resp.status_code == 202
    assert resp.body == b'{"job_id":"00000000-0000-0000-0000-000000000007"}'
