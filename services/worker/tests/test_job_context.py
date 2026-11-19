"""IT-correlation (worker part): payload ID -> worker logs -> job result envelope (XC-FND-11)."""

from collections.abc import Iterator
import io
import json
import logging
from typing import Any

import numpy as np
import pytest

from jude_kernel.core import Frame, MeshArrays, OpResult, OpStatus
from jude_platform import correlation
from jude_platform.logs import configure_logging
from jude_worker.jobs.context import job_context, result_envelope

PERSONAL_PARAM = "Иванова Айгерим 870101300123"


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    configure_logging("worker", distribution="jude-worker", stream=buf)
    yield buf
    logging.getLogger().handlers = []


def _lines(buf: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line]


def _result() -> OpResult:
    mesh = MeshArrays.create(
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
        np.array([[0, 1, 2]], dtype=np.int32),
        frame=Frame.F_SCAN,
    )
    return OpResult(
        status=OpStatus.OK,
        op_type="test.op",
        op_version=1,
        outputs={"out": mesh},
        report={"n": 3},
        reason_code=None,
        kernel_version="0.1.0",
        image_digest="sha256:" + "ab" * 32,
        lib_versions={"numpy": "2.5.4"},
    )


def test_id_flows_from_api_payload_to_result(logs: io.StringIO) -> None:
    with correlation.bound("ui-action-12345678"):  # API request context
        payload = correlation.inject({"params": {"label": PERSONAL_PARAM}})
    with job_context("job-1", "regenerate.v1", payload) as cid:
        assert correlation.current() == cid == "ui-action-12345678"
        envelope = result_envelope(_result(), cid, {"kernel": 12.5})
    assert correlation.current() is None
    assert envelope["correlation_id"] == "ui-action-12345678"
    assert envelope["report"] == {"n": 3} and envelope["output_names"] == ["out"]

    docs = _lines(logs)
    assert [d["event"] for d in docs] == ["job.started", "job.finished"]
    assert all(d["correlation_id"] == "ui-action-12345678" for d in docs)
    assert PERSONAL_PARAM not in logs.getvalue()


def test_failed_job_logs_type_only(logs: io.StringIO) -> None:
    payload = correlation.inject({}, "job-cid-123456789")
    with pytest.raises(ValueError), job_context("job-2", "export.v1", payload):
        raise ValueError(f"bad input {PERSONAL_PARAM}")
    failed = [d for d in _lines(logs) if d["event"] == "job.failed"]
    assert failed and failed[0]["exc_type"] == "builtins.ValueError"
    assert PERSONAL_PARAM not in logs.getvalue()
