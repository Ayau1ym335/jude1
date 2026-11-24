"""FN-KRP-03 Canonical parameter-list hash (ALG-55; TD-19, TD-20; FR-090 binding 3, DATA-04).

The identity of the parameters an approval binds:

    params_sha = SHA-256( JCS(parameter document) )        (RFC 8785, ``jcs.jcs_bytes``)

Canonical JSON makes the identity independent of key order and whitespace: two documents
with the same members hash equal. Any value change (a number by one ulp, a string, a list
order, a flag) changes the hash.

``parameter_document`` builds the document from the FN-KRP-03 inputs, so every caller binds
the same structure (schema ``jude-params/1``):

    {"schema": "jude-params/1",
     "cleanup_ops": [...],                         # in their order
     "frame": {"id": "<uuid>", "matrix": [16 doubles, row-major]},
     "design_ops": [{"type", "op_version", "params", "enabled"}, ...],   # in their order
     "template_ref": "<ref>" | null,
     "config_version": <int>}

Lists keep their order: the op log is ordered, and reordering it is a different design. The
values come from the caller as they are stored. This function sets no default (DEC-029): a
missing input is an error, not a default.
"""

from collections.abc import Mapping, Sequence
import hashlib
import math
from typing import Any, Final

from jude_kernel.core.errors import KernelContractError
from jude_kernel.k08_replay.jcs import jcs_bytes

PARAMS_SCHEMA: Final = "jude-params/1"
_DESIGN_OP_KEYS: Final = frozenset({"type", "op_version", "params", "enabled"})


def params_sha256(document: Any) -> str:
    """Lower-case hex SHA-256 of the JCS form of ``document`` (``char(64)`` params_sha)."""
    return hashlib.sha256(jcs_bytes(document)).hexdigest()


def parameter_document(
    *,
    cleanup_ops: Sequence[Mapping[str, Any]],
    frame_id: str,
    frame_matrix: Sequence[float],
    design_ops: Sequence[Mapping[str, Any]],
    template_ref: str | None,
    config_version: int,
) -> dict[str, Any]:
    """The FN-KRP-03 input set as one JSON document (validated, not hashed)."""
    matrix = [float(x) for x in frame_matrix]
    if len(matrix) != 16 or not all(math.isfinite(x) for x in matrix):
        raise KernelContractError("frame_matrix: 16 finite values (row-major 4x4) required")
    if not isinstance(frame_id, str) or not frame_id:
        raise KernelContractError("frame_id: non-empty string required")
    if isinstance(config_version, bool) or not isinstance(config_version, int):
        raise KernelContractError("config_version: integer required")
    if template_ref is not None and not isinstance(template_ref, str):
        raise KernelContractError("template_ref: string or None required")
    ops = []
    for i, op in enumerate(design_ops):
        if set(op) != _DESIGN_OP_KEYS:
            raise KernelContractError(
                f"design_ops[{i}]: exactly {sorted(_DESIGN_OP_KEYS)} required, got {sorted(op)}"
            )
        if not isinstance(op["enabled"], bool):
            raise KernelContractError(f"design_ops[{i}].enabled: bool required")
        ops.append(dict(op))
    return {
        "schema": PARAMS_SCHEMA,
        "cleanup_ops": [dict(op) for op in cleanup_ops],
        "frame": {"id": frame_id, "matrix": matrix},
        "design_ops": ops,
        "template_ref": template_ref,
        "config_version": config_version,
    }
