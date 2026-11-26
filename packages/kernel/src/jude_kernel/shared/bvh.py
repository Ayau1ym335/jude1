"""XC-SHR-02 Deterministic AABB BVH (IDR-10; ALG-11, ALG-33, ALG-34, ALG-40).

The one spatial index of the kernel. It serves four kinds of query:

- closest point: anchors (ALG-33), signed distance (ALG-40);
- first ray hit: sector coverage (ALG-34), thickness;
- box-pair candidates: self-intersection broad phase (ALG-11);
- faces in a box: the incremental guard after a local edit, together with ``refit``.

**Determinism** (VER-07). The same (V, F) always gives the same tree and the same answers:
- median split on the face-box centres along the widest axis, with a stable sort, so equal
  keys keep a fixed order;
- every loop and the traversal order are fixed;
- numba with fastmath and parallel off (``kernel_jit``);
- pair and face outputs are sorted.

**Tie rule** (T14). Among faces at exactly the same squared distance (closest point) or the
same parameter t (ray), the smallest face_id wins. Branch-and-bound prunes a node only when
its box is farther than the current best by more than ``PRUNE_MARGIN``, so no tied face (and
no face that rounds 1 ulp closer) is ever skipped.

**Closest point on a triangle** (Ericson, Real-Time Collision Detection §5.1.5). The Voronoi
regions are classified by dot products, which gives the feature (vertex A/B/C, edge AB/AC/BC,
face) and the barycentric coordinates. A degenerate triangle (zero area) is handled as its
three edges, so no division by zero reaches a result.

**Ray hit** (Moller-Trumbore) with an exact ``det == 0`` test for rays parallel to the plane,
no epsilon (DEC-025: no ad-hoc tolerances). A hit on an edge or vertex counts (closed
triangle).

Boxes are closed and exact: no inflation, float64 throughout, millimetres.
"""

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import KernelContractError
from jude_kernel.shared.jit import kernel_jit

LEAF_SIZE: Final = 4
# Conservative pruning margin (relative). The box tests and the triangle tests round
# differently, so a box can look 1 ulp farther than a hit inside it (rays through a vertex
# shared by many faces). A box is therefore skipped only when it is farther than the best hit
# by more than this margin. It is not a geometric tolerance: every answer still comes from
# the exact same triangle test as the brute-force oracle, and a larger margin only costs a
# few extra triangle tests. 2**-20 is far above the double rounding of either test.
PRUNE_MARGIN: Final = 2.0**-20
NO_FACE: Final = -1

# feature codes of a closest point (ALG-33 feature type)
FEATURE_FACE: Final = 0
FEATURE_EDGE_AB: Final = 1
FEATURE_EDGE_AC: Final = 2
FEATURE_EDGE_BC: Final = 3
FEATURE_VERTEX_A: Final = 4
FEATURE_VERTEX_B: Final = 5
FEATURE_VERTEX_C: Final = 6


# --- triangle primitives -----------------------------------------------------------------------


@kernel_jit
def _segment_closest(
    p: NDArray[np.float64], a: NDArray[np.float64], b: NDArray[np.float64]
) -> tuple[float, float]:
    """(squared distance, parameter s in [0, 1]) of p to segment a + s (b - a)."""
    abx, aby, abz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    apx, apy, apz = p[0] - a[0], p[1] - a[1], p[2] - a[2]
    den = abx * abx + aby * aby + abz * abz
    s = 0.0
    if den > 0.0:
        s = (apx * abx + apy * aby + apz * abz) / den
        if s < 0.0:
            s = 0.0
        elif s > 1.0:
            s = 1.0
    dx = a[0] + s * abx - p[0]
    dy = a[1] + s * aby - p[1]
    dz = a[2] + s * abz - p[2]
    return dx * dx + dy * dy + dz * dz, s


@kernel_jit
def closest_point_triangle(
    p: NDArray[np.float64],
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    out: NDArray[np.float64],
) -> tuple[float, int]:
    """Closest point of triangle abc to p (Ericson 5.1.5).

    Writes the barycentric coordinates (wa, wb, wc) to ``out[0:3]`` and the point to
    ``out[3:6]``; returns (squared distance, feature code).
    """
    abx, aby, abz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    acx, acy, acz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    apx, apy, apz = p[0] - a[0], p[1] - a[1], p[2] - a[2]
    d1 = abx * apx + aby * apy + abz * apz
    d2 = acx * apx + acy * apy + acz * apz
    wa, wb, wc, feature = 0.0, 0.0, 0.0, FEATURE_FACE
    if d1 <= 0.0 and d2 <= 0.0:
        wa, feature = 1.0, FEATURE_VERTEX_A
    else:
        bpx, bpy, bpz = p[0] - b[0], p[1] - b[1], p[2] - b[2]
        d3 = abx * bpx + aby * bpy + abz * bpz
        d4 = acx * bpx + acy * bpy + acz * bpz
        cpx, cpy, cpz = p[0] - c[0], p[1] - c[1], p[2] - c[2]
        d5 = abx * cpx + aby * cpy + abz * cpz
        d6 = acx * cpx + acy * cpy + acz * cpz
        vc = d1 * d4 - d3 * d2
        vb = d5 * d2 - d1 * d6
        va = d3 * d6 - d5 * d4
        if d3 >= 0.0 and d4 <= d3:
            wb, feature = 1.0, FEATURE_VERTEX_B
        elif vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
            v = d1 / (d1 - d3)
            wa, wb, feature = 1.0 - v, v, FEATURE_EDGE_AB
        elif d6 >= 0.0 and d5 <= d6:
            wc, feature = 1.0, FEATURE_VERTEX_C
        elif vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
            w = d2 / (d2 - d6)
            wa, wc, feature = 1.0 - w, w, FEATURE_EDGE_AC
        elif va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
            w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
            wb, wc, feature = 1.0 - w, w, FEATURE_EDGE_BC
        elif va + vb + vc != 0.0:
            den = 1.0 / (va + vb + vc)
            v, w = vb * den, vc * den
            wa, wb, wc = 1.0 - v - w, v, w
        else:  # degenerate (zero-area) triangle: the closest of its three edges
            s_ab, t_ab = _segment_closest(p, a, b)
            s_ac, t_ac = _segment_closest(p, a, c)
            s_bc, t_bc = _segment_closest(p, b, c)
            if s_ab <= s_ac and s_ab <= s_bc:
                wa, wb, feature = 1.0 - t_ab, t_ab, FEATURE_EDGE_AB
            elif s_ac <= s_bc:
                wa, wc, feature = 1.0 - t_ac, t_ac, FEATURE_EDGE_AC
            else:
                wb, wc, feature = 1.0 - t_bc, t_bc, FEATURE_EDGE_BC
    out[0], out[1], out[2] = wa, wb, wc
    qx = wa * a[0] + wb * b[0] + wc * c[0]
    qy = wa * a[1] + wb * b[1] + wc * c[1]
    qz = wa * a[2] + wb * b[2] + wc * c[2]
    out[3], out[4], out[5] = qx, qy, qz
    dx, dy, dz = qx - p[0], qy - p[1], qz - p[2]
    return dx * dx + dy * dy + dz * dz, feature


@kernel_jit
def ray_triangle(
    o: NDArray[np.float64],
    d: NDArray[np.float64],
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
) -> tuple[bool, float, float, float]:
    """Moller-Trumbore: (hit, t, u, v) of ray o + t d with closed triangle abc."""
    e1x, e1y, e1z = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    e2x, e2y, e2z = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    px = d[1] * e2z - d[2] * e2y
    py = d[2] * e2x - d[0] * e2z
    pz = d[0] * e2y - d[1] * e2x
    det = e1x * px + e1y * py + e1z * pz
    if det == 0.0:
        return False, 0.0, 0.0, 0.0
    inv = 1.0 / det
    tx, ty, tz = o[0] - a[0], o[1] - a[1], o[2] - a[2]
    u = (tx * px + ty * py + tz * pz) * inv
    if u < 0.0 or u > 1.0:
        return False, 0.0, 0.0, 0.0
    qx = ty * e1z - tz * e1y
    qy = tz * e1x - tx * e1z
    qz = tx * e1y - ty * e1x
    v = (d[0] * qx + d[1] * qy + d[2] * qz) * inv
    if v < 0.0 or u + v > 1.0:
        return False, 0.0, 0.0, 0.0
    t = (e2x * qx + e2y * qy + e2z * qz) * inv
    return True, t, u, v


# --- build and refit ------------------------------------------------------------------------------


@kernel_jit
def _face_boxes(
    V: NDArray[np.float64],  # noqa: N803 - DS-01 names
    F: NDArray[np.int32],  # noqa: N803
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    m = F.shape[0]
    lo = np.empty((m, 3))
    hi = np.empty((m, 3))
    for f in range(m):
        for k in range(3):
            x0, x1, x2 = V[F[f, 0], k], V[F[f, 1], k], V[F[f, 2], k]
            lo[f, k] = min(x0, min(x1, x2))
            hi[f, k] = max(x0, max(x1, x2))
    return lo, hi


@kernel_jit
def _build(
    flo: NDArray[np.float64], fhi: NDArray[np.float64], leaf_size: int
) -> tuple[
    NDArray[np.int32], NDArray[np.int32], NDArray[np.int32], NDArray[np.int32],
    NDArray[np.int32], NDArray[np.float64], NDArray[np.float64], int,
]:  # fmt: skip
    m = flo.shape[0]
    order = np.arange(m).astype(np.int32)
    cap = max(1, 2 * m)
    left = np.full(cap, -1, np.int32)
    right = np.full(cap, -1, np.int32)
    start = np.zeros(cap, np.int32)
    count = np.zeros(cap, np.int32)
    nlo = np.empty((cap, 3))
    nhi = np.empty((cap, 3))
    centre = (flo + fhi) * 0.5
    stack = np.empty(cap, np.int32)
    n_nodes = 1
    start[0], count[0] = 0, m
    top = 0
    stack[0] = 0
    while top >= 0:
        node = stack[top]
        top -= 1
        s, c = start[node], count[node]
        for k in range(3):
            lo_k, hi_k = np.inf, -np.inf
            for i in range(s, s + c):
                f = order[i]
                lo_k = min(lo_k, flo[f, k])
                hi_k = max(hi_k, fhi[f, k])
            nlo[node, k], nhi[node, k] = lo_k, hi_k
        if c <= leaf_size:
            continue
        axis, best = 0, -1.0
        for k in range(3):  # widest spread of the centres; ties: the lowest axis
            cmin, cmax = np.inf, -np.inf
            for i in range(s, s + c):
                x = centre[order[i], k]
                cmin = min(cmin, x)
                cmax = max(cmax, x)
            if cmax - cmin > best:
                axis, best = k, cmax - cmin
        keys = np.empty(c)
        for i in range(c):
            keys[i] = centre[order[s + i], axis]
        perm = np.argsort(keys, kind="mergesort")  # stable: equal keys keep their order
        seg = order[s : s + c].copy()
        for i in range(c):
            order[s + i] = seg[perm[i]]
        half = c // 2
        lc, rc = n_nodes, n_nodes + 1
        n_nodes += 2
        start[lc], count[lc] = s, half
        start[rc], count[rc] = s + half, c - half
        left[node], right[node] = lc, rc
        top += 1
        stack[top] = rc
        top += 1
        stack[top] = lc
    return order, left, right, start, count, nlo, nhi, n_nodes


@kernel_jit
def _refit_nodes(
    order: NDArray[np.int32], left: NDArray[np.int32], right: NDArray[np.int32],
    start: NDArray[np.int32], count: NDArray[np.int32], flo: NDArray[np.float64],
    fhi: NDArray[np.float64], n_nodes: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:  # fmt: skip
    nlo = np.empty((n_nodes, 3))
    nhi = np.empty((n_nodes, 3))
    for node in range(n_nodes - 1, -1, -1):  # children always have larger indices
        for k in range(3):
            if left[node] < 0:
                lo_k, hi_k = np.inf, -np.inf
                for i in range(start[node], start[node] + count[node]):
                    lo_k = min(lo_k, flo[order[i], k])
                    hi_k = max(hi_k, fhi[order[i], k])
            else:
                lo_k = min(nlo[left[node], k], nlo[right[node], k])
                hi_k = max(nhi[left[node], k], nhi[right[node], k])
            nlo[node, k], nhi[node, k] = lo_k, hi_k
    return nlo, nhi


# --- queries -------------------------------------------------------------------------------------


@kernel_jit
def _box_sqdist(q: NDArray[np.float64], lo: NDArray[np.float64], hi: NDArray[np.float64]) -> float:
    s = 0.0
    for k in range(3):
        if q[k] < lo[k]:
            d = lo[k] - q[k]
            s += d * d
        elif q[k] > hi[k]:
            d = q[k] - hi[k]
            s += d * d
    return s


@kernel_jit
def _closest_points(
    Q: NDArray[np.float64], V: NDArray[np.float64], F: NDArray[np.int32],  # noqa: N803
    order: NDArray[np.int32], left: NDArray[np.int32], right: NDArray[np.int32],
    start: NDArray[np.int32], count: NDArray[np.int32], nlo: NDArray[np.float64],
    nhi: NDArray[np.float64],
) -> tuple[
    NDArray[np.int32], NDArray[np.float64], NDArray[np.float64], NDArray[np.int8]
]:  # fmt: skip
    n = Q.shape[0]
    face = np.full(n, NO_FACE, np.int32)
    sqd = np.full(n, np.inf)
    res = np.zeros((n, 6))
    feat = np.zeros(n, np.int8)
    stack = np.empty(128, np.int32)
    tmp = np.empty(6)
    for qi in range(n):
        q = Q[qi]
        best, best_face = np.inf, NO_FACE
        top = 0
        stack[0] = 0
        while top >= 0:
            node = stack[top]
            top -= 1
            if _box_sqdist(q, nlo[node], nhi[node]) > best * (1.0 + PRUNE_MARGIN):
                continue  # strictly farther: a tie can still be inside
            if left[node] < 0:
                for i in range(start[node], start[node] + count[node]):
                    f = order[i]
                    d2, ft = closest_point_triangle(q, V[F[f, 0]], V[F[f, 1]], V[F[f, 2]], tmp)
                    if d2 < best or (d2 == best and f < best_face):
                        best, best_face = d2, f
                        res[qi, :] = tmp
                        feat[qi] = ft
            else:
                dl = _box_sqdist(q, nlo[left[node]], nhi[left[node]])
                dr = _box_sqdist(q, nlo[right[node]], nhi[right[node]])
                near, far = (left[node], right[node]) if dl <= dr else (right[node], left[node])
                top += 1
                stack[top] = far
                top += 1
                stack[top] = near
        face[qi] = best_face
        sqd[qi] = best
    return face, sqd, res, feat


@kernel_jit
def _ray_box(
    o: NDArray[np.float64], d: NDArray[np.float64], lo: NDArray[np.float64],
    hi: NDArray[np.float64], t0: float, t1: float,
) -> bool:  # fmt: skip
    for k in range(3):
        if d[k] == 0.0:
            if o[k] < lo[k] or o[k] > hi[k]:
                return False
            continue
        ta = (lo[k] - o[k]) / d[k]
        tb = (hi[k] - o[k]) / d[k]
        if ta > tb:
            ta, tb = tb, ta
        ta -= abs(ta) * PRUNE_MARGIN  # conservative: never skip a box that holds a hit
        tb += abs(tb) * PRUNE_MARGIN
        t0 = max(t0, ta)
        t1 = min(t1, tb)
        if t0 > t1:
            return False
    return True


@kernel_jit
def _first_hits(
    origins: NDArray[np.float64], dirs: NDArray[np.float64], t_min: float, t_max: float,
    V: NDArray[np.float64], F: NDArray[np.int32],  # noqa: N803
    order: NDArray[np.int32], left: NDArray[np.int32], right: NDArray[np.int32],
    start: NDArray[np.int32], count: NDArray[np.int32], nlo: NDArray[np.float64],
    nhi: NDArray[np.float64],
) -> tuple[NDArray[np.int32], NDArray[np.float64], NDArray[np.float64]]:  # fmt: skip
    n = origins.shape[0]
    face = np.full(n, NO_FACE, np.int32)
    tt = np.full(n, np.inf)
    uv = np.zeros((n, 2))
    stack = np.empty(128, np.int32)
    for ri in range(n):
        o, d = origins[ri], dirs[ri]
        best_t, best_face = t_max, NO_FACE
        top = 0
        stack[0] = 0
        while top >= 0:
            node = stack[top]
            top -= 1
            if not _ray_box(o, d, nlo[node], nhi[node], t_min, best_t):
                continue  # the box is closed, so a tie at best_t still enters
            if left[node] < 0:
                for i in range(start[node], start[node] + count[node]):
                    f = order[i]
                    hit, t, u, v = ray_triangle(o, d, V[F[f, 0]], V[F[f, 1]], V[F[f, 2]])
                    if (
                        hit
                        and t >= t_min
                        and (t < best_t or (t == best_t and (best_face < 0 or f < best_face)))
                    ):
                        best_t, best_face = t, f
                        uv[ri, 0], uv[ri, 1] = u, v
            else:
                top += 1
                stack[top] = right[node]
                top += 1
                stack[top] = left[node]
        if best_face >= 0:
            face[ri], tt[ri] = best_face, best_t
    return face, tt, uv


@kernel_jit
def _overlap(
    alo: NDArray[np.float64], ahi: NDArray[np.float64], blo: NDArray[np.float64],
    bhi: NDArray[np.float64],
) -> bool:  # fmt: skip
    for k in range(3):
        if alo[k] > bhi[k] or blo[k] > ahi[k]:
            return False
    return True


@kernel_jit
def _grow(buf: NDArray[np.int32], used: int) -> NDArray[np.int32]:
    if used < buf.shape[0]:
        return buf
    bigger = np.empty((2 * buf.shape[0], 2), np.int32)
    bigger[:used] = buf[:used]
    return bigger


@kernel_jit
def _self_pairs(
    flo: NDArray[np.float64], fhi: NDArray[np.float64], order: NDArray[np.int32],
    left: NDArray[np.int32], right: NDArray[np.int32], start: NDArray[np.int32],
    count: NDArray[np.int32], nlo: NDArray[np.float64], nhi: NDArray[np.float64],
) -> NDArray[np.int32]:  # fmt: skip
    pairs = np.empty((1024, 2), np.int32)
    used = 0
    sa = np.empty(4096, np.int32)
    sb = np.empty(4096, np.int32)
    top = 0
    sa[0], sb[0] = 0, 0
    while top >= 0:
        a, b = sa[top], sb[top]
        top -= 1
        if a != b and not _overlap(nlo[a], nhi[a], nlo[b], nhi[b]):
            continue
        if left[a] < 0 and left[b] < 0:
            for i in range(start[a], start[a] + count[a]):
                fi = order[i]
                j0 = i + 1 if a == b else start[b]
                for j in range(j0, start[b] + count[b]):
                    fj = order[j]
                    if _overlap(flo[fi], fhi[fi], flo[fj], fhi[fj]):
                        pairs = _grow(pairs, used)
                        pairs[used, 0], pairs[used, 1] = min(fi, fj), max(fi, fj)
                        used += 1
            continue
        if top + 3 >= sa.shape[0]:
            na = np.empty(2 * sa.shape[0], np.int32)
            nb = np.empty(2 * sb.shape[0], np.int32)
            na[: top + 1], nb[: top + 1] = sa[: top + 1], sb[: top + 1]
            sa, sb = na, nb
        if a == b:
            la, ra = left[a], right[a]
            for x, y in ((la, la), (ra, ra), (la, ra)):
                top += 1
                sa[top], sb[top] = x, y
        elif left[a] >= 0 and (left[b] < 0 or count[a] >= count[b]):
            for x in (left[a], right[a]):
                top += 1
                sa[top], sb[top] = x, b
        else:
            for y in (left[b], right[b]):
                top += 1
                sa[top], sb[top] = a, y
    return pairs[:used]


@kernel_jit
def _faces_in_box(
    lo: NDArray[np.float64], hi: NDArray[np.float64], flo: NDArray[np.float64],
    fhi: NDArray[np.float64], order: NDArray[np.int32], left: NDArray[np.int32],
    right: NDArray[np.int32], start: NDArray[np.int32], count: NDArray[np.int32],
    nlo: NDArray[np.float64], nhi: NDArray[np.float64],
) -> NDArray[np.int32]:  # fmt: skip
    out = np.empty(flo.shape[0], np.int32)
    used = 0
    stack = np.empty(128, np.int32)
    top = 0
    stack[0] = 0
    while top >= 0:
        node = stack[top]
        top -= 1
        if not _overlap(lo, hi, nlo[node], nhi[node]):
            continue
        if left[node] < 0:
            for i in range(start[node], start[node] + count[node]):
                f = order[i]
                if _overlap(lo, hi, flo[f], fhi[f]):
                    out[used] = f
                    used += 1
        else:
            top += 1
            stack[top] = right[node]
            top += 1
            stack[top] = left[node]
    return out[:used]


# --- public API -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosestHits:
    face: NDArray[np.int32]  # face_id, NO_FACE for an empty mesh
    sqdist: NDArray[np.float64]
    point: NDArray[np.float64]  # (n, 3) on the surface
    bary: NDArray[np.float64]  # (n, 3) weights of F[face] corners
    feature: NDArray[np.int8]  # FEATURE_*


@dataclass(frozen=True)
class RayHits:
    face: NDArray[np.int32]  # NO_FACE: no hit in [t_min, t_max]
    t: NDArray[np.float64]  # inf when no hit
    uv: NDArray[np.float64]  # (n, 2) Moller-Trumbore u, v (bary = 1 - u - v, u, v)


@dataclass(frozen=True, eq=False)
class Bvh:
    """An immutable BVH over (V, F). Build with ``build_bvh``; ``refit`` after moving vertices."""

    V: NDArray[np.float64]
    F: NDArray[np.int32]
    order: NDArray[np.int32]
    left: NDArray[np.int32]
    right: NDArray[np.int32]
    start: NDArray[np.int32]
    count: NDArray[np.int32]
    node_lo: NDArray[np.float64]
    node_hi: NDArray[np.float64]
    face_lo: NDArray[np.float64]
    face_hi: NDArray[np.float64]

    @property
    def n_nodes(self) -> int:
        return int(self.left.shape[0])

    def _tree(self) -> tuple[Any, ...]:
        return (self.order, self.left, self.right, self.start, self.count,
                self.node_lo, self.node_hi)  # fmt: skip

    def closest_points(self, points: Any) -> ClosestHits:
        q = _points(points, "points")
        if self.F.shape[0] == 0:
            n = q.shape[0]
            return ClosestHits(np.full(n, NO_FACE, np.int32), np.full(n, np.inf),
                               np.full((n, 3), np.nan), np.full((n, 3), np.nan),
                               np.zeros(n, np.int8))  # fmt: skip
        face, sqd, res, feat = _closest_points(q, self.V, self.F, *self._tree())
        return ClosestHits(face, sqd, res[:, 3:6].copy(), res[:, 0:3].copy(), feat)

    def first_hits(
        self, origins: Any, directions: Any, *, t_min: float = 0.0, t_max: float = np.inf
    ) -> RayHits:
        o = _points(origins, "origins")
        d = _points(directions, "directions")
        if o.shape != d.shape:
            raise KernelContractError("origins and directions: same shape required")
        if not (np.isfinite(t_min) and t_min <= t_max):
            raise KernelContractError("ray interval: finite t_min <= t_max required")
        if self.F.shape[0] == 0:
            n = o.shape[0]
            return RayHits(np.full(n, NO_FACE, np.int32), np.full(n, np.inf), np.zeros((n, 2)))
        face, t, uv = _first_hits(o, d, float(t_min), float(t_max), self.V, self.F,
                                  *self._tree())  # fmt: skip
        return RayHits(face, t, uv)

    def self_overlap_pairs(self) -> NDArray[np.int32]:
        """(i, j), i < j, of faces whose closed boxes overlap; sorted (ALG-11 broad phase)."""
        if self.F.shape[0] < 2:
            return np.zeros((0, 2), np.int32)
        p = _self_pairs(self.face_lo, self.face_hi, *self._tree())
        return p[np.lexsort((p[:, 1], p[:, 0]))] if p.shape[0] else p

    def faces_in_box(self, lo: Any, hi: Any) -> NDArray[np.int32]:
        """Sorted ids of the faces whose closed boxes overlap the box [lo, hi]."""
        blo, bhi = (np.asarray(x, np.float64).reshape(3) for x in (lo, hi))
        if self.F.shape[0] == 0:
            return np.zeros(0, np.int32)
        found = _faces_in_box(blo, bhi, self.face_lo, self.face_hi, *self._tree())
        return np.sort(found)

    def refit(self, V: Any) -> "Bvh":  # noqa: N803 - DS-01
        """Same topology, moved vertices: new boxes, same tree (the guard's incremental mode)."""
        v = _vertices(V, self.F)
        if v.shape != self.V.shape:
            raise KernelContractError("refit: same vertex count required")
        flo, fhi = _face_boxes(v, self.F)
        nlo, nhi = _refit_nodes(self.order, self.left, self.right, self.start, self.count,
                                flo, fhi, self.n_nodes)  # fmt: skip
        return Bvh(_frozen(v), self.F, self.order, self.left, self.right, self.start,
                   self.count, _frozen(nlo), _frozen(nhi), _frozen(flo), _frozen(fhi))  # fmt: skip


def _frozen[A: np.ndarray[Any, Any]](a: A) -> A:
    a.setflags(write=False)
    return a


def _points(values: Any, name: str) -> NDArray[np.float64]:
    p = np.ascontiguousarray(values, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3:
        raise KernelContractError(f"{name}: shape (n, 3) required, got {p.shape}")
    if not np.all(np.isfinite(p)):
        raise KernelContractError(f"{name}: values must be finite")
    return p


def _vertices(V: Any, F: NDArray[np.int32]) -> NDArray[np.float64]:  # noqa: N803
    v = _points(V, "V")
    if F.size and (int(F.min()) < 0 or int(F.max()) >= v.shape[0]):
        raise KernelContractError("F: every index must satisfy 0 <= index < n_vertices")
    return v


def build_bvh(V: Any, F: Any, *, leaf_size: int = LEAF_SIZE) -> Bvh:  # noqa: N803 - DS-01
    """Build the BVH of (V float64[n,3], F int32[m,3]); deterministic for equal input."""
    f = np.ascontiguousarray(F, dtype=np.int32)
    if f.ndim != 2 or f.shape[1] != 3:
        raise KernelContractError(f"F: shape (m, 3) required, got {f.shape}")
    if leaf_size < 1:
        raise KernelContractError("leaf_size must be >= 1")
    v = _vertices(V, f)
    if f.shape[0] == 0:
        z = np.zeros(1, np.int32)
        empty = np.zeros((1, 3))
        return Bvh(_frozen(v), _frozen(f), np.zeros(0, np.int32), np.full(1, -1, np.int32),
                   np.full(1, -1, np.int32), z, z.copy(), empty, empty.copy(),
                   np.zeros((0, 3)), np.zeros((0, 3)))  # fmt: skip
    flo, fhi = _face_boxes(v, f)
    order, left, right, start, count, nlo, nhi, n = _build(flo, fhi, leaf_size)
    return Bvh(
        _frozen(v), _frozen(f), _frozen(order), _frozen(left[:n].copy()),
        _frozen(right[:n].copy()), _frozen(start[:n].copy()), _frozen(count[:n].copy()),
        _frozen(nlo[:n].copy()), _frozen(nhi[:n].copy()), _frozen(flo), _frozen(fhi),
    )  # fmt: skip


def warm_up() -> None:
    """Compile (or load from cache) every BVH kernel (X-06 §6.4)."""
    v = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    f = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], np.int32)
    tree = build_bvh(v, f, leaf_size=1)
    tree.closest_points(np.array([[0.2, 0.2, 2.0]]))
    tree.first_hits(np.array([[0.1, 0.1, 5.0]]), np.array([[0.0, 0.0, -1.0]]))
    tree.self_overlap_pairs()
    tree.faces_in_box([0.0, 0.0, 0.0], [0.5, 0.5, 0.5])
    tree.refit(v + 1.0)
