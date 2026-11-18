"""UT-core: DS-03 OpSpec / registry, DS-05 OpResult, IF-03 runner (XC-FND-12)."""

from collections.abc import Mapping
from typing import Any

import numpy as np
import pytest

from jude_kernel import KERNEL_VERSION
from jude_kernel.core import (
    REGISTRY,
    Frame,
    KernelContractError,
    MeshArrays,
    OpOutcome,
    OpResult,
    OpSpec,
    OpStatus,
    Registry,
    run,
)

DIGEST = "sha256:" + "ab" * 32
MESH = MeshArrays.create(
    np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
    np.array([[0, 1, 2]], dtype=np.int32),
    frame=Frame.F_SCAN,
)


def _as_kernel_fn(fn: Any) -> Any:
    """Test ops pretend to live in the kernel package (the registry only accepts those)."""
    fn.__module__ = "jude_kernel.ops._test"
    return fn


@_as_kernel_fn
def op_identity(inputs: Mapping[str, MeshArrays], params: Mapping[str, Any]) -> OpOutcome:
    return OpOutcome.ok({"out": inputs["src"]}, {"n": inputs["src"].n_vertices})


@_as_kernel_fn
def op_raises(inputs: Mapping[str, MeshArrays], params: Mapping[str, Any]) -> OpOutcome:
    raise ZeroDivisionError("boom")


@_as_kernel_fn
def op_wrong_outputs(inputs: Mapping[str, MeshArrays], params: Mapping[str, Any]) -> OpOutcome:
    return OpOutcome.ok({"other": inputs["src"]})


@_as_kernel_fn
def op_mutates_params(inputs: Mapping[str, MeshArrays], params: Mapping[str, Any]) -> OpOutcome:
    params["nested"]["x"] = 2
    return OpOutcome.ok({"out": inputs["src"]})


def spec(fn: Any, type_: str = "test.identity", version: int = 1) -> OpSpec:
    return OpSpec(
        type=type_,
        version=version,
        fn=fn,
        params_schema={"type": "object"},
        input_kinds=("src",),
        output_kinds=("out",),
        topology_preserving=True,
        guard=False,
        idempotent=True,
    )


def accept(spec: OpSpec, params: Mapping[str, Any]) -> str | None:
    return None


def not_set(spec: OpSpec, params: Mapping[str, Any]) -> str | None:
    return "PARAM_NOT_SET"


REG = Registry(
    [
        spec(op_identity),
        spec(op_raises, "test.raises"),
        spec(op_wrong_outputs, "test.wrong"),
        spec(op_mutates_params, "test.mutates"),
    ]
)


def go(op_type: str, **kw: Any) -> OpResult:
    return run(
        REG,
        op_type,
        kw.pop("version", 1),
        kw.pop("inputs", {"src": MESH}),
        kw.pop("params", {}),
        validate=kw.pop("validate", accept),
        image_digest=kw.pop("image_digest", DIGEST),
    )


def test_ok_result_is_stamped() -> None:
    r = go("test.identity")
    assert r.status is OpStatus.OK
    assert (r.op_type, r.op_version, r.kernel_version, r.image_digest) == (
        "test.identity",
        1,
        KERNEL_VERSION,
        DIGEST,
    )
    assert set(r.lib_versions) == {"numpy", "python"}
    assert r.outputs["out"] is MESH
    assert dict(r.timings_ms) == {}


def test_unknown_op_or_version_rejected() -> None:
    assert go("test.nope").reason_code == "OP_UNKNOWN"
    r = go("test.identity", version=2)
    assert (r.status, r.reason_code, dict(r.outputs)) == (OpStatus.REJECTED, "OP_UNKNOWN", {})


def test_validator_reason_rejects_before_running() -> None:
    r = go("test.raises", validate=not_set)
    assert (r.status, r.reason_code) == (OpStatus.REJECTED, "PARAM_NOT_SET")


def test_exception_becomes_failed_without_outputs() -> None:
    r = go("test.raises")
    assert (r.status, r.reason_code, dict(r.outputs)) == (OpStatus.FAILED, "KERNEL_EXCEPTION", {})
    assert r.report["exception"] == "ZeroDivisionError"


def test_output_kinds_enforced() -> None:
    r = go("test.wrong")
    assert (r.status, r.reason_code) == (OpStatus.FAILED, "OUTPUT_CONTRACT")


def test_op_gets_private_params() -> None:
    params = {"nested": {"x": 1}}
    assert go("test.mutates", params=params).status is OpStatus.OK
    assert params == {"nested": {"x": 1}}


def test_inputs_must_match_spec_and_not_be_display_only() -> None:
    with pytest.raises(KernelContractError, match="inputs"):
        go("test.identity", inputs={"other": MESH})
    display = MeshArrays.create(MESH.V, MESH.F, frame="F_scan", display_only=True)
    with pytest.raises(KernelContractError, match="display_only"):
        go("test.identity", inputs={"src": display})


def test_image_digest_format_required() -> None:
    with pytest.raises(KernelContractError, match="image_digest"):
        go("test.identity", image_digest="latest")


def test_rejected_or_failed_outcome_cannot_carry_outputs() -> None:
    with pytest.raises(KernelContractError, match="SAF-09"):
        OpOutcome(OpStatus.REJECTED, {"out": MESH}, {}, "X_Y")
    with pytest.raises(KernelContractError, match="reason_code"):
        OpOutcome(OpStatus.FAILED, {}, {}, None)
    with pytest.raises(KernelContractError, match="no reason_code"):
        OpOutcome(OpStatus.OK, {"out": MESH}, {}, "X_Y")


def test_registry_refuses_functions_outside_the_kernel() -> None:
    def outside(inputs: Mapping[str, MeshArrays], params: Mapping[str, Any]) -> OpOutcome:
        return OpOutcome.ok({})

    with pytest.raises(KernelContractError, match="must live in jude_kernel"):
        spec(outside)


def test_registry_rejects_duplicates_and_bad_specs() -> None:
    with pytest.raises(KernelContractError, match="duplicate"):
        Registry([spec(op_identity), spec(op_identity)])
    with pytest.raises(KernelContractError, match="version"):
        spec(op_identity, version=0)
    with pytest.raises(KernelContractError, match="dotted"):
        spec(op_identity, type_="Bad-Type")


def test_shipped_registry_is_immutable_and_empty_until_ops_land() -> None:
    assert len(REGISTRY) == 0
    assert not hasattr(REGISTRY, "register")
