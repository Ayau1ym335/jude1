"""Deterministic test meshes (FN-OPS-06). Vertex arrays float64 mm, faces int32, outward CCW.

Cross-platform bytes: coordinates use only correctly rounded IEEE operations (+ - * / sqrt).
Where a transcendental function is unavoidable, its value is first snapped to a dyadic grid
(``dyadic``), so a last-bit difference between libm implementations cannot change the output.
"""

import math

import numpy as np
from numpy.typing import NDArray

Vec = NDArray[np.float64]
Faces = NDArray[np.int32]

DYADIC_BITS = 40


def dyadic(x: float, bits: int = DYADIC_BITS) -> float:
    """``x`` rounded to a multiple of 2**-bits (deterministic for libm-dependent values)."""
    scale = float(2**bits)
    return round(x * scale) / scale


def cos_sin(angle_rad: float) -> tuple[float, float]:
    return dyadic(math.cos(angle_rad)), dyadic(math.sin(angle_rad))


def _normalise_rows(v: Vec) -> Vec:
    n = np.sqrt(v[:, 0] * v[:, 0] + v[:, 1] * v[:, 1] + v[:, 2] * v[:, 2])
    return v / n[:, None]


def icosahedron() -> tuple[Vec, Faces]:
    t = (1.0 + math.sqrt(5.0)) / 2.0
    v = np.array(
        [
            [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
            [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
            [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1],
        ],
        dtype=np.float64,
    )  # fmt: skip
    f = np.array(
        [
            [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
            [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
            [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
            [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
        ],
        dtype=np.int32,
    )  # fmt: skip
    return _normalise_rows(v), f


def subdivide_on_sphere(v: Vec, f: Faces) -> tuple[Vec, Faces]:
    """One 4:1 subdivision; new vertices are edge midpoints pushed to the unit sphere."""
    edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    keys = np.sort(edges, axis=1)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    mids = _normalise_rows(v[uniq[:, 0]] + v[uniq[:, 1]])
    base = v.shape[0]
    m = f.shape[0]
    mid = (inverse.reshape(3, m) + base).astype(np.int32)  # rows: ab, bc, ca
    ab, bc, ca = mid[0], mid[1], mid[2]
    a, b, c = f[:, 0], f[:, 1], f[:, 2]
    nf = np.concatenate(
        [np.stack([a, ab, ca], 1), np.stack([b, bc, ab], 1), np.stack([c, ca, bc], 1),
         np.stack([ab, bc, ca], 1)]
    ).astype(np.int32)  # fmt: skip
    return np.concatenate([v, mids]), nf


def icosphere(level: int, radius: float) -> tuple[Vec, Faces]:
    """Icosphere with 20*4**level faces; every vertex at distance ``radius`` (to rounding)."""
    v, f = icosahedron()
    for _ in range(level):
        v, f = subdivide_on_sphere(v, f)
    return v * radius, f


def ellipsoid(
    level: int, a: float, b: float, c: float, rot: tuple[float, float] = (1.0, 0.0)
) -> tuple[Vec, Faces]:
    """Unit icosphere scaled to semi-axes (a, b, c), then rotated about z by (cos, sin)."""
    v, f = icosphere(level, 1.0)
    x, y, z = v[:, 0] * a, v[:, 1] * b, v[:, 2] * c
    cs, sn = rot
    out = np.stack([cs * x - sn * y, sn * x + cs * y, z], axis=1)
    return out, f


def torus(major: float, minor: float, nu: int, nv: int) -> tuple[Vec, Faces]:
    """Closed torus about z (genus 1), nu x nv quads split into triangles, outward CCW."""
    cu = [cos_sin(2.0 * math.pi * i / nu) for i in range(nu)]
    cv = [cos_sin(2.0 * math.pi * j / nv) for j in range(nv)]
    v = np.array(
        [[(major + minor * cvj) * cui, (major + minor * cvj) * sui, minor * svj]
         for cui, sui in cu for cvj, svj in cv],
        dtype=np.float64,
    )  # fmt: skip
    faces = []
    for i in range(nu):
        for j in range(nv):
            p, q = i * nv + j, ((i + 1) % nu) * nv + j
            p1, q1 = i * nv + (j + 1) % nv, ((i + 1) % nu) * nv + (j + 1) % nv
            faces += [[p, q, q1], [p, q1, p1]]
    return v, np.array(faces, dtype=np.int32)


def keep_faces(v: Vec, f: Faces, keep: NDArray[np.bool_]) -> tuple[Vec, Faces]:
    """Sub-mesh of the kept faces with unused vertices removed (order preserved)."""
    kept = f[keep]
    used = np.unique(kept)
    remap = np.full(v.shape[0], -1, dtype=np.int64)
    remap[used] = np.arange(used.size)
    return v[used], remap[kept].astype(np.int32)


def signed_volume(v: Vec, f: Faces) -> float:
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    cross = np.cross(b, c)
    return float(math.fsum((a * cross).sum(axis=1).tolist()) / 6.0)
