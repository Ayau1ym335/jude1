"""XC-EXP-06 probe, run inside the experiment image.

  probe.py run                      one fresh process: import, JIT (first call), second call,
                                    SHA-256 of every kernel output -> one JSON line
  probe.py series N CPU CACHE       N fresh `run` processes; CPU = host | generic (sets
                                    NUMBA_CPU_NAME=generic); CACHE = cold (empty cache dir per
                                    process) | warm (one shared cache dir; run 1 fills it)

Inputs are synthetic and generated from a fixed PCG64 seed, so they are bit-identical on every
host. Hashes are of raw output bytes (no normalisation): any bit difference counts.
"""

import hashlib
import json
import os
import subprocess
import sys
import time

SEED = 20261119
HERE = os.path.dirname(os.path.abspath(__file__))


def _inputs():
    import numpy as np

    rng = np.random.Generator(np.random.PCG64(SEED))
    n = 20000
    tri = rng.normal(size=(4, n, 3)) * 50.0
    grid = 120
    gx, gy = np.meshgrid(np.arange(grid, dtype=np.float64), np.arange(grid, dtype=np.float64))
    verts = np.column_stack([gx.ravel(), gy.ravel(), rng.normal(size=grid * grid)])
    nbrs = [[] for _ in range(grid * grid)]
    for r in range(grid):
        for c in range(grid):
            i = r * grid + c
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < grid and 0 <= cc < grid:
                    nbrs[i].append(rr * grid + cc)
    ptr = np.zeros(grid * grid + 1, dtype=np.int64)
    ptr[1:] = np.cumsum([len(x) for x in nbrs])
    idx = np.array([j for x in nbrs for j in x], dtype=np.int64)
    xs = np.array([0.0, 0.2, 0.35, 0.6, 0.85, 1.0])
    ys = np.array([1.0, 0.95, 0.7, 0.3, 0.05, 0.0])
    return {
        "ordered_sum": (rng.normal(size=200000) * 1e3,),
        "orient3d_float": (tri[0], tri[1], tri[2], tri[3]),
        "closest_point_triangle": (rng.normal(size=(n, 3)) * 80.0, tri[0], tri[1], tri[2]),
        "transcendental": (rng.normal(size=50000) * 10.0,),
        "laplacian_smooth": (verts, ptr, idx, 0.5, 10),
        "median_split_order": (rng.normal(size=(n, 3)) * 100.0, 8),
        "hermite_profile": (np.linspace(0.0, 1.0, 10001), xs, ys),
    }


def run():
    t0 = time.perf_counter()
    import llvmlite.binding as llvm
    import numba
    import numpy as np

    sys.path.insert(0, HERE)
    import kernels

    import_s = time.perf_counter() - t0
    inputs = _inputs()
    row = {
        "import_s": round(import_s, 6),
        "numba_cpu_name": numba.core.config.CPU_NAME or "host",
        "llvm_host_cpu": llvm.get_host_cpu_name(),
        "cpu_features_sha": hashlib.sha256(
            llvm.get_host_cpu_features().flatten().encode()
        ).hexdigest()[:16],
        "kernels": {},
    }
    jit_total = 0.0
    for name, args in inputs.items():
        fn = getattr(kernels, name)
        t1 = time.perf_counter()
        out = fn(*args)
        first = time.perf_counter() - t1
        t2 = time.perf_counter()
        out2 = fn(*args)
        second = time.perf_counter() - t2
        a = np.ascontiguousarray(out)
        b = np.ascontiguousarray(out2)
        row["kernels"][name] = {
            "first_s": round(first, 6),
            "second_s": round(second, 6),
            "sha": hashlib.sha256(a.tobytes()).hexdigest(),
            "repeat_equal": a.tobytes() == b.tobytes(),
        }
        jit_total += first
    row["first_calls_total_s"] = round(jit_total, 6)
    row["warmup_total_s"] = round(import_s + jit_total, 6)
    return row


def series(n, cpu, cache):
    base_env = dict(os.environ)
    if cpu == "generic":
        base_env["NUMBA_CPU_NAME"] = "generic"
    elif cpu != "host":
        raise SystemExit("CPU must be host or generic")
    for i in range(1, n + 1):
        env = dict(base_env)
        env["NUMBA_CACHE_DIR"] = (
            f"/tmp/numba-cache-{cpu}-warm"
            if cache == "warm"
            else f"/tmp/numba-cache-{cpu}-cold-{i}"
        )
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "run"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        row = json.loads(proc.stdout.strip().splitlines()[-1])
        row.update({"run": i, "cpu_mode": cpu, "cache": cache})
        sys.stdout.write(json.dumps(row) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    if sys.argv[1] == "run":
        sys.stdout.write(json.dumps(run()) + "\n")
    elif sys.argv[1] == "series":
        series(int(sys.argv[2]), sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(__doc__)
