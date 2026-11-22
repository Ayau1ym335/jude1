"""Fixture sets T1-T8 and T10 (FN-OPS-06, DEVELOPMENT_TEST_PLAN §7). T9 is TSK-OPS-04-C.

Every fixture is files + an analytic JSON (``truth``) + the parameters and seed that produced
it. Coordinates are mm. Frame convention of every phantom, stated in its JSON: x = A-P
(+x anterior), y = M-L (+y patient-left), z = inferior-superior (+z superior); right-handed.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import math
import struct
from typing import Any

import numpy as np

from jude_fixtures import analytic as an
from jude_fixtures import formats
from jude_fixtures.geometry import (
    Faces,
    Vec,
    cos_sin,
    dyadic,
    ellipsoid,
    icosphere,
    keep_faces,
    torus,
)
from jude_kernel.core.jarr import encode_mesh
from jude_kernel.core.mesh import Frame, MeshArrays
from jude_kernel.k01_io import write_binary_stl

FRAME_NOTE = {
    "axes": {"x": "A-P, +x anterior", "y": "M-L, +y patient-left", "z": "+z superior"},
    "units": "mm",
    "handedness": "right",
}
HEADER = "JUDE fixture mm"


@dataclass(frozen=True)
class Fixture:
    set: str
    name: str
    files: dict[str, bytes]
    truth: dict[str, Any]
    params: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None

    @property
    def id(self) -> str:
        return f"{self.set}/{self.name}"


def stl(v: Vec, f: Faces) -> bytes:
    """Binary STL via the kernel writer (frame tag only; coordinates are not transformed)."""
    return write_binary_stl(MeshArrays.create(v, f, frame=Frame.F_EXPORT), HEADER).data


def jarr(v: Vec, f: Faces) -> bytes:
    return encode_mesh(MeshArrays.create(v, f, frame=Frame.F_SCAN))


def _rot(cos_sin_pair: tuple[float, float]) -> dict[str, float]:
    return {"cos": cos_sin_pair[0], "sin": cos_sin_pair[1]}


# ---------------------------------------------------------------------------------- T1 ---
ELLIPSOID = (95.0, 75.0, 70.0)  # synthetic semi-axes (mm); not clinical reference values
ASYM_ROT = (24.0 / 25.0, 7.0 / 25.0)  # exact Pythagorean rotation, phi ~ 16.26 deg
SECTION_HEIGHTS = (0.0, 20.0, 40.0)


def t1() -> list[Fixture]:
    out = []
    for s in range(4, 9):
        v, f = icosphere(s, 75.0)
        out.append(
            Fixture(
                "T1",
                f"icosphere_s{s}_r75",
                {"mesh.stl": stl(v, f)},
                {**an.sphere_truth(75.0, s), "frame": FRAME_NOTE},
                {"level": s, "radius": 75.0},
            )
        )
    for s in (4, 6):
        for name, rot in (("ellipsoid", (1.0, 0.0)), ("ellipsoid_asym", ASYM_ROT)):
            v, f = ellipsoid(s, *ELLIPSOID, rot=rot)
            truth = {
                "surface": "ellipsoid",
                "semi_axes": list(ELLIPSOID),
                "rotation_about_z": _rot(rot),
                "volume": an.r9(4.0 / 3.0 * math.pi * ELLIPSOID[0] * ELLIPSOID[1] * ELLIPSOID[2]),
                "centre": [0.0, 0.0, 0.0],
                "mesh": {"n_faces": int(f.shape[0]), "closed": True, "euler": 2},
                "sections": an.ellipsoid_sections(*ELLIPSOID, rot, SECTION_HEIGHTS),
                "frame": FRAME_NOTE,
            }
            out.append(
                Fixture(
                    "T1",
                    f"{name}_s{s}",
                    {"mesh.stl": stl(v, f)},
                    truth,
                    {"level": s, "semi_axes": list(ELLIPSOID), "rotation": _rot(rot)},
                )
            )
    v, f = torus(60.0, 20.0, 96, 48)
    out.append(
        Fixture(
            "T1",
            "torus_R60_r20",
            {"mesh.stl": stl(v, f)},
            {
                "surface": "torus",
                "major_radius": 60.0,
                "minor_radius": 20.0,
                "area": an.r9(4.0 * math.pi**2 * 60.0 * 20.0),
                "volume": an.r9(2.0 * math.pi**2 * 60.0 * 20.0**2),
                "mesh": {
                    "n_vertices": 96 * 48,
                    "n_faces": 2 * 96 * 48,
                    "euler": 0,
                    "genus": 1,
                    "closed": True,
                },
                "frame": FRAME_NOTE,
            },
            {"major": 60.0, "minor": 20.0, "nu": 96, "nv": 48},
        )
    )
    return out


# ---------------------------------------------------------------------------------- T2 ---
def t2() -> list[Fixture]:
    """Open head-like surfaces: ellipsoid caps with different boundaries (closure input)."""
    v, f = ellipsoid(4, *ELLIPSOID)
    centroid_z = (v[f[:, 0], 2] + v[f[:, 1], 2] + v[f[:, 2], 2]) / 3.0
    cx = (v[f[:, 0], 0] + v[f[:, 1], 0] + v[f[:, 2], 0]) / 3.0
    cy = (v[f[:, 0], 1] + v[f[:, 1], 1] + v[f[:, 2], 1]) / 3.0
    tilt = cos_sin(math.radians(15.0))
    ang = np.arctan2(cy, cx)
    wave = np.array([dyadic(5.0 * math.sin(3.0 * a)) for a in ang.tolist()])
    top = (centroid_z > 60.0) & (cx * cx + cy * cy < 8.0**2)
    variants = {
        "cap_planar_z-20": (centroid_z >= -20.0, {"kind": "planar", "plane_z": -20.0}, 1),
        "cap_tilted_15deg": (
            centroid_z * tilt[0] - cx * tilt[1] >= -20.0,
            {"kind": "tilted", "plane": {"normal": [-tilt[1], 0.0, tilt[0]], "offset": -20.0}},
            1,
        ),
        "cap_wavy": (centroid_z >= -20.0 + wave, {"kind": "wavy", "z": "-20 + 5 sin(3 phi)"}, 1),
        "cap_with_top_hole": (
            (centroid_z >= -20.0) & ~top,
            {"kind": "planar + hole near the vertex", "plane_z": -20.0},
            2,
        ),
    }
    out = []
    for name, (keep, boundary, loops) in variants.items():
        sv, sf = keep_faces(v, f, keep)
        out.append(
            Fixture(
                "T2",
                name,
                {"mesh.stl": stl(sv, sf)},
                {
                    "surface": "open ellipsoid cap",
                    "semi_axes": list(ELLIPSOID),
                    "boundary": boundary,
                    "boundary_loops": loops,
                    "watertight": False,
                    "n_faces": int(sf.shape[0]),
                    "closure_expectation": "one cut contour (FN-KOP-06); other loops are refused",
                    "frame": FRAME_NOTE,
                },
                {"level": 4, "cut": boundary},
            )
        )
    return out


# ---------------------------------------------------------------------------------- T3 ---
def t3(seed: int = 3003) -> list[Fixture]:
    """Defect catalogue on a level-2 sphere (320 faces) with seeded, counted defects."""
    rng = np.random.Generator(np.random.PCG64(seed))
    v, f = icosphere(2, 75.0)
    n_v, n_f = v.shape[0], f.shape[0]

    def fx(
        name: str, mv: Vec, mf: Faces, counts: dict[str, Any], extra: dict[str, Any] | None = None
    ) -> Fixture:
        return Fixture(
            "T3",
            name,
            {"mesh.stl": stl(mv, mf), "mesh.jarr": jarr(mv, mf)},
            {"base": "icosphere_s2_r75", "defects": counts, **(extra or {}), "frame": FRAME_NOTE},
            {"base_level": 2},
            seed,
        )

    out = []
    # hole: remove the faces around one vertex (a 5- or 6-ring) -> one boundary loop
    hub = int(rng.integers(0, n_v))
    ring = np.any(f == hub, axis=1)
    hv, hf = keep_faces(v, f, ~ring)
    ring_vertices = sorted(set(f[ring].ravel().tolist()) - {hub})
    out.append(
        fx(
            "hole_one_ring",
            hv,
            hf,
            {"boundary_loops": 1, "hole_vertices": len(ring_vertices)},
            {"removed_faces": int(ring.sum())},
        )
    )
    k = 5
    dup = np.sort(rng.choice(n_f, k, replace=False))
    out.append(fx("duplicate_faces", v, np.concatenate([f, f[dup]]), {"duplicate_faces": k}))
    flip = np.sort(rng.choice(n_f, k, replace=False))
    ff = f.copy()
    ff[flip] = ff[flip][:, [0, 2, 1]]
    out.append(fx("flipped_faces", v, ff, {"flipped_faces": k}))
    # duplicated vertices: copy k vertices and point one incident face at the copy
    dv, df = v.copy(), f.copy()
    chosen: list[int] = []
    touched: set[int] = set()
    for vi in rng.permutation(n_v).tolist():  # pairwise non-adjacent, so loops never merge
        star = set(f[np.any(f == vi, axis=1)].ravel().tolist())
        if vi not in touched and not (star & set(chosen)):
            chosen.append(vi)
            touched |= star
        if len(chosen) == k:
            break
    for vi in sorted(chosen):
        face = int(np.flatnonzero(np.any(df == vi, axis=1))[0])
        dv = np.concatenate([dv, dv[vi : vi + 1]])
        df[face][df[face] == vi] = dv.shape[0] - 1
    out.append(
        fx("duplicate_vertices", dv, df, {"coincident_vertex_pairs": k, "boundary_loops": k})
    )
    # non-manifold edge: a fin triangle on an existing edge
    a, b = int(f[0, 0]), int(f[0, 1])
    fin_v = np.concatenate([v, (v[a : a + 1] + v[b : b + 1]) * 0.75])
    fin_f = np.concatenate([f, np.array([[a, b, n_v]], dtype=np.int32)])
    out.append(fx("nonmanifold_edge", fin_v, fin_f, {"nonmanifold_edges": 1}))
    # non-manifold vertex: point reflection through vertex p gives a sphere centred at 2p that
    # touches the first one only at p (both polyhedra lie inside their balls)
    top = int(rng.integers(0, n_v))
    v2 = 2.0 * v[top] - v
    f2 = f[:, [0, 2, 1]] + n_v  # the reflection flips orientation; swap back to outward
    f2 = np.where(f2 == top + n_v, top, f2).astype(np.int32)
    nm_v = np.concatenate([v, v2])
    out.append(
        fx(
            "nonmanifold_vertex",
            nm_v,
            np.concatenate([f, f2]),
            {"nonmanifold_vertices": 1, "components_by_faces": 1, "unused_vertices": 1},
        )
    )
    # self-intersection: one vertex pushed through the sphere to the far side
    si_v = v.copy()
    pv = int(rng.integers(0, n_v))
    si_v[pv] = -0.5 * si_v[pv]
    out.append(fx("self_intersection", si_v, f, {"self_intersecting": True, "moved_vertex": pv}))
    gv, gf = v * 0.98, f + n_v  # inner offset shell: ghost layer 1.5 mm inside
    out.append(
        fx(
            "ghost_layer",
            np.concatenate([v, gv]),
            np.concatenate([f, gf]),
            {"components": 2, "ghost_layers": 1, "shell_gap_mm": 1.5},
        )
    )
    sv, sf = icosphere(1, 5.0)
    sv = sv + np.array([200.0, 0.0, 0.0])
    out.append(
        fx(
            "extra_component",
            np.concatenate([v, sv]),
            np.concatenate([f, sf + n_v]),
            {"components": 2, "small_component_faces": int(sf.shape[0])},
        )
    )
    deg = np.array([[0, 0, 1], [2, 3, 2], [4, 4, 4]], dtype=np.int32)
    out.append(fx("degenerate_faces", v, np.concatenate([f, deg]), {"degenerate_faces": 3}))
    # files that are not valid meshes
    good = stl(v, f)
    junk = rng.integers(0, 256, 2048, dtype=np.uint8).tobytes()
    files = {
        "empty.stl": (b"", {"expected": "FILE_EMPTY"}),
        "random_bytes.stl": (junk, {"expected": "FILE_UNREADABLE"}),
        "truncated.stl": (
            good[:-37],
            {"expected": "FILE_UNREADABLE", "reason": "size != 84 + 50*count"},
        ),
        "face_bomb.stl": (
            good[:80] + struct.pack("<I", 2**31) + good[84:184],
            {
                "expected": "FILE_UNREADABLE or FACE_LIMIT",
                "reason": "count field claims 2**31 triangles in a 184-byte file",
            },
        ),
    }
    for fname, (data, exp) in files.items():
        out.append(
            Fixture(
                "T3",
                fname.removesuffix(".stl"),
                {fname: data},
                {"defects": exp, "note": "file-level defect"},
                {},
                seed,
            )
        )
    out.append(
        Fixture(
            "T3",
            "oversize_parametric",
            {},
            {
                "defects": {"expected": "FILE_TOO_LARGE"},
                "note": "Generated at test time with jude_fixtures.sets.oversize_stl(size_bytes); "
                "the cap "
                "is a clinic/deployment setting (SEC-07), so no size is fixed here.",
            },
        )
    )
    return out


def oversize_stl(size_bytes: int) -> bytes:
    """A syntactically valid binary STL of at least ``size_bytes`` (T3 oversize, at test time)."""
    m = max(1, (size_bytes - 84 + 49) // 50)
    return b"JUDE oversize".ljust(80, b" ") + struct.pack("<I", m) + bytes(50 * m)


# ---------------------------------------------------------------------------------- T4 ---
def t4() -> list[Fixture]:
    """One object, every supported format. Coordinates on a 2**-10 mm grid so float32 STL and
    decimal text hold the very same values: every import must give equal V and F."""
    v, f = icosphere(2, 75.0)
    v = np.round(v * 1024.0) / 1024.0
    tris = f.tolist()
    quad_v = np.array(
        [
            [0, 0, 0],
            [40, 0, 0],
            [40, 40, 0],
            [0, 40, 0],
            [0, 0, 40],
            [40, 0, 40],
            [40, 40, 40],
            [0, 40, 40],
        ],
        dtype=np.float64,
    )
    quads = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    files = {
        "sphere_binary.stl": stl(v, f),
        "sphere_ascii.stl": formats.ascii_stl(v, f),
        "sphere.obj": formats.obj(v, tris),
        "sphere_negative_indices.obj": formats.obj(v, tris, negative=True),
        "sphere_texture_refs.obj": formats.obj(v, tris, texture=True),
        "sphere_ascii.ply": formats.ply(v, f, "ascii"),
        "sphere_le.ply": formats.ply(v, f, "binary_little_endian"),
        "sphere_be.ply": formats.ply(v, f, "binary_big_endian"),
        "expected_sphere.jarr": jarr(v, f),
        "cube_quads.obj": formats.obj(quad_v, quads),
    }
    return [
        Fixture(
            "T4",
            "format_set",
            files,
            {
                "oracle": "every sphere_* file imports to the V and F of expected_sphere.jarr "
                "(STL: after vertex welding of identical coordinates)",
                "n_vertices": int(v.shape[0]),
                "n_faces": int(f.shape[0]),
                "cube_quads": {
                    "n_vertices": 8,
                    "n_quads": 6,
                    "n_triangles_after_split": 12,
                    "area": 6 * 40.0 * 40.0,
                    "volume": 40.0**3,
                },
                "frame": FRAME_NOTE,
            },
            {"grid": "2**-10 mm"},
        )
    ]


# ------------------------------------------------------------------------------ T5 / T6 ---
def t5() -> list[Fixture]:
    """Laterality object: sphere with a bump on the patient-left (+y) side only."""
    v, f = icosphere(4, 75.0)
    cos_max = cos_sin(math.radians(20.0))[0]
    c = v[:, 1] / 75.0  # cos of the angle to +y
    w = np.where(c > cos_max, (c - cos_max) / (1.0 - cos_max), 0.0)
    v = v * (1.0 + (8.0 / 75.0) * w)[:, None]
    return [
        Fixture(
            "T5",
            "laterality_bump_left",
            {"mesh.stl": stl(v, f)},
            {
                "marker_side": "L",
                "marker_axis": [0.0, 1.0, 0.0],
                "marker_height_mm": 8.0,
                "marker_cone_half_angle_deg": 20,
                "oracle": "the bump appears on the side labelled L, side-specific values come from "
                "+y, "
                "and in the exported STL the bump centroid has y > 0",
                "frame": FRAME_NOTE,
            },
            {"level": 4, "radius": 75.0},
        )
    ]


def t6() -> list[Fixture]:
    v, f = icosphere(4, 75.0)
    return [
        Fixture(
            "T6",
            "sign_sphere_r75",
            {"mesh.stl": stl(v, f)},
            {
                "radius": 75.0,
                "convention": "+m moves the surface along the outward normal (FN-KOP-10)",
                "expected": [{"m": m, "radius_after": 75.0 + m} for m in (-2.0, -0.5, 0.5, 2.0)],
                "note": "magnitudes are test inputs, not clinical values",
                "frame": FRAME_NOTE,
            },
            {"level": 4, "radius": 75.0},
        )
    ]


# ---------------------------------------------------------------------------------- T7 ---
def t7() -> list[Fixture]:
    """Metamorphic transforms. Exact ones keep every double exact (stored as jude-arr, float64)."""
    v, f = ellipsoid(3, *ELLIPSOID, rot=ASYM_ROT)
    transforms: dict[str, tuple[list[list[float]], list[float], bool]] = {
        "rot_z_90": ([[0, -1, 0], [1, 0, 0], [0, 0, 1]], [0, 0, 0], True),
        "rot_x_180": ([[1, 0, 0], [0, -1, 0], [0, 0, -1]], [0, 0, 0], True),
        "cyclic_xyz": ([[0, 0, 1], [1, 0, 0], [0, 1, 0]], [0, 0, 0], True),
        "translate_pow2": ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [256.0, -128.0, 64.0], True),
        "scale_2": ([[2, 0, 0], [0, 2, 0], [0, 0, 2]], [0, 0, 0], True),
        "scale_half": ([[0.5, 0, 0], [0, 0.5, 0], [0, 0, 0.5]], [0, 0, 0], True),
        "unit_cm_to_mm": ([[10, 0, 0], [0, 10, 0], [0, 0, 10]], [0, 0, 0], False),
        "unit_inch_to_mm": ([[25.4, 0, 0], [0, 25.4, 0], [0, 0, 25.4]], [0, 0, 0], False),
    }
    files = {"base.jarr": jarr(v, f)}
    meta = {}
    for name, (m, t, exact) in transforms.items():
        mat = np.array(m, dtype=np.float64)
        tv = np.stack([v @ mat[0], v @ mat[1], v @ mat[2]], axis=1) + np.array(t)
        if not exact and name.startswith("unit_"):
            tv = v / mat[0, 0]  # the file is in the source unit; importer scales it back
        files[f"{name}.jarr"] = jarr(tv, f)
        meta[name] = {"matrix": m, "translation": t, "exact": exact}
    return [
        Fixture(
            "T7",
            "metamorphic_ellipsoid",
            files,
            {
                "base": "ellipsoid_asym level 3",
                "transforms": meta,
                "oracle": "exact transforms: results transform exactly (bit-equal) or are "
                "invariant; "
                "unit_* files hold the base in cm / inch: after unit confirmation they equal "
                "base within DEC-025 (not bit-exact: 25.4 and 1/10 are not dyadic)",
                "frame": FRAME_NOTE,
            },
        )
    ]


# ---------------------------------------------------------------------------------- T8 ---
def t8() -> list[Fixture]:
    return [
        Fixture(
            "T8",
            "hypothesis_profile",
            {},
            {
                "profile": "jude-fixed",
                "settings": {
                    "derandomize": True,
                    "database": None,
                    "max_examples": 200,
                    "deadline": None,
                    "print_blob": True,
                },
                "strategies": "jude_fixtures.t8: face selections on fixture meshes; signed "
                "magnitudes and offsets drawn from an interval the test passes in "
                "(no default values)",
                "oracle": "every generated op yields a valid mesh or an explicit rejection code",
            },
        )
    ]


# --------------------------------------------------------------------------------- T10 ---
def t10() -> list[Fixture]:
    """Export round-trip: an exported STL and corrupted copies with the check that must fire."""
    v, f = icosphere(3, 75.0)
    good = stl(v, f)
    rec = 84  # first triangle record

    def patched(offset: int, fmt: str, value: float | int) -> bytes:
        b = bytearray(good)
        struct.pack_into(fmt, b, offset, value)
        return bytes(b)

    first_x = struct.unpack_from("<f", good, rec + 12)[0]
    lsb = struct.unpack(
        "<f", struct.pack("<I", struct.unpack("<I", struct.pack("<f", first_x))[0] ^ 1)
    )[0]
    swapped = bytearray(good)
    swapped[rec : rec + 50], swapped[rec + 50 : rec + 100] = (
        good[rec + 50 : rec + 100],
        good[rec : rec + 50],
    )
    cases = {
        "export_ok.stl": (good, {}),
        "truncated.stl": (good[:-10], {"size": True}),
        "count_plus_one.stl": (patched(80, "<I", f.shape[0] + 1), {"size": True, "count": True}),
        "vertex_moved_0p5mm.stl": (patched(rec + 12, "<f", first_x + 0.5), {"fidelity": True}),
        "vertex_lsb_flip.stl": (patched(rec + 12, "<f", lsb), {"fidelity": False}),
        "triangles_swapped.stl": (bytes(swapped), {"fidelity": True}),
        "nan_coordinate.stl": (patched(rec + 12, "<f", float("nan")), {"fidelity": True}),
    }
    out = []
    for fname, (data, fires) in cases.items():
        checks = {"size": False, "count": False, "fidelity": False, **fires, "sha256": data != good}
        out.append(
            Fixture(
                "T10",
                fname.removesuffix(".stl"),
                {fname: data},
                {
                    "source": "icosphere_s3_r75 written by FN-KIO-06",
                    "n_triangles": int(f.shape[0]),
                    "checks_that_must_fire": checks,
                    "note": "fidelity = max per-vertex deviation in face order > 1e-4 mm "
                    "(DEC-025); "
                    "a 1-ulp change stays within fidelity but changes the SHA-256",
                },
                {"level": 3, "radius": 75.0},
            )
        )
    return out


# ------------------------------------------------------------------------ T13 / T14 / T15 ---
def t13() -> list[Fixture]:
    """Adversarial predicate inputs (pinned by hash) and their exact signs (committed)."""
    from jude_fixtures.t13 import SEED, inputs_bytes, oracle2d, oracle3d, t13_orient2d, t13_orient3d
    from jude_kernel.core.jarr import encode

    out = []
    for name, gen, oracle, keys in (
        ("orient2d", t13_orient2d, oracle2d, "abc"),
        ("orient3d", t13_orient3d, oracle3d, "abcd"),
    ):
        pts, cats = gen()
        want = oracle(*pts)
        order = list(dict.fromkeys(cats))
        code = np.array([order.index(c) for c in cats], dtype=np.uint8)
        inputs = inputs_bytes(name, pts)
        expected = encode(
            {"sign_plus_1": (want.astype(np.int64) + 1).astype(np.uint8), "category": code},
            {"schema": "t13/1", "predicate": name},
        )
        truth = {
            "predicate": name,
            "convention": "orient2d = sign det[b-a, c-a]; orient3d = sign det[b-a, c-a, d-a] "
            "(FN-KVL-05; opposite of Shewchuk's orient3d)",
            "oracle": "fractions.Fraction (jude_fixtures.t13), independent of the kernel",
            "n_cases": len(cats),
            "category_order": order,
            "category_counts": {c: cats.count(c) for c in order},
            "sign_counts": {str(k): int((want == k).sum()) for k in (-1, 0, 1)},
            "files": {
                "inputs.jarr": "arrays " + ", ".join(keys) + " (float64, n x dim)",
                "expected.jarr": "sign_plus_1 (uint8 = sign + 1), category (uint8)",
            },
        }
        out.append(
            Fixture(
                "T13",
                name,
                {"inputs.jarr": inputs, "expected.jarr": expected},
                truth,
                {"seed": SEED},
                SEED,
            )
        )
    return out


def t14() -> list[Fixture]:
    from jude_fixtures.t14_t15 import CUBE_F, CUBE_V, OCTA_F, OCTA_V, t14_truth

    files = {
        "cube_40.jarr": jarr(np.array(CUBE_V, dtype=np.float64), np.array(CUBE_F, dtype=np.int32)),
        "octahedron_40.jarr": jarr(
            np.array(OCTA_V, dtype=np.float64), np.array(OCTA_F, dtype=np.int32)
        ),
    }
    return [Fixture("T14", "ties", files, {**t14_truth(), "frame": FRAME_NOTE})]


def t15() -> list[Fixture]:
    from jude_fixtures.t14_t15 import contours, t15_truth
    from jude_kernel.core.jarr import encode

    shapes = contours()
    files = {
        "contours.jarr": encode(
            {k: np.array(v, dtype=np.float64) for k, v in shapes.items()}, {"schema": "t15/1"}
        )
    }
    return [Fixture("T15", "contours", files, t15_truth(shapes))]


SETS: dict[str, Callable[[], list[Fixture]]] = {
    "T1": t1,
    "T2": t2,
    "T3": t3,
    "T4": t4,
    "T5": t5,
    "T6": t6,
    "T7": t7,
    "T8": t8,
    "T10": t10,
    "T13": t13,
    "T14": t14,
    "T15": t15,
}
