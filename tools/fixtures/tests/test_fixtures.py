"""CI-FN-OPS-06 / UT-FN-OPS-06: fixtures are reproducible by seed, every fixture has analytic
JSON, and every claim in that JSON is re-derived here with independent code."""

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import struct
from typing import Any

import numpy as np
from numpy.typing import NDArray
import pytest

from jude_fixtures import analytic as an
from jude_fixtures import build, t8
from jude_fixtures.sets import SETS, oversize_stl
from jude_kernel.core.jarr import decode_mesh

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "tests/fixtures"
MANIFEST = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
FX = MANIFEST["fixtures"]


def truth(fid: str) -> dict[str, Any]:
    return json.loads((OUT / FX[fid]["truth"]).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def read_stl(data: bytes) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """Independent binary STL reader; vertices welded by exact coordinates."""
    (m,) = struct.unpack_from("<I", data, 80)
    corners = [struct.unpack_from("<9f", data, 84 + 50 * i + 12) for i in range(m)]
    index: dict[tuple[float, ...], int] = {}
    faces = []
    for c in corners:
        tri = []
        for k in range(3):
            key = c[3 * k : 3 * k + 3]
            tri.append(index.setdefault(key, len(index)))
        faces.append(tri)
    return np.array(list(index), dtype=np.float64), np.array(faces, dtype=np.int64)


def mesh_of(fid: str, fname: str = "mesh.stl") -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    path = OUT / FX[fid]["files"][fname]["path"]
    if not path.exists():
        pytest.skip(f"{path} is generated-only; run `jude-fixtures build`")
    if fname.endswith(".jarr"):
        m = decode_mesh(path.read_bytes())
        return m.V, m.F.astype(np.int64)
    return read_stl(path.read_bytes())


def edge_use(f: NDArray[np.int64]) -> Counter[tuple[int, int]]:
    c: Counter[tuple[int, int]] = Counter()
    for a, b, d in f.tolist():
        for x, y in ((a, b), (b, d), (d, a)):
            c[(x, y)] += 1
    return c


def undirected(f: NDArray[np.int64]) -> Counter[tuple[int, int]]:
    c: Counter[tuple[int, int]] = Counter()
    for (x, y), n in edge_use(f).items():
        c[(min(x, y), max(x, y))] += n
    return c


def boundary_loops(f: NDArray[np.int64]) -> int:
    und = undirected(f)
    bnd = [e for e, n in und.items() if n == 1]
    adj: dict[int, list[int]] = defaultdict(list)
    for a, b in bnd:
        adj[a].append(b)
        adj[b].append(a)
    seen: set[int] = set()
    loops = 0
    for start in adj:
        if start in seen:
            continue
        loops += 1
        stack = [start]
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                stack += adj[x]
    return loops


def components(f: NDArray[np.int64]) -> int:
    parent = list(range(int(f.max()) + 1))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, c in f.tolist():
        parent[find(b)] = find(a)
        parent[find(c)] = find(a)
    return len({find(int(x)) for x in np.unique(f)})


def closed_oriented(f: NDArray[np.int64]) -> bool:
    use = edge_use(f)
    return all(n == 1 and use.get((y, x)) == 1 for (x, y), n in use.items())


# ------------------------------------------------------------------- completion criterion ---
def test_every_fixture_has_analytic_json() -> None:
    sets_seen = {e["set"] for e in FX.values()}
    assert sets_seen == set(SETS)
    for fid, entry in FX.items():
        assert (OUT / entry["truth"]).is_file(), fid
        assert json.loads((OUT / entry["truth"]).read_text(encoding="utf-8")), fid


@pytest.mark.parametrize("set_name", sorted(set(SETS) - {"T1"}))
def test_reproducible_by_seed(set_name: str) -> None:
    assert build.check(OUT, [set_name]) == []


@pytest.mark.determinism
def test_reproducible_t1_including_generated_only_files() -> None:
    assert build.check(OUT, ["T1"]) == []


def test_large_files_are_ignored_not_committed() -> None:
    ignored = (OUT / ".gitignore").read_text(encoding="utf-8")
    for entry in FX.values():
        for meta in entry["files"].values():
            assert (f"/{meta['path']}" in ignored) == (not meta["committed"])


# ---------------------------------------------------------------------------- analytic ---
def test_agm_perimeter_matches_numerical_integration() -> None:
    for a, b in ((75.0, 75.0), (95.0, 75.0), (95.0, 10.0)):
        n = 200_000
        t = np.linspace(0.0, 2.0 * np.pi, n + 1)
        pts = np.stack([a * np.cos(t), b * np.sin(t)], 1)
        chord = float(np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(1)).sum())
        assert abs(an.ellipse_perimeter(a, b) - chord) / chord < 1e-9


def _ray_length(a: float, b: float, rot: tuple[float, float], deg: float) -> float:
    """Chord through the centre at angle deg, by solving the rotated ellipse equation."""
    dx, dy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    cs, sn = rot
    u, w = cs * dx + sn * dy, -sn * dx + cs * dy  # direction in ellipse coordinates
    return 2.0 / math.sqrt((u / a) ** 2 + (w / b) ** 2)


@pytest.mark.parametrize("fid", ["T1/ellipsoid_s4", "T1/ellipsoid_asym_s4", "T1/icosphere_s4_r75"])
def test_section_values_rederived(fid: str) -> None:
    t = truth(fid)
    rot = (
        (t["rotation_about_z"]["cos"], t["rotation_about_z"]["sin"])
        if "rotation_about_z" in t
        else (1.0, 0.0)
    )
    for sec in t["sections"]:
        a, b = sec.get("semi_axes", [t.get("radius"), t.get("radius")])
        ang = np.linspace(0, 2 * np.pi, 400_001)
        x = a * np.cos(ang) * rot[0] - b * np.sin(ang) * rot[1]
        y = a * np.cos(ang) * rot[1] + b * np.sin(ang) * rot[0]
        assert abs(float(x.max() - x.min()) - sec["L"]) < 1e-6
        assert abs(float(y.max() - y.min()) - sec["W"]) < 1e-6
        assert abs(100 * sec["W"] / sec["L"] - sec["CI"]) < 1e-6
        for deg, d in sec["diagonals"].items():
            d1, d2 = _ray_length(a, b, rot, float(deg)), _ray_length(a, b, rot, -float(deg))
            assert abs(d1 - d["D1"]) < 1e-6 and abs(d2 - d["D2"]) < 1e-6
            assert abs(d["CVA"] - abs(d1 - d2)) < 1e-6
            assert abs(d["CVAI_short"] - 100 * abs(d1 - d2) / min(d1, d2)) < 1e-6
            assert abs(d["CVAI_long"] - 100 * abs(d1 - d2) / max(d1, d2)) < 1e-6
    if "asym" in fid:  # the asymmetric phantom really has a diagonal difference
        assert t["sections"][0]["diagonals"]["30"]["CVA"] > 1.0


# ---------------------------------------------------------------------------- T1 / T5 / T6 ---
@pytest.mark.parametrize("fid", ["T1/icosphere_s4_r75", "T6/sign_sphere_r75"])
def test_sphere_mesh_matches_truth(fid: str) -> None:
    v, f = mesh_of(fid)
    t = truth(fid)
    r = np.sqrt((v * v).sum(1))
    assert np.abs(r - t["radius"]).max() < 1e-4  # float32 file
    assert closed_oriented(f)
    assert v.shape[0] - len(undirected(f)) + f.shape[0] == 2
    if "mesh" in t:
        assert (v.shape[0], f.shape[0]) == (t["mesh"]["n_vertices"], t["mesh"]["n_faces"])


@pytest.mark.parametrize("fid", ["T1/ellipsoid_s4", "T1/ellipsoid_asym_s4"])
def test_ellipsoid_vertices_on_surface(fid: str) -> None:
    v, f = mesh_of(fid)
    t = truth(fid)
    a, b, c = t["semi_axes"]
    cs, sn = t["rotation_about_z"]["cos"], t["rotation_about_z"]["sin"]
    x, y = cs * v[:, 0] + sn * v[:, 1], -sn * v[:, 0] + cs * v[:, 1]
    q = (x / a) ** 2 + (y / b) ** 2 + (v[:, 2] / c) ** 2
    assert np.abs(q - 1.0).max() < 3e-6  # float32 rounding of a ~100 mm coordinate
    assert closed_oriented(f) and f.shape[0] == t["mesh"]["n_faces"]


def test_torus_topology() -> None:
    v, f = mesh_of("T1/torus_R60_r20")
    assert closed_oriented(f)
    assert v.shape[0] - len(undirected(f)) + f.shape[0] == 0  # genus 1


def test_laterality_bump_is_on_plus_y() -> None:
    v, _ = mesh_of("T5/laterality_bump_left")
    r = np.sqrt((v * v).sum(1))
    bump = v[r > 75.5]
    assert (
        len(bump) > 0
        and bump[:, 1].min() > 0
        and truth("T5/laterality_bump_left")["marker_side"] == "L"
    )


# ---------------------------------------------------------------------------------- T2 ---
CAPS = ["cap_planar_z-20", "cap_tilted_15deg", "cap_wavy", "cap_with_top_hole"]


@pytest.mark.parametrize("name", CAPS)
def test_open_caps_boundary_loops(name: str) -> None:
    _, f = mesh_of(f"T2/{name}")
    t = truth(f"T2/{name}")
    assert boundary_loops(f) == t["boundary_loops"]
    assert components(f) == 1 and f.shape[0] == t["n_faces"]


# ---------------------------------------------------------------------------------- T3 ---
def test_defect_counts() -> None:
    def m(name: str) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
        return mesh_of(f"T3/{name}", "mesh.jarr")

    v, f = m("hole_one_ring")
    assert boundary_loops(f) == 1
    _, f = m("duplicate_faces")
    assert sum(n - 1 for n in Counter(tuple(sorted(t)) for t in f.tolist()).values()) == 5
    _, f = m("flipped_faces")
    use = edge_use(f)
    assert sum(1 for n in use.values() if n > 1) > 0  # same-direction edges appear
    v, f = m("duplicate_vertices")
    coincident = sum(n - 1 for n in Counter(map(tuple, v.tolist())).values())
    assert coincident == 5 and boundary_loops(f) == 5
    _, f = m("nonmanifold_edge")
    assert sum(1 for n in undirected(f).values() if n > 2) == 1
    v, f = m("nonmanifold_vertex")
    assert components(f) == 1 and len(np.unique(f)) == v.shape[0] - 1
    _, f = m("ghost_layer")
    assert components(f) == 2
    _, f = m("extra_component")
    assert components(f) == 2
    _, f = m("degenerate_faces")
    assert sum(1 for t in f.tolist() if len(set(t)) < 3) == 3


def test_defect_files() -> None:
    def data(name: str, fname: str) -> bytes:
        return bytes((OUT / FX[f"T3/{name}"]["files"][fname]["path"]).read_bytes())

    assert data("empty", "empty.stl") == b""
    t = data("truncated", "truncated.stl")
    assert len(t) != 84 + 50 * struct.unpack_from("<I", t, 80)[0]
    bomb = data("face_bomb", "face_bomb.stl")
    assert struct.unpack_from("<I", bomb, 80)[0] == 2**31 and len(bomb) == 184
    big = oversize_stl(10_000)
    assert len(big) >= 10_000 and len(big) == 84 + 50 * struct.unpack_from("<I", big, 80)[0]


# ---------------------------------------------------------------------------------- T4 ---
def _floats(line: str) -> list[float]:
    return [float(x) for x in line.split()[1:4]]


def test_format_set_encodes_the_same_mesh() -> None:
    files = FX["T4/format_set"]["files"]

    def raw(name: str) -> bytes:
        return bytes((OUT / files[name]["path"]).read_bytes())

    exp = decode_mesh(raw("expected_sphere.jarr"))
    ev = [tuple(p) for p in exp.V.tolist()]
    ef = exp.F.tolist()
    sv, sf = read_stl(raw("sphere_binary.stl"))
    assert sorted(map(tuple, sv.tolist())) == sorted(ev) and len(sf) == len(ef)
    text = raw("sphere_ascii.stl").decode()
    assert [
        tuple(_floats(x.strip())) for x in text.splitlines() if x.strip().startswith("vertex")
    ] == [ev[i] for t in ef for i in t]
    for name in ("sphere.obj", "sphere_negative_indices.obj", "sphere_texture_refs.obj"):
        lines = raw(name).decode().splitlines()
        vs = [tuple(_floats(x)) for x in lines if x.startswith("v ")]
        fs = [
            [int(tok.split("/")[0]) for tok in x.split()[1:]] for x in lines if x.startswith("f ")
        ]
        fs = [[i + len(vs) if i < 0 else i - 1 for i in t] for t in fs]
        assert vs == ev and fs == ef, name
    ply = raw("sphere_ascii.ply").decode().split("end_header\n")[1].splitlines()
    assert [tuple(map(float, x.split())) for x in ply[: len(ev)]] == ev
    for name, order in (("sphere_le.ply", "<"), ("sphere_be.ply", ">")):
        body = raw(name).split(b"end_header\n", 1)[1]
        got = [struct.unpack_from(order + "3d", body, 24 * i) for i in range(len(ev))]
        tris = [
            struct.unpack_from(order + "B3i", body, 24 * len(ev) + 13 * j)[1:]
            for j in range(len(ef))
        ]
        assert got == ev and [list(t) for t in tris] == ef, name


# --------------------------------------------------------------------------------- T10 ---
T10 = sorted(re.sub(r"^T10/", "", k) for k in FX if k.startswith("T10/"))


@pytest.mark.parametrize("name", T10)
def test_corruptions_trip_the_declared_checks(name: str) -> None:
    good = (OUT / FX["T10/export_ok"]["files"]["export_ok.stl"]["path"]).read_bytes()
    data = (OUT / FX[f"T10/{name}"]["files"][f"{name}.stl"]["path"]).read_bytes()
    want = truth(f"T10/{name}")["checks_that_must_fire"]
    count = struct.unpack_from("<I", data, 80)[0]
    n = truth(f"T10/{name}")["n_triangles"]
    size_bad = len(data) != 84 + 50 * count
    count_bad = count != n
    fidelity_bad = False
    if not size_bad:
        for i in range(min(count, n)):
            a = struct.unpack_from("<9f", data, 84 + 50 * i + 12)
            b = struct.unpack_from("<9f", good, 84 + 50 * i + 12)
            if any(not math.isfinite(x) or abs(x - y) > 1e-4 for x, y in zip(a, b, strict=True)):
                fidelity_bad = True
    assert (size_bad, count_bad, fidelity_bad, data != good) == (
        want["size"],
        want["count"],
        want["fidelity"],
        want["sha256"],
    )


# ---------------------------------------------------------------------------------- T8 ---
def test_t8_profile_and_strategies() -> None:
    from hypothesis import given, settings

    t8.register()
    assert settings.get_profile(t8.PROFILE).derandomize is True
    seen: list[tuple[list[int], float]] = []

    @t8.fixed
    @given(t8.face_selection(320, max_size=10), t8.signed_value(-1.5, 2.0))
    def probe(sel: list[int], value: float) -> None:
        assert sel == sorted(set(sel)) and all(0 <= i < 320 for i in sel)
        assert -1.5 <= value <= 2.0
        seen.append((sel, value))

    probe()
    first = list(seen)
    seen.clear()
    probe()
    assert seen == first  # derandomized: the same examples every run
    with pytest.raises(ValueError):
        t8.signed_value(1.0, 1.0)
