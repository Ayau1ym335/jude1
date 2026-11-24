"""FN-KRP-02 Canonical geometry hash (ALG-54; ADR-010, TD-19, TD-20; FR-052, FR-090, FR-101).

Byte-exact identity of geometry, used for approval binding: an approval stores the
geometry_sha of the version (INV-04), and export proves that the replayed geometry has the
same hash (FN-EXP-02).

    geometry_sha256 = SHA-256( b"JGEO1"
                               || uint64 LE  nV
                               || uint64 LE  nF
                               || V  float64 LE, row-major, with -0.0 -> +0.0
                               || F  int32   LE, row-major )

- -0.0 is the only canonicalisation. Every other bit of every coordinate counts, so a 1-ulp
  change in any coordinate gives a different hash. Equal-but-differently-signed zeros are the
  only bit patterns that compare equal, and they hash equal.
- Face order and vertex order are part of the identity. The kernel's order is deterministic,
  so sorting would only add cost (ALG-54 alternative, rejected).
- The counts are in the layout, so the bytes of V cannot be confused with those of F.
- Inputs: V float64[nV, 3], finite; F int32[nF, 3]. Any other dtype or shape, or a non-finite
  coordinate, raises KernelContractError: a programming error, since finiteness is checked
  upstream (EH-KRN). There is no silent conversion: hashing float32 coordinates as float64 would
  name a geometry that was never stored.
- Pure function: no clock, randomness or I/O. hashlib only.
"""

import hashlib
import struct
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import MeshArrays

GEOMETRY_MAGIC: Final = b"JGEO1"
_F64: Final = np.dtype("<f8")
_I32: Final = np.dtype("<i4")


def _check(values: Any, *, name: str, kind: str, itemsize: int) -> NDArray[Any]:
    arr = np.asarray(values)
    if arr.dtype.kind != kind or arr.dtype.itemsize != itemsize:
        want = "float64" if kind == "f" else "int32"
        raise KernelContractError(f"{name}: {want} required, got {arr.dtype}")
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise KernelContractError(f"{name}: shape (n, 3) required, got {arr.shape}")
    return arr


def canonical_geometry_bytes(V: NDArray[Any], F: NDArray[Any]) -> bytes:  # noqa: N803 - DS-01
    """The ALG-54 byte layout that is hashed (exposed for tests and audits)."""
    v = _check(V, name="V", kind="f", itemsize=8)
    f = _check(F, name="F", kind="i", itemsize=4)
    if not np.all(np.isfinite(v)):
        raise KernelContractError("V: values must be finite")
    v = np.ascontiguousarray(v, dtype=_F64)
    v = np.where(v == 0.0, 0.0, v).astype(_F64, copy=False)  # -0.0 -> +0.0, nothing else
    f = np.ascontiguousarray(f, dtype=_I32)
    head = GEOMETRY_MAGIC + struct.pack("<QQ", v.shape[0], f.shape[0])
    return head + v.tobytes(order="C") + f.tobytes(order="C")


def geometry_sha256(V: NDArray[Any], F: NDArray[Any]) -> str:  # noqa: N803 - DS-01 names
    """Lower-case hex SHA-256 of the canonical layout (``char(64)`` geometry_sha)."""
    return hashlib.sha256(canonical_geometry_bytes(V, F)).hexdigest()


def mesh_geometry_sha256(mesh: MeshArrays) -> str:
    """geometry_sha of a MeshArrays (its V and F only; tags and attributes are not geometry)."""
    return geometry_sha256(mesh.V, mesh.F)
