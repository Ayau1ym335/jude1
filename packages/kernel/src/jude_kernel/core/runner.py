"""IF-03 kernel runner: run(OpSpec, inputs, params) -> stamped DS-05 OpResult.

Steps, in order:
1. Look up (op_type, op_version); unknown -> rejected OP_UNKNOWN.
2. Inputs must be exactly the spec's input kinds, each a MeshArrays that is not
   display_only (INV-10). A mismatch is a caller bug: KernelContractError.
3. Params go through the caller-supplied validator (explicit, never defaulted); a reason
   code from it -> rejected with that code.
4. The op runs on a private deep copy of params. An exception -> failed KERNEL_EXCEPTION
   (no partial geometry, SAF-09); an ok outcome whose outputs differ from the spec's output
   kinds -> failed OUTPUT_CONTRACT.
5. The result is stamped with op type/version, KERNEL_VERSION, the container image digest
   (passed in by the worker; the kernel cannot read its environment) and library versions.
"""

from collections.abc import Mapping
import copy
import sys
from typing import Any, Protocol

import numpy as np

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import MeshArrays
from jude_kernel.core.registry import OpSpec, Registry
from jude_kernel.core.result import OpOutcome, OpResult, OpStatus
from jude_kernel.version import KERNEL_VERSION


class ParamValidator(Protocol):
    """Returns a reason code (e.g. PARAM_NOT_SET) or None when params are valid."""

    def __call__(self, spec: OpSpec, params: Mapping[str, Any]) -> str | None: ...


def lib_versions() -> dict[str, str]:
    v = sys.version_info
    return {"numpy": np.__version__, "python": f"{v.major}.{v.minor}.{v.micro}"}


def _stamp(outcome: OpOutcome, op_type: str, op_version: int, image_digest: str) -> OpResult:
    return OpResult(
        status=outcome.status,
        op_type=op_type,
        op_version=op_version,
        outputs=outcome.outputs,
        report=outcome.report,
        reason_code=outcome.reason_code,
        kernel_version=KERNEL_VERSION,
        image_digest=image_digest,
        lib_versions=lib_versions(),
    )


def run(
    registry: Registry,
    op_type: str,
    op_version: int,
    inputs: Mapping[str, MeshArrays],
    params: Mapping[str, Any],
    *,
    validate: ParamValidator,
    image_digest: str,
) -> OpResult:
    spec = registry.get(op_type, op_version)
    if spec is None:
        return _stamp(OpOutcome.rejected("OP_UNKNOWN"), op_type, max(op_version, 1), image_digest)

    if set(inputs) != set(spec.input_kinds):
        raise KernelContractError(
            f"{op_type} v{op_version}: inputs {sorted(inputs)} != {list(spec.input_kinds)}"
        )
    for name, mesh in inputs.items():
        if not isinstance(mesh, MeshArrays):
            raise KernelContractError(f"input {name!r} must be a MeshArrays")
        if mesh.display_only:
            raise KernelContractError(f"input {name!r} is display_only (INV-10)")

    reason = validate(spec, params)
    if reason is not None:
        return _stamp(OpOutcome.rejected(reason), op_type, op_version, image_digest)

    private_params = copy.deepcopy(dict(params))
    try:
        returned: object = spec.fn(inputs, private_params)
    except Exception as exc:  # any op exception becomes a failed result, never partial output
        returned = OpOutcome.failed("KERNEL_EXCEPTION", {"exception": type(exc).__name__})
    if isinstance(returned, OpOutcome):
        outcome = returned
    else:
        outcome = OpOutcome.failed("OUTPUT_CONTRACT", {"returned": type(returned).__name__})
    if outcome.status is OpStatus.OK and set(outcome.outputs) != set(spec.output_kinds):
        outcome = OpOutcome.failed(
            "OUTPUT_CONTRACT",
            {"expected": list(spec.output_kinds), "got": sorted(outcome.outputs)},
        )
    return _stamp(outcome, op_type, op_version, image_digest)
