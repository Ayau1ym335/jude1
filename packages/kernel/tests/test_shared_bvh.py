"""UT-bvh / GT-bvh: the deterministic AABB BVH (XC-SHR-02; IDR-10, ALG-11/33/34).

Completion criterion: equals a brute-force oracle on 10^4 random queries, including ties;
100-run determinism; build and query times recorded (BM-01, performance stage).

The oracle visits every face with the same triangle primitive, so it checks the tree itself:
build, pruning, traversal order and the tie rule. The triangle primitives are checked
separately against an independent formulation (projection plus edge clamping). Test inputs come
from a deterministic Halton sequence; the kernel bans randomness, its tests too.
"""

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core import KernelContractError, decode_mesh
from jude_kernel.shared.bvh import (
    FEATURE_EDGE_AB,
    FEATURE_EDGE_AC,
    FEATURE_EDGE_BC,
    FEATURE_FACE,
    FEATURE_VERTEX_A,
    FEATURE_VERTEX_B,
    FEATURE_VERTEX_C,
    NO_FACE,
    Bvh,
    build_bvh,
    closest_point_triangle,
    ray_triangle,
)
from jude_kernel.shared.jit import kernel_jit

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
F64 = NDArray[np.float64]
I32 = NDArray[np.int32]
STL_RECORD = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23)


def read_stl(path: Path) -> tuple[F64, I32]:
    """Test-side binary STL reader (the kernel parser is TSK-KIO-02-K); identical points welded."""
    data = path.read_bytes()
    n = int(np.frombuffer(data, "<u4", 1, 80)[0])
    rec = np.frombuffer(data, STL_RECORD, n, 84)
    pts = rec["v"].reshape(-1, 3).astype(np.float64)
    verts, inverse = np.unique(pts, axis=0, return_inverse=True)
    return verts, inverse.reshape(-1, 3).astype(np.int32)


def halton(n: int, dims: int, skip: int = 1) -> F64:
    """Deterministic low-discrepancy points in [0, 1)^dims (radical inverse in prime bases)."""
    out = np.zeros((n, dims))
    idx = np.arange(skip, skip + n)
    for d in range(dims):
        base, f, i = PRIMES[d], 1.0, idx.copy()
        while np.any(i > 0):
            f /= base
            out[:, d] += f * (i % base)
            i //= base
    return out


def t14_cube() -> Any:
    return decode_mesh((FIXTURES / "T14" / "ties" / "cube_40.jarr").read_bytes())


def sphere_mesh() -> tuple[F64, I32]:
    return read_stl(FIXTURES / "T1" / "icosphere_s4_r75" / "mesh.stl")


# --- brute-force oracles (every face, same primitive, explicit tie rule) --------------------------


@kernel_jit
def _brute_closest(q: F64, v: F64, f: I32) -> tuple[I32, F64]:
    n = q.shape[0]
    face = np.full(n, -1, np.int32)
    sqd = np.full(n, np.inf)
    tmp = np.empty(6)
    for qi in range(n):
        for fi in range(f.shape[0]):
            d2, _ = closest_point_triangle(q[qi], v[f[fi, 0]], v[f[fi, 1]], v[f[fi, 2]], tmp)
            if d2 < sqd[qi] or (d2 == sqd[qi] and fi < face[qi]):
                sqd[qi], face[qi] = d2, fi
    return face, sqd


@kernel_jit
def _brute_rays(o: F64, d: F64, t_min: float, t_max: float, v: F64, f: I32) -> tuple[I32, F64]:
    n = o.shape[0]
    face = np.full(n, -1, np.int32)
    tt = np.full(n, np.inf)
    for ri in range(n):
        best = t_max
        for fi in range(f.shape[0]):
            hit, t, _, _ = ray_triangle(o[ri], d[ri], v[f[fi, 0]], v[f[fi, 1]], v[f[fi, 2]])
            closer = t < best or (t == best and (face[ri] < 0 or fi < face[ri]))
            if hit and t >= t_min and closer:
                best, face[ri] = t, fi
        if face[ri] >= 0:
            tt[ri] = best
    return face, tt


brute_closest: Callable[[F64, F64, I32], tuple[I32, F64]] = _brute_closest
brute_rays: Callable[[F64, F64, float, float, F64, I32], tuple[I32, F64]] = _brute_rays


def queries(v: F64, f: I32, n: int) -> F64:
    """Off-surface points at many scales, on-surface points, near-surface and tie-prone points."""
    lo, hi = v.min(axis=0), v.max(axis=0)
    span = hi - lo
    k = n // 5
    h = halton(5 * k, 3)
    far = lo - 2 * span + h[:k] * 5 * span
    near_box = lo + h[k : 2 * k] * span
    tri = f[(h[2 * k : 3 * k, 0] * f.shape[0]).astype(int)]
    a, b = h[2 * k : 3 * k, 1:2], h[2 * k : 3 * k, 2:3]
    a, b = np.where(a + b > 1, 1 - a, a), np.where(a + b > 1, 1 - b, b)
    on_surface = (1 - a - b) * v[tri[:, 0]] + a * v[tri[:, 1]] + b * v[tri[:, 2]]
    jitter = on_surface + (h[3 * k : 4 * k] - 0.5) * span.max() * 2e-3
    pick_v = (h[4 * k : 5 * k, 0] * v.shape[0]).astype(int)
    pick_e = (h[4 * k : 5 * k, 1] * f.shape[0]).astype(int)
    ties = np.vstack([v[pick_v[: k // 2]],  # vertices: several faces at distance 0
                      (v[f[pick_e[k // 2 :], 0]] + v[f[pick_e[k // 2 :], 1]]) / 2])  # fmt: skip
    return np.vstack([far, near_box, on_surface, jitter, ties])


# --- completion criterion ----------------------------------------------------------------------


@pytest.mark.parametrize("leaf_size", [1, 4, 16])
def test_completion_criterion_t14_ties_follow_the_rule(leaf_size: int) -> None:
    cube = t14_cube()
    tree = build_bvh(cube.V, cube.F, leaf_size=leaf_size)
    cases = json.loads((FIXTURES / "T14" / "ties.json").read_text())["closest_point_ties"]
    for name, case in cases["queries"].items():
        hits = tree.closest_points(np.array([case["query"]], float))
        assert int(hits.face[0]) == case["face_by_tie_rule"], name
        assert float(hits.sqdist[0]) == float(case["distance_squared"]), name


@pytest.mark.parametrize("mesh", ["icosphere_s4_r75", "torus_R60_r20"])
def test_completion_criterion_closest_point_equals_brute_force_on_10k_queries(mesh: str) -> None:
    v, f = read_stl(FIXTURES / "T1" / mesh / "mesh.stl")
    q = queries(v, f, 10_000)
    assert q.shape[0] == 10_000
    hits = build_bvh(v, f).closest_points(q)
    face, sqd = brute_closest(q, v, f)
    assert np.array_equal(hits.face, face)  # exact, the tie rule included
    assert np.array_equal(hits.sqdist, sqd)
    # ties really occur in the set: vertex queries have several faces at distance 0
    tmp = np.empty(6)
    tied = 0
    for qq in q[-200:]:
        d = [closest_point_triangle(qq, v[t[0]], v[t[1]], v[t[2]], tmp)[0] for t in f]
        tied += int(np.count_nonzero(np.array(d) == min(d)) > 1)
    assert tied > 50


def test_completion_criterion_cube_ties_on_10k_lattice_queries() -> None:
    cube = t14_cube()
    lattice = np.floor(halton(10_000, 3) * 9 - 2) * 10.0  # -20 .. 60 step 10: many exact ties
    tree = build_bvh(cube.V, cube.F, leaf_size=1)
    face, sqd = brute_closest(lattice, cube.V, cube.F)
    hits = tree.closest_points(lattice)
    assert np.array_equal(hits.face, face) and np.array_equal(hits.sqdist, sqd)


@pytest.mark.determinism
def test_completion_criterion_100_run_determinism() -> None:
    v, f = sphere_mesh()
    q = queries(v, f, 1000)
    o, d = np.zeros((500, 3)), halton(500, 3) - 0.5
    digests = set()
    for _ in range(100):
        tree = build_bvh(v, f)
        hits, rays = tree.closest_points(q), tree.first_hits(o, d)
        h = hashlib.sha256()
        for a in (tree.order, tree.left, tree.right, tree.node_lo, tree.node_hi, hits.face,
                  hits.sqdist, hits.point, hits.bary, rays.face, rays.t, rays.uv,
                  tree.self_overlap_pairs()):  # fmt: skip
            h.update(np.ascontiguousarray(a).tobytes())
        digests.add(h.hexdigest())
    assert len(digests) == 1


@pytest.mark.performance
def test_completion_criterion_build_and_query_times_are_recorded() -> None:
    """BM-01: build and query times per mesh size, written to the performance report."""
    rows: list[dict[str, Any]] = []
    build_bvh(np.eye(3), np.array([[0, 1, 2]], np.int32)).closest_points(np.zeros((1, 3)))
    for mesh in ("icosphere_s5_r75", "icosphere_s6_r75", "icosphere_s7_r75", "icosphere_s8_r75"):
        v, f = read_stl(FIXTURES / "T1" / mesh / "mesh.stl")
        q = queries(v, f, 10_000)
        t0 = time.perf_counter()
        tree = build_bvh(v, f)
        t1 = time.perf_counter()
        tree.closest_points(q)
        t2 = time.perf_counter()
        rows.append({"mesh": mesh, "faces": int(f.shape[0]), "build_s": round(t1 - t0, 4),
                     "queries": int(q.shape[0]), "query_s": round(t2 - t1, 4)})  # fmt: skip
    out = Path(os.environ.get("JUDE_CI_REPORTS", "reports")) / "perf" / "bvh_bm01.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"benchmark": "BM-01 bvh", "rows": rows}, indent=1), "utf-8")
    assert all(r["build_s"] > 0 and r["query_s"] > 0 for r in rows)


# --- triangle primitives vs an independent formulation -------------------------------------------


def independent_sqdist(p: F64, tri: F64) -> float:
    """Squared distance by projection onto the plane, else the nearest of the three edges."""
    a, b, c = tri
    n = np.cross(b - a, c - a)
    nn = float(n @ n)
    best = np.inf
    if nn > 0:
        proj = p - float((p - a) @ n) / nn * n
        sides = [float(np.dot(np.cross(y - x, proj - x), n)) for x, y in ((a, b), (b, c), (c, a))]
        if min(sides) >= 0:
            best = float((p - proj) @ (p - proj))
    for x, y in ((a, b), (b, c), (c, a)):
        e = y - x
        ee = float(e @ e)
        s = min(max(float((p - x) @ e) / ee, 0.0), 1.0) if ee > 0 else 0.0
        dd = p - (x + s * e)
        best = min(best, float(dd @ dd))
    return best


ZERO_WEIGHTS = {FEATURE_VERTEX_A: (1, 2), FEATURE_VERTEX_B: (0, 2), FEATURE_VERTEX_C: (0, 1),
                FEATURE_EDGE_AB: (2,), FEATURE_EDGE_AC: (1,), FEATURE_EDGE_BC: (0,),
                FEATURE_FACE: ()}  # fmt: skip


def test_closest_point_triangle_matches_an_independent_formulation() -> None:
    h = (halton(3000, 9) - 0.5) * 200.0
    out = np.empty(6)
    for row in h:
        tri, p = row[:9].reshape(3, 3), row[[4, 0, 8]] * 1.6
        d2, feature = closest_point_triangle(p, tri[0], tri[1], tri[2], out)
        assert d2 == pytest.approx(independent_sqdist(p, tri), rel=1e-9, abs=1e-9)
        w = out[:3]
        assert np.all(w >= -1e-12) and float(w.sum()) == pytest.approx(1.0, abs=1e-12)
        assert np.allclose(w @ tri, out[3:6], rtol=0, atol=1e-9)
        assert all(w[i] == 0.0 for i in ZERO_WEIGHTS[feature])


def test_degenerate_triangles_are_their_edges() -> None:
    out = np.empty(6)
    a, b, c = np.array([0.0, 0, 0]), np.array([10.0, 0, 0]), np.array([20.0, 0, 0])  # collinear
    d2, feature = closest_point_triangle(np.array([15.0, 5.0, 0.0]), a, b, c, out)
    assert d2 == 25.0 and feature in (FEATURE_EDGE_AC, FEATURE_EDGE_BC)
    d2, _ = closest_point_triangle(np.array([3.0, 4.0, 0.0]), a, a, a, out)  # a point
    assert d2 == 25.0 and np.array_equal(out[3:6], a)


# --- rays -----------------------------------------------------------------------------------------


def test_first_hits_equal_brute_force_including_ties() -> None:
    v, f = sphere_mesh()
    n = 4000
    h = halton(n, 6)
    origins = np.vstack([np.zeros((n // 2, 3)), (h[n // 2 :, :3] - 0.5) * 400])
    dirs = h[:, 3:] - 0.5
    dirs[: n // 8] = v[(h[: n // 8, 0] * v.shape[0]).astype(int)]  # through vertices: ties
    hits = build_bvh(v, f).first_hits(origins, dirs)
    face, tt = brute_rays(origins, dirs, 0.0, np.inf, v, f)
    assert np.array_equal(hits.face, face) and np.array_equal(hits.t, tt)
    assert np.count_nonzero(hits.face >= 0) > n // 2


def test_ray_edge_cases_on_the_cube() -> None:
    cube = t14_cube()
    tree = build_bvh(cube.V, cube.F, leaf_size=1)
    o = np.array([[20.0, 20, 100], [20.0, 20, 100], [100.0, 20, 20], [20.0, 20, 20]])
    d = np.array([[0.0, 0, -1], [1.0, 0, 0], [0.0, 1, 0], [0.0, 0, 1]])
    hits = tree.first_hits(o, d)
    face, tt = brute_rays(o, d, 0.0, np.inf, cube.V, cube.F)
    assert np.array_equal(hits.face, face) and np.array_equal(hits.t, tt)
    assert hits.t[0] == 60.0  # through the top diagonal: a tie, smallest face_id
    assert hits.face[1] == NO_FACE and np.isinf(hits.t[1])  # misses the cube
    assert hits.face[2] == NO_FACE  # never meets a face it is not parallel to
    assert hits.t[3] == 20.0  # from inside
    assert tree.first_hits(o[:1], d[:1], t_min=0.0, t_max=59.0).face[0] == NO_FACE


# --- box pairs and box queries --------------------------------------------------------------------


def brute_pairs(lo: F64, hi: F64) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for i in range(lo.shape[0]):
        ok = np.all((lo[i] <= hi[i + 1 :]) & (lo[i + 1 :] <= hi[i]), axis=1)
        pairs.update((i, i + 1 + int(j)) for j in np.nonzero(ok)[0])
    return pairs


@pytest.mark.parametrize("leaf_size", [1, 4])
def test_self_overlap_pairs_equal_brute_force(leaf_size: int) -> None:
    v, f = read_stl(FIXTURES / "T1" / "torus_R60_r20" / "mesh.stl")
    tree = build_bvh(v, f, leaf_size=leaf_size)
    pairs = tree.self_overlap_pairs()
    assert {(int(a), int(b)) for a, b in pairs} == brute_pairs(tree.face_lo, tree.face_hi)
    assert np.all(pairs[:, 0] < pairs[:, 1])
    assert np.array_equal(pairs, pairs[np.lexsort((pairs[:, 1], pairs[:, 0]))])  # sorted


def test_faces_in_box_and_refit() -> None:
    v, f = sphere_mesh()
    tree = build_bvh(v, f)
    lo, hi = np.array([0.0, 0, 0]), np.array([40.0, 30, 75])
    expect = np.nonzero(np.all((tree.face_lo <= hi) & (lo <= tree.face_hi), axis=1))[0]
    assert np.array_equal(tree.faces_in_box(lo, hi), expect)
    # refit after moving vertices answers like a fresh build (same tree topology)
    moved = v * np.array([1.2, 0.9, 1.1]) + np.sin(v) * 0.5
    refit, fresh = tree.refit(moved), build_bvh(moved, f)
    assert np.array_equal(refit.order, tree.order)
    q = queries(moved, f, 2000)
    a, b = refit.closest_points(q), fresh.closest_points(q)
    assert np.array_equal(a.face, b.face) and np.array_equal(a.sqdist, b.sqdist)
    refit_pairs = {(int(x), int(y)) for x, y in refit.self_overlap_pairs()}
    assert refit_pairs == brute_pairs(refit.face_lo, refit.face_hi)


# --- contract -------------------------------------------------------------------------------------


TRI = np.array([[0, 1, 2]])


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda: build_bvh(np.zeros((3, 2)), TRI), "shape"),
        (lambda: build_bvh(np.full((3, 3), np.nan), TRI), "finite"),
        (lambda: build_bvh(np.zeros((3, 3)), np.array([[0, 1, 3]])), "index"),
        (lambda: build_bvh(np.zeros((3, 3)), TRI, leaf_size=0), "leaf"),
        (lambda: build_bvh(np.eye(3), TRI).closest_points([[np.inf, 0, 0]]), "finite"),
        (lambda: build_bvh(np.eye(3), TRI).first_hits([[0, 0, 0]], [[1, 0]]), "shape"),
    ],
)
def test_contract(call: Callable[[], Any], match: str) -> None:
    with pytest.raises(KernelContractError, match=match):
        call()


def test_empty_mesh() -> None:
    tree: Bvh = build_bvh(np.zeros((0, 3)), np.zeros((0, 3), np.int32))
    hits = tree.closest_points([[1.0, 2.0, 3.0]])
    assert hits.face[0] == NO_FACE and np.isinf(hits.sqdist[0])
    assert tree.first_hits([[0.0, 0, 0]], [[0.0, 0, 1]]).face[0] == NO_FACE
    assert tree.self_overlap_pairs().shape == (0, 2)
    assert tree.faces_in_box([0, 0, 0], [1, 1, 1]).size == 0
