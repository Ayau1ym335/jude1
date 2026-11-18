"""XC-EXP-08 probe, run inside the experiment image.

  probe.py smoke  -> one JSON line: import times and a minimal working call per library
  probe.py soup   -> JSON: Python, platform, every installed distribution with licence,
                     numpy BLAS configuration, Debian packages of the WeasyPrint stack

Each `smoke` call is a fresh process, so import and JIT times are cold-process times.
Synthetic inputs only.
"""

import importlib
import importlib.metadata as md
import json
import platform
import subprocess
import sys
import time


def _timed_import(name: str) -> float:
    t0 = time.perf_counter()
    importlib.import_module(name)
    return time.perf_counter() - t0


def smoke() -> dict[str, object]:
    out: dict[str, object] = {}
    for mod in ("numpy", "scipy.sparse.csgraph", "numba", "fast_simplification", "weasyprint"):
        out[f"import_{mod.split('.')[0]}_s"] = round(_timed_import(mod), 6)

    import numpy as np
    from scipy.sparse import coo_array
    from scipy.sparse.csgraph import connected_components

    a = np.arange(9, dtype=np.float64).reshape(3, 3)
    out["numpy_matmul_ok"] = bool((a @ np.eye(3) == a).all())

    rows, cols = np.array([0, 1, 3]), np.array([1, 2, 4])
    graph = coo_array((np.ones(3), (rows, cols)), shape=(5, 5))
    n_comp, _ = connected_components(graph, directed=False)
    out["scipy_components_ok"] = int(n_comp) == 2

    import numba

    @numba.njit(fastmath=False, parallel=False, cache=False)
    def ordered_sum(x: np.ndarray) -> float:  # fixed summation order (TD-19)
        s = 0.0
        for v in x:
            s += v
        return s

    xs = np.linspace(0.0, 1.0, 1001)
    t0 = time.perf_counter()
    first = ordered_sum(xs)
    out["numba_first_call_s"] = round(time.perf_counter() - t0, 6)
    t0 = time.perf_counter()
    second = ordered_sum(xs)
    out["numba_second_call_s"] = round(time.perf_counter() - t0, 6)
    out["numba_ok"] = first == second == sum(xs.tolist())

    import fast_simplification

    # 40x40 vertex grid -> 2 * 39 * 39 triangles
    g = np.stack(np.meshgrid(np.arange(40.0), np.arange(40.0)), -1).reshape(-1, 2)
    pts = np.column_stack([g, np.zeros(len(g))])
    idx = np.arange(1600).reshape(40, 40)
    q = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    tris = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]]).astype(np.int32)
    t0 = time.perf_counter()
    _, f2 = fast_simplification.simplify(pts, tris, target_reduction=0.5)
    out["fastsimp_s"] = round(time.perf_counter() - t0, 6)
    out["fastsimp_ok"] = 0 < len(f2) < len(tris)

    from weasyprint import HTML

    t0 = time.perf_counter()
    pdf = HTML(string="<p>Синтетический отчёт: геометрическая проверка</p>").write_pdf()
    out["weasyprint_pdf_s"] = round(time.perf_counter() - t0, 6)
    out["weasyprint_ok"] = isinstance(pdf, bytes) and pdf.startswith(b"%PDF-")
    out["all_ok"] = all(v for k, v in out.items() if k.endswith("_ok"))
    return out


def _licence(dist: md.Distribution) -> str:
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr
    classifiers = [
        c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    lic = (meta.get("License") or "").strip().splitlines()
    return lic[0][:80] if lic else "UNKNOWN"


def soup() -> dict[str, object]:
    import numpy as np

    dists = sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower())
    deb = subprocess.run(  # fixed argv, absolute path; experiment image only
        [
            "/usr/bin/dpkg-query",
            "-W",
            "-f=${Package}\t${Version}\n",
            "libpango-1.0-0",
            "libpangoft2-1.0-0",
            "libharfbuzz-subset0",
            "libharfbuzz0b",
            "libfontconfig1",
            "libfreetype6",
            "fonts-dejavu-core",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    blas = np.show_config(mode="dicts").get("Build Dependencies", {}).get("blas", {})
    return {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "libc": "-".join(platform.libc_ver()),
        "packages": [
            {"name": d.metadata["Name"], "version": d.version, "licence": _licence(d)}
            for d in dists
        ],
        "debian": [line.split("\t") for line in deb.splitlines() if line],
        "numpy_blas": {k: blas.get(k) for k in ("name", "version", "openblas configuration")},
    }


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    sys.stdout.write(json.dumps(smoke() if mode == "smoke" else soup(), ensure_ascii=False) + "\n")
