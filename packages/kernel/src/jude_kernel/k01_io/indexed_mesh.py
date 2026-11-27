"""FN-KIO-05 Build and validate indexed mesh (ALG-05; FR-010, FR-015, SEC-07).

Turns parser output into the canonical indexed triangle mesh, in deterministic order:

1. -0.0 becomes +0.0.
2. Exactly equal vertex triples merge into one index. This is bitwise equality of the float64
   triple: no epsilon welding, because near-duplicates must stay separate rather than
   silently change the topology (05 §1.1). Vertices come in first-occurrence order.
3. Faces stay in file order and are never sorted, so a face id is a stable reference.
   Degenerate faces are kept; ALG-08 reports them.
4. Validation:
   - all coordinates are finite, else NON_FINITE_COORDINATES;
   - indices are in range, else FILE_UNREADABLE;
   - there is at least one face, else FILE_EMPTY;
   - the face count is at most ``max_faces``, the deployment cap with no default (OD-03),
     else FACE_LIMIT.

The input is either a triangle soup (``float64[3m, 3]``, from the STL parser) or an indexed
``(V, F)`` pair (OBJ / PLY parsers, with ``polygons_triangulated`` from their fan
triangulation). The result is a DS-01 ``MeshArrays`` in frame F_file plus the import stats of
FN-KIO-05: ``{n_vertices_in, n_vertices_merged, polygons_triangulated, notices}``.
"""

from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import Frame, MeshArrays

NON_FINITE: Final = "NON_FINITE_COORDINATES"
FILE_EMPTY: Final = "FILE_EMPTY"
FILE_UNREADABLE: Final = "FILE_UNREADABLE"
FACE_LIMIT: Final = "FACE_LIMIT"
INT32_MAX: Final = 2**31 - 1


@dataclass(frozen=True)
class ImportStats:
    n_vertices_in: int
    n_vertices_merged: int
    polygons_triangulated: int = 0
    notices: tuple[str, ...] = field(default=())

    def as_json(self) -> dict[str, Any]:
        return {
            "n_vertices_in": self.n_vertices_in,
            "n_vertices_merged": self.n_vertices_merged,
            "polygons_triangulated": self.polygons_triangulated,
            "notices": list(self.notices),
        }


@dataclass(frozen=True)
class IndexedMesh:
    """``mesh`` and ``stats`` on success, else ``reason_code`` and ``detail``."""

    mesh: MeshArrays | None
    stats: ImportStats | None
    reason_code: str | None = None
    detail: str = ""


def _refuse(code: str, detail: str) -> IndexedMesh:
    return IndexedMesh(None, None, code, detail)


def weld(points: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Exact merge: (unique points in first-occurrence order, index of each input point)."""
    canon = np.ascontiguousarray(np.where(points == 0.0, 0.0, points), dtype=np.float64)
    rows = canon.view(np.dtype((np.void, canon.dtype.itemsize * 3))).ravel()
    _, first, inverse = np.unique(rows, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")  # unique ids by first appearance
    rank = np.empty_like(order)
    rank[order] = np.arange(order.size)
    return canon[first[order]], rank[inverse.ravel()]


def _check_finite(values: NDArray[np.float64], what: str) -> IndexedMesh | None:
    bad = ~np.isfinite(values)
    if np.any(bad):
        row = int(np.argwhere(bad)[0][0])
        return _refuse(NON_FINITE, f"{what} {row}: non-finite coordinate")
    return None


def _check_limits(m: int, max_faces: int) -> IndexedMesh | None:
    if isinstance(max_faces, bool) or not isinstance(max_faces, int) or max_faces < 1:
        raise KernelContractError("max_faces: the configured face cap is required (no default)")
    if 3 * max_faces > INT32_MAX:
        raise KernelContractError("max_faces: 3 * cap must fit int32 vertex indices (DS-01)")
    if m == 0:
        return _refuse(FILE_EMPTY, "no faces")
    if m > max_faces:
        return _refuse(FACE_LIMIT, f"{m} faces, cap {max_faces}")
    return None


def _result(
    v: NDArray[np.float64], f: NDArray[np.int64], n_in: int, triangulated: int,
    notices: tuple[str, ...],
) -> IndexedMesh:  # fmt: skip
    mesh = MeshArrays.create(v, f.astype(np.int32), frame=Frame.F_FILE)
    stats = ImportStats(n_in, n_in - mesh.n_vertices, triangulated, notices)
    return IndexedMesh(mesh, stats)


def from_soup(soup: Any, *, max_faces: int, notices: tuple[str, ...] = ()) -> IndexedMesh:
    """FN-KIO-05 for a triangle soup ``float64[3m, 3]`` (three corners per face, in order)."""
    s = np.asarray(soup, dtype=np.float64)
    if s.ndim != 2 or s.shape[1] != 3 or s.shape[0] % 3:
        raise KernelContractError(f"soup: shape (3m, 3) required, got {s.shape}")
    if (limit := _check_limits(s.shape[0] // 3, max_faces)) is not None:
        return limit
    if (bad := _check_finite(s, "corner")) is not None:
        return bad
    v, idx = weld(s)
    return _result(v, idx.reshape(-1, 3), s.shape[0], 0, notices)


def from_indexed(
    vertices: Any, faces: Any, *, max_faces: int, polygons_triangulated: int = 0,
    notices: tuple[str, ...] = (),
) -> IndexedMesh:  # fmt: skip
    """FN-KIO-05 for an indexed pair from a parser: merge equal vertices, remap the faces."""
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces)
    if v.ndim != 2 or v.shape[1] != 3 or f.ndim != 2 or f.shape[1] != 3:
        raise KernelContractError("vertices (n, 3) and faces (m, 3) required")
    if f.dtype.kind not in "iu":
        raise KernelContractError(f"faces: integer indices required, got {f.dtype}")
    if (limit := _check_limits(f.shape[0], max_faces)) is not None:
        return limit
    if f.size and (int(f.min()) < 0 or int(f.max()) >= v.shape[0]):
        return _refuse(FILE_UNREADABLE, f"face index outside 0..{v.shape[0] - 1}")
    if (bad := _check_finite(v, "vertex")) is not None:
        return bad
    merged, idx = weld(v)
    return _result(merged, idx[f.astype(np.int64)], v.shape[0], polygons_triangulated, notices)
