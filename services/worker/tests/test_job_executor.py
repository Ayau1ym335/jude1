"""UT-FN-JOB-02: executors and outcome mapping (no database)."""

from collections.abc import Mapping
import sys
import time
from typing import Any

import numpy as np
import pytest

from jude_kernel.core import Frame, MeshArrays, OpResult, OpStatus
from jude_worker.jobs.executor import InlineExecutor, Limits, Outcome, outcome_of

linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="fork + setrlimit")


def result(status: OpStatus, code: str | None = None) -> OpResult:
    mesh = MeshArrays.create(np.eye(3), np.array([[0, 1, 2]]), frame=Frame.F_SCAN)
    return OpResult(
        status=status, op_type="t.op", op_version=1,
        outputs={"m": mesh} if status is OpStatus.OK else {}, report={"n": 1},
        reason_code=code, kernel_version="0.0.0", image_digest="sha256:" + "0" * 64,
        lib_versions={},
    )  # fmt: skip


def test_outcome_mapping() -> None:
    assert outcome_of(result(OpStatus.OK), "cid-12345678").kind == "ok"
    rej = outcome_of(result(OpStatus.REJECTED, "SELF_INTERSECTION_CREATED"), "cid-12345678")
    assert (rej.kind, rej.code) == ("rejected", "SELF_INTERSECTION_CREATED")
    assert rej.envelope is not None and rej.envelope["correlation_id"] == "cid-12345678"
    assert (
        outcome_of(result(OpStatus.FAILED, "SELF_INTERSECTION_TIMEOUT"), "c" * 8).kind == "failed"
    )


def test_limits_have_no_default() -> None:
    with pytest.raises(RuntimeError, match="no default"):
        Limits.from_env({})
    with pytest.raises(RuntimeError):
        Limits.from_env({"JUDE_JOB_CPU_SECONDS": "0", "JUDE_JOB_MEMORY_MB": "10"})
    assert Limits.from_env({"JUDE_JOB_CPU_SECONDS": "5", "JUDE_JOB_MEMORY_MB": "64"}) == Limits(
        5, 64
    )


def _ok(_: Mapping[str, Any]) -> OpResult:
    return result(OpStatus.OK)


def _boom(_: Mapping[str, Any]) -> OpResult:
    raise ConnectionError("storage went away")


def _oom(_: Mapping[str, Any]) -> OpResult:
    raise MemoryError


def test_inline_executor() -> None:
    ex = InlineExecutor()
    assert ex.run(_ok, {}, "c" * 8, lambda: True).kind == "ok"
    assert ex.run(_boom, {}, "c" * 8, lambda: True) == Outcome("error", code="ConnectionError")
    assert ex.run(_oom, {}, "c" * 8, lambda: True).code == "JOB_RESOURCE_LIMIT"
    assert ex.run(_ok, {}, "c" * 8, lambda: False).kind == "lease_lost"


def _spin(_: Mapping[str, Any]) -> OpResult:
    while True:
        pass


def _hog(_: Mapping[str, Any]) -> OpResult:
    blocks = []
    while True:
        blocks.append(bytearray(16 * 1024 * 1024))


def _slow(_: Mapping[str, Any]) -> OpResult:
    time.sleep(3)
    return result(OpStatus.OK)


@linux_only
def test_fork_executor_limits_and_lease() -> None:
    from jude_worker.jobs.executor import ForkExecutor

    ex = ForkExecutor(Limits(cpu_seconds=1, memory_mb=64), lease_s=0.6)
    assert ex.run(_ok, {}, "c" * 8, lambda: True).kind == "ok"
    assert ex.run(_boom, {}, "c" * 8, lambda: True).code == "ConnectionError"
    assert ex.run(_spin, {}, "c" * 8, lambda: True).code == "JOB_RESOURCE_LIMIT"
    assert ex.run(_hog, {}, "c" * 8, lambda: True).code == "JOB_RESOURCE_LIMIT"
    ticks: list[int] = []

    def lose_after_two() -> bool:
        ticks.append(1)
        return len(ticks) < 2

    assert ex.run(_slow, {}, "c" * 8, lose_after_two).kind == "lease_lost"
