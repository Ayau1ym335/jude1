"""DS-01 MeshArrays: the kernel's in-memory mesh value (TD-21, INV-10).

Invariants enforced at construction:
- V is float64[n, 3], C-contiguous, finite, millimetres; -0.0 is canonicalised to +0.0.
- F is int32[m, 3] with 0 <= F < n (counter-clockwise = outward on closed solids).
- face_tags (optional) is uint8[m] using only the DS-01 bit flags.
- vertex_attrs (optional) maps attribute names to finite float64[n].
- frame is one of the DS-01 frame tags; display_only meshes are never kernel inputs.

Every array is copied and made read-only, so a MeshArrays never aliases caller memory.
Size caps (SEC-07) are configuration (OD-03) and are checked with explicit limits by
``check_caps``; nothing here has a default limit.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntFlag, StrEnum
import re
from types import MappingProxyType
from typing import Any

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import KernelContractError

F64 = np.dtype("<f8")
I32 = np.dtype("<i4")
U8 = np.dtype("<u1")

ATTR_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class Frame(StrEnum):
    """DS-01 frame tag."""

    F_FILE = "F_file"
    F_SCAN = "F_scan"
    F_ANAT = "F_anat"
    F_EXPORT = "F_export"


class FaceTag(IntFlag):
    """DS-01 face_tags bit flags."""

    SCAN = 1
    CUT = 2
    WALL = 4
    CAP = 8
    SYNTHETIC = 16


FACE_TAG_MASK = int(FaceTag.SCAN | FaceTag.CUT | FaceTag.WALL | FaceTag.CAP | FaceTag.SYNTHETIC)


def canonical_float(values: NDArray[Any], *, name: str, dtype: np.dtype[Any]) -> NDArray[Any]:
    """Copy to little-endian ``dtype``, require finite values, turn -0.0 into +0.0, freeze."""
    arr = np.array(values, dtype=dtype, order="C", copy=True)
    if not np.all(np.isfinite(arr)):
        raise KernelContractError(f"{name}: values must be finite")
    arr[arr == 0] = 0  # -0.0 == 0, so this rewrites every negative zero as +0.0
    arr.setflags(write=False)
    return arr


def _frozen_int(values: NDArray[Any], *, name: str, dtype: np.dtype[Any]) -> NDArray[Any]:
    src = np.asarray(values)
    if src.dtype.kind not in "iu":
        raise KernelContractError(f"{name}: integer array required, got {src.dtype}")
    info = np.iinfo(dtype)
    if src.size and (int(src.min()) < info.min or int(src.max()) > info.max):
        raise KernelContractError(f"{name}: values out of range for {dtype}")
    arr = np.array(src, dtype=dtype, order="C", copy=True)
    arr.setflags(write=False)
    return arr


@dataclass(frozen=True, eq=False)
class MeshArrays:
    """Immutable, validated mesh value. Build with ``MeshArrays.create``."""

    V: NDArray[np.float64]
    F: NDArray[np.int32]
    frame: Frame
    face_tags: NDArray[np.uint8] | None = None
    vertex_attrs: Mapping[str, NDArray[np.float64]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    display_only: bool = False

    @classmethod
    def create(
        cls,
        vertices: NDArray[Any],
        faces: NDArray[Any],
        *,
        frame: Frame | str,
        face_tags: NDArray[np.generic] | None = None,
        vertex_attrs: Mapping[str, NDArray[np.generic]] | None = None,
        display_only: bool = False,
    ) -> "MeshArrays":
        try:
            frame_tag = Frame(frame)
        except ValueError as exc:
            raise KernelContractError(f"frame: unknown tag {frame!r}") from exc
        if not isinstance(display_only, bool):
            raise KernelContractError("display_only must be a bool")

        v_src = np.asarray(vertices)
        if v_src.dtype.kind not in "fiu":
            raise KernelContractError(f"V: numeric array required, got {v_src.dtype}")
        v = canonical_float(v_src, name="V", dtype=F64)
        if v.ndim != 2 or v.shape[1] != 3:
            raise KernelContractError(f"V: shape (n, 3) required, got {v.shape}")
        n = v.shape[0]

        f = _frozen_int(np.asarray(faces), name="F", dtype=I32)
        if f.ndim != 2 or f.shape[1] != 3:
            raise KernelContractError(f"F: shape (m, 3) required, got {f.shape}")
        if f.size and (int(f.min()) < 0 or int(f.max()) >= n):
            raise KernelContractError("F: every index must satisfy 0 <= index < n_vertices")
        m = f.shape[0]

        tags = None
        if face_tags is not None:
            tags = _frozen_int(np.asarray(face_tags), name="face_tags", dtype=U8)
            if tags.shape != (m,):
                raise KernelContractError(f"face_tags: shape ({m},) required, got {tags.shape}")
            if np.any(tags & ~np.uint8(FACE_TAG_MASK)):
                raise KernelContractError("face_tags: only DS-01 bit flags 1|2|4|8|16 allowed")

        attrs: dict[str, NDArray[np.float64]] = {}
        for name in sorted(vertex_attrs or {}):
            if not ATTR_NAME_RE.fullmatch(name):
                raise KernelContractError(f"vertex_attrs: invalid name {name!r}")
            a = canonical_float(np.asarray((vertex_attrs or {})[name]), name=name, dtype=F64)
            if a.shape != (n,):
                raise KernelContractError(f"vertex_attrs[{name}]: shape ({n},) required")
            attrs[name] = a

        return cls(
            V=v,
            F=f,
            frame=frame_tag,
            face_tags=tags,
            vertex_attrs=MappingProxyType(attrs),
            display_only=display_only,
        )

    @property
    def n_vertices(self) -> int:
        return int(self.V.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self.F.shape[0])


def check_caps(mesh: MeshArrays, *, max_vertices: int, max_faces: int) -> str | None:
    """SEC-07 size caps with explicit, configured limits. Returns a reason code or None."""
    if max_vertices < 1 or max_faces < 1:
        raise KernelContractError("caps must be explicit positive limits (no defaults, OD-03)")
    if mesh.n_faces > max_faces:
        return "FACE_LIMIT"
    if mesh.n_vertices > max_vertices:
        return "VERTEX_LIMIT"
    return None
