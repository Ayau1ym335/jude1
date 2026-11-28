"""XC-EXP-01 probe, run inside the experiment image.

  probe.py run              one fresh process -> one JSON line:
                            per (library, phantom): SHA-256 of each raw output array, the time
                            of the first and of the second call, and output sizes
  probe.py series N         N fresh `run` processes, one JSON line each
  probe.py agree            one process -> agreement of libigl / Open3D with the own BVH and
                            the face each library picks at the T14 tie queries (JSON)

Closest point (TQ-05): own BVH (jude_kernel.shared.bvh, XC-SHR-02), libigl
``point_mesh_squared_distance``, Open3D ``RaycastingScene.compute_closest_points``.
Display LOD (TQ-07): fast-simplification ``simplify`` and meshoptimizer ``simplify``, each to a
quarter of the faces.

Inputs are synthetic only: the T1 phantoms (BM-01 series) and the T14 tie fixture, plus query
points from a fixed PCG64 seed (bit-identical on every host). Queries per phantom: every
vertex (each one is an exact tie between all its incident faces, distance 0) and 20 000 points
scattered around the surface. Hashes are of raw output bytes: any bit difference counts.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SEED = 20261127
ROOT = Path(os.environ.get("X01_ROOT", "/opt/x01"))
PHANTOMS = ("icosphere_s4_r75", "icosphere_s6_r75", "ellipsoid_asym_s6", "torus_R60_r20")
N_SCATTER = 20_000
LOD_FRACTION = 0.25


def _numba_cache() -> None:
    """Copy the build-time numba cache to the writable tmpfs (numba needs a writable dir)."""
    import shutil

    src, dst = ROOT / "numba-cache", Path(os.environ["NUMBA_CACHE_DIR"])
    if src.is_dir() and not dst.exists():
        shutil.copytree(src, dst)


def _sha(a) -> str:
    import numpy as np

    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def _load(name: str):
    from jude_kernel.k01_io import detect_bytes, from_soup, parse_stl

    data = (ROOT / "fixtures" / "T1" / name / "mesh.stl").read_bytes()
    soup = parse_stl(data, detect_bytes(data).format, max_faces=2_000_000).soup
    mesh = from_soup(soup, max_faces=2_000_000).mesh
    return mesh.V, mesh.F


def _queries(v):
    import numpy as np

    rng = np.random.Generator(np.random.PCG64(SEED))
    centre = v.mean(axis=0)
    radius = float(np.max(np.linalg.norm(v - centre, axis=1)))
    d = rng.normal(size=(N_SCATTER, 3))
    d /= np.linalg.norm(d, axis=1)[:, None]
    r = rng.uniform(0.3, 1.5, size=N_SCATTER) * radius
    return np.vstack([v, centre + d * r[:, None]])


# --- closest point -------------------------------------------------------------------------------


def own_closest(v, f, q):
    from jude_kernel.shared.bvh import build_bvh

    hits = build_bvh(v, f).closest_points(q)
    return hits.face.astype("<i8"), hits.sqdist, hits.point


def igl_closest(v, f, q):
    import igl
    import numpy as np

    sqd, face, point = igl.point_mesh_squared_distance(q, v, f.astype(np.int64))
    return np.asarray(face, "<i8"), np.asarray(sqd, "<f8"), np.asarray(point, "<f8")


def o3d_closest(v, f, q):
    import numpy as np
    import open3d as o3d

    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(v.astype(np.float32)), o3d.core.Tensor(f.astype(np.uint32)))
    ans = scene.compute_closest_points(o3d.core.Tensor(q.astype(np.float32)))
    point = ans["points"].numpy().astype("<f8")  # float32 -> float64 is exact
    face = ans["primitive_ids"].numpy().astype("<i8")
    sqd = np.sum((point - q) ** 2, axis=1)
    return face, sqd, point


CLOSEST = {"own": own_closest, "libigl": igl_closest, "open3d": o3d_closest}


# --- display LOD ---------------------------------------------------------------------------------


def fs_simplify(v, f):
    import fast_simplification
    import numpy as np

    # the kernel's arrays are read-only; the binding needs writable C arrays
    v2, f2 = fast_simplification.simplify(np.array(v, np.float64), np.array(f, np.int32),
                                          target_reduction=1.0 - LOD_FRACTION)  # fmt: skip
    return v2, f2


def mo_simplify(v, f):
    import meshoptimizer
    import numpy as np

    idx = f.astype(np.uint32).ravel()
    out = np.zeros_like(idx)
    target = int(idx.size * LOD_FRACTION) // 3 * 3
    n = meshoptimizer.simplify(out, idx, v.astype(np.float32), target_index_count=target,
                               target_error=1.0)  # fmt: skip
    return v.astype(np.float32), out[:n].reshape(-1, 3)


LOD = {"fast_simplification": fs_simplify, "meshoptimizer": mo_simplify}


def _same(a: tuple, b: tuple) -> bool:
    import numpy as np

    return all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))


def _timed(fn, *args):
    t0 = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - t0


def run() -> dict:
    t0 = time.perf_counter()
    import fast_simplification  # noqa: F401
    import igl  # noqa: F401
    import meshoptimizer  # noqa: F401
    import open3d  # noqa: F401

    from jude_kernel.shared.warmup import warm_up

    warm_up()
    row: dict = {"import_and_warmup_s": round(time.perf_counter() - t0, 6), "closest": {},
                 "lod": {}}  # fmt: skip
    for name in PHANTOMS:
        v, f = _load(name)
        q = _queries(v)
        for lib, fn in CLOSEST.items():
            first, t1 = _timed(fn, v, f, q)
            second, t2 = _timed(fn, v, f, q)
            row["closest"][f"{lib}/{name}"] = {
                "face": _sha(first[0]), "sqdist": _sha(first[1]), "point": _sha(first[2]),
                "same_in_process": _same(first, second),
                "first_s": round(t1, 6), "second_s": round(t2, 6), "n_queries": int(q.shape[0]),
            }  # fmt: skip
        for lib, fn in LOD.items():
            first, t1 = _timed(fn, v, f)
            second, t2 = _timed(fn, v, f)
            row["lod"][f"{lib}/{name}"] = {
                "V": _sha(first[0]), "F": _sha(first[1]),
                "same_in_process": _same(first, second),
                "first_s": round(t1, 6), "second_s": round(t2, 6),
                "faces_in": int(f.shape[0]), "faces_out": int(first[1].shape[0]),
            }  # fmt: skip
    row["total_s"] = round(time.perf_counter() - t0, 6)
    return row


def agree() -> dict:
    import numpy as np

    from jude_kernel.core import decode_mesh

    out: dict = {"phantoms": {}, "ties": {}}
    for name in PHANTOMS:
        v, f = _load(name)
        q = _queries(v)
        n_vertex = v.shape[0]
        own = own_closest(v, f, q)
        for lib in ("libigl", "open3d"):
            face, sqd, _ = CLOSEST[lib](v, f, q)
            diff = face != own[0]
            # a different face at exactly the same distance is a tie decision, not an error
            tie = diff & (sqd == own[1])
            rel = np.abs(sqd - own[1]) / np.maximum(own[1], 1e-300)
            out["phantoms"][f"{lib}/{name}"] = {
                "faces_differ": int(diff.sum()),
                "faces_differ_at_vertex_queries": int(diff[:n_vertex].sum()),
                "faces_differ_same_sqdist": int(tie.sum()),
                "max_abs_sqdist_diff": float(np.max(np.abs(sqd - own[1]))),
                # distance error in mm, comparable with DEC-025 (e = 0.011 mm)
                "max_abs_dist_diff_mm": float(np.max(np.abs(np.sqrt(sqd) - np.sqrt(own[1])))),
                "max_rel_sqdist_diff_scatter": float(np.max(rel[n_vertex:])),
                "sqdist_bit_equal": int(np.sum(sqd == own[1])),
                "n_queries": int(q.shape[0]),
            }
    spec = json.loads((ROOT / "fixtures" / "T14" / "ties.json").read_text())["closest_point_ties"]
    cube = decode_mesh((ROOT / "fixtures" / "T14" / "ties" / "cube_40.jarr").read_bytes())
    names = sorted(spec["queries"])
    q = np.array([spec["queries"][n]["query"] for n in names], dtype=np.float64)
    for lib, fn in CLOSEST.items():
        face, sqd, _ = fn(cube.V, cube.F, q)
        out["ties"][lib] = {
            n: {"face": int(face[i]), "sqdist": float(sqd[i]),
                "tied": spec["queries"][n]["tied_faces"],
                "rule": spec["queries"][n]["face_by_tie_rule"],
                "in_tie_set": int(face[i]) in spec["queries"][n]["tied_faces"],
                "matches_rule": int(face[i]) == spec["queries"][n]["face_by_tie_rule"]}
            for i, n in enumerate(names)
        }  # fmt: skip
    return out


def series(n: int) -> None:
    for _ in range(n):
        done = subprocess.run([sys.executable, __file__, "run"], capture_output=True, text=True,
                              check=False)  # fmt: skip
        if done.returncode != 0:
            print(json.dumps({"error": done.stderr[-2000:]}), flush=True)
            continue
        print(done.stdout.strip(), flush=True)


if __name__ == "__main__":
    _numba_cache()
    cmd = sys.argv[1]
    if cmd == "run":
        print(json.dumps(run(), sort_keys=True))
    elif cmd == "series":
        series(int(sys.argv[2]))
    elif cmd == "agree":
        print(json.dumps(agree(), sort_keys=True, indent=1))
    else:
        raise SystemExit(f"unknown command {cmd}")
