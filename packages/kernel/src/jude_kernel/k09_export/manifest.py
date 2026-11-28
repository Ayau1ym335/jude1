"""FN-KEX-01 Build export manifest (ALG-52; FR-103, INT-05, SAF-10, SAF-06, NFR-08).

Assembles the jude-manifest/0.1 document (``manifest_schema``) that carries the zone metadata,
units, frame and approval to production, and serialises it canonically:

    data = JCS(document)            (RFC 8785, jude_kernel.k08_replay.jcs)
    manifest_sha = SHA-256(data)

The bytes are the file that is released, so a manifest hashes the same wherever it is rebuilt.

**What the kernel computes itself:**
- **the STL hash and size**, from the exported bytes, so the hash in the manifest always
  equals the file hash (completion criterion);
- **the device side of every effect block (SAF-10).** Each operation states its effect on the
  positive surface (``outward``, ``inward``, or ``unchanged`` for an op that moves nothing,
  such as the closure above its base, IDR-01). The device is formed over the positive, so its
  inner surface follows: outward gives "more space", inward gives "less space". Deriving it
  here keeps one convention throughout.

**What it checks:**
- **The document validates against the published schema.** A missing, empty or null required
  value means MANIFEST_INCOMPLETE, and the export fails. The detail lists the JSON pointers.
- **Any other mismatch is a caller bug** (``KernelContractError``): a wrong type, a value
  outside an enum, a non-rigid F_export matrix, or bytes that are not a binary STL.
- **Every index value carries a definition id and version (SAF-06).** Without one the manifest
  is incomplete.

Nothing is defaulted (DEC-029). The units ("mm", ALG-06), the frame name (F_export) and the
format ("stl-binary") are fixed by the format, not chosen here. The clock is an input
(``created_at_utc``; the kernel has none).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from typing import Any, Final

import jsonschema

from jude_kernel.core.errors import KernelContractError
from jude_kernel.k03_frames.transform import check_rigid
from jude_kernel.k08_replay.jcs import jcs_bytes
from jude_kernel.k09_export.manifest_schema import MANIFEST_SCHEMA, MANIFEST_SCHEMA_ID
from jude_kernel.version import KERNEL_VERSION

MANIFEST_INCOMPLETE: Final = "MANIFEST_INCOMPLETE"
DEVICE_SIDE: Final = {"outward": "more space", "inward": "less space", "unchanged": "unchanged"}
_VALIDATOR: Final = jsonschema.Draft202012Validator(MANIFEST_SCHEMA)


@dataclass(frozen=True)
class ManifestResult:
    """``document``, ``data`` (JCS bytes) and ``sha256`` on success, else the reason code."""

    document: dict[str, Any] | None
    data: bytes | None
    sha256: str | None
    reason_code: str | None = None
    detail: str = ""


def _effect(positive_surface: Any) -> dict[str, Any]:
    if positive_surface is None:  # absent: reported as MANIFEST_INCOMPLETE by the schema
        return {"positive_surface": None, "device_inner_surface": None}
    if positive_surface not in DEVICE_SIDE:
        raise KernelContractError(f"positive_surface: one of {sorted(DEVICE_SIDE)} required")
    return {"positive_surface": positive_surface,
            "device_inner_surface": DEVICE_SIDE[positive_surface]}  # fmt: skip


def _operation(op: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: op[k] for k in ("seq", "type", "op_version", "category", "name", "params") if k in op}
    out["effect"] = _effect(op.get("positive_surface"))
    return out


def _stl_file(name: Any, stl: Any) -> dict[str, Any]:
    if not isinstance(stl, bytes | bytearray):
        raise KernelContractError("stl: the exported binary STL bytes are required")
    n = int.from_bytes(stl[80:84], "little") if len(stl) >= 84 else -1
    if n < 0 or len(stl) != 84 + 50 * n:
        raise KernelContractError("stl: not a binary STL (size != 84 + 50 n)")
    return {"name": name, "sha256": hashlib.sha256(stl).hexdigest(), "format": "stl-binary",
            "units": "mm", "size_bytes": len(stl)}  # fmt: skip


def _pointer(path: Sequence[Any]) -> str:
    return "/" + "/".join(str(p) for p in path)


def _missing_pointer(error: jsonschema.ValidationError) -> str:
    path = list(error.path)
    if error.validator == "required":  # the absent member is named in the message only
        path.append(error.message.split("'")[1])
    return _pointer(path)


def _is_missing(error: jsonschema.ValidationError) -> bool:
    if error.validator == "required":
        return True
    return error.instance is None or (error.validator == "minLength" and error.instance == "")


def build_manifest(
    *,
    case_id: Any,
    design_version_id: Any,
    design_version_number: Any,
    stl_name: Any,
    stl: Any,
    frame_matrix: Any,
    frame_definition_ref: Any,
    config_version: Any,
    source_scan_sha256: Any,
    operations: Sequence[Mapping[str, Any]],
    template_ref: Any,
    approval: Mapping[str, Any],
    reimport_check: Mapping[str, Any],
    index_values: Sequence[Mapping[str, Any]],
    software_build: Any,
    created_at_utc: Any,
    intended_use_statement: Any,
) -> ManifestResult:
    """FN-KEX-01: the jude-manifest/0.1 document, its JCS bytes and its SHA-256."""
    if frame_matrix is not None:
        reason = check_rigid(frame_matrix)
        if reason is not None:
            raise KernelContractError(f"frame_matrix: F_export must be rigid ({reason})")
        frame_matrix = [float(x) for x in list(frame_matrix)]
    document = {
        "schema": MANIFEST_SCHEMA_ID,
        "case_id": case_id,
        "design_version": {"id": design_version_id, "number": design_version_number},
        "files": [_stl_file(stl_name, stl)],
        "frame": {"name": "F_export", "matrix": frame_matrix,
                  "definition_ref": frame_definition_ref, "config_version": config_version},
        "source_scan_sha256": source_scan_sha256,
        "operations": [_operation(op) for op in operations],
        "template_ref": template_ref,
        "approval": dict(approval),
        "reimport_check": dict(reimport_check),
        "index_values": [dict(v) for v in index_values],
        "software": {"build": software_build, "kernel_version": KERNEL_VERSION},
        "created_at_utc": created_at_utc,
        "intended_use_statement": intended_use_statement,
    }  # fmt: skip
    errors = sorted(_VALIDATOR.iter_errors(document), key=lambda e: [str(p) for p in e.path])
    missing = [e for e in errors if _is_missing(e)]
    if missing:
        where = sorted({_missing_pointer(e) for e in missing})
        return ManifestResult(None, None, None, MANIFEST_INCOMPLETE, ", ".join(where))
    if errors:
        e = errors[0]
        raise KernelContractError(f"manifest {_pointer(e.path)}: {e.message}")
    data = jcs_bytes(document)
    return ManifestResult(document, data, hashlib.sha256(data).hexdigest())
