"""UT-FN-KIO-06: binary STL writer (TSK-KIO-06-K; ALG-06, TD-21, DEC-025).

Completion criterion: file size = 84 + 50*M; triangle count equal; vertex deviation <= 1e-4 mm
on re-read. Re-reading uses ``read_back`` below, an independent struct-based parser that shares
no code with the writer (the oracle second reader of ALG-06 joins in TSK-KIO-06-V).
"""

import hashlib
import math
import struct
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
import pytest

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import Frame, MeshArrays
from jude_kernel.k01_io import StlBytes, stl_header, write_binary_stl

FILE_FIDELITY_MM = 1e-4  # DEC-025
HEADER = stl_header("0.0.0", "J-0123ABCD", 1)


def read_back(data: bytes) -> tuple[bytes, list[tuple[tuple[float, ...], ...]], list[int]]:
    """Independent reader: header, per-triangle (normal, v0, v1, v2), attributes."""
    header = data[:80]
    (count,) = struct.unpack_from("<I", data, 80)
    tris, attrs = [], []
    for i in range(count):
        vals = struct.unpack_from("<12fH", data, 84 + 50 * i)
        tris.append(tuple(tuple(vals[k : k + 3]) for k in range(0, 12, 3)))
        attrs.append(vals[12])
    return header, tris, attrs


def mesh(v: Any, f: list[list[int]]) -> MeshArrays:
    return MeshArrays.create(np.asarray(v, dtype=np.float64), np.asarray(f), frame=Frame.F_EXPORT)


def octa_sphere(level: int, radius: float = 75.0) -> MeshArrays:
    """Deterministic sphere-like test mesh: subdivided octahedron projected to a sphere."""
    v = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
    f = [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]]
    verts = [np.array(p, dtype=np.float64) for p in v]
    for _ in range(level):
        mid: dict[tuple[int, int], int] = {}
        nf = []
        for a, b, c in f:
            ids = []
            for x, y in ((a, b), (b, c), (c, a)):
                key = (min(x, y), max(x, y))
                if key not in mid:
                    p = verts[x] + verts[y]
                    verts.append(p / math.sqrt(float(p @ p)))
                    mid[key] = len(verts) - 1
                ids.append(mid[key])
            ab, bc, ca = ids
            nf += [[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]]
        f = nf
    return mesh(np.array(verts) * radius, f)


def test_known_triangle_gives_known_bytes() -> None:
    out = write_binary_stl(mesh([[0, 0, 0], [10, 0, 0], [0, 20, 0]], [[0, 1, 2]]), "JUDE test")
    expected = (
        b"JUDE test".ljust(80, b" ")
        + struct.pack("<I", 1)
        + struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 10, 0, 0, 0, 20, 0, 0)
    )
    assert out.data == expected
    assert out.sha256 == hashlib.sha256(expected).hexdigest()
    assert out.n_triangles == 1


def test_size_count_header_and_attributes() -> None:
    m = octa_sphere(3)
    out = write_binary_stl(m, HEADER)
    assert len(out.data) == 84 + 50 * m.n_faces
    header, tris, attrs = read_back(out.data)
    assert len(tris) == m.n_faces == out.n_triangles
    assert header == b"JUDE 0.0.0 J-0123ABCD v1 mm F_export".ljust(80, b" ")
    assert set(attrs) == {0}


def _max_dev(m: MeshArrays, data: bytes) -> tuple[float, bool]:
    """Max |v_file - v| over all triangle corners, and whether each is <= half a float32 ulp."""
    _, tris, _ = read_back(data)
    worst, within_half_ulp = 0.0, True
    for (_, *corners), face in zip(tris, m.F, strict=True):
        for got, idx in zip(corners, face, strict=True):
            for g, x in zip(got, m.V[idx], strict=True):
                d = abs(g - float(x))
                worst = max(worst, d)
                within_half_ulp &= d <= float(np.spacing(np.float32(abs(x)))) / 2 or d == 0.0
    return worst, within_half_ulp


def test_completion_criterion_on_reference_sphere() -> None:
    m = octa_sphere(5)  # 8192 triangles, R = 75 mm
    out = write_binary_stl(m, HEADER)
    worst, half_ulp = _max_dev(m, out.data)
    assert len(out.data) == 84 + 50 * 8192
    assert half_ulp
    assert worst <= 7.6e-6 < FILE_FIDELITY_MM  # TD-21 bound for |x| <= 128 mm


coord = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(coord, coord, coord), min_size=3, max_size=30), st.data())
def test_reread_deviation_property(
    points: list[tuple[float, float, float]], data: st.DataObject
) -> None:
    n = len(points)
    idx = st.integers(min_value=0, max_value=n - 1)
    faces = data.draw(st.lists(st.lists(idx, min_size=3, max_size=3), min_size=1, max_size=40))
    m = mesh(points, faces)
    out = write_binary_stl(m, HEADER)
    assert len(out.data) == 84 + 50 * len(faces)
    worst, half_ulp = _max_dev(m, out.data)
    assert half_ulp and worst <= FILE_FIDELITY_MM


def test_large_coordinates_round_within_half_ulp() -> None:
    """ALG-06 edge case: far from the origin float32 rounding grows (export frame avoids it)."""
    x = 10_000.123456789
    m = mesh([[x, 0, 0], [x + 1, 0, 0], [x, 1, 0]], [[0, 1, 2]])
    worst, half_ulp = _max_dev(m, write_binary_stl(m, HEADER).data)
    assert half_ulp and worst <= float(np.spacing(np.float32(x))) / 2


def test_normals_unit_right_handed_and_zero_for_degenerate_faces() -> None:
    m = octa_sphere(2)
    _, tris, _ = read_back(write_binary_stl(m, HEADER).data)
    for n, a, _b, _c in tris:
        assert abs(math.hypot(*n) - 1.0) < 1e-6
        assert sum(ni * ai for ni, ai in zip(n, a, strict=True)) > 0  # outward on a sphere
    deg = mesh([[0, 0, 0], [1, 1, 1], [2, 2, 2], [5, 0, 0]], [[0, 1, 2], [0, 0, 3]])
    _, tris, _ = read_back(write_binary_stl(deg, HEADER).data)
    assert [t[0] for t in tris] == [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]


def test_empty_mesh_is_a_valid_file() -> None:
    out = write_binary_stl(
        MeshArrays.create(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32), frame="F_export"),
        "JUDE x",
    )
    assert len(out.data) == 84 and struct.unpack_from("<I", out.data, 80) == (0,)


@pytest.mark.parametrize(
    "header",
    ["solid head", "  SOLID x", "x" * 81, "JUDE Иванова", "JUDE\ttab", "JUDE\x00"],
)
def test_bad_headers_are_rejected(header: str) -> None:
    with pytest.raises(KernelContractError):
        write_binary_stl(octa_sphere(0), header)


def test_header_builder_validates_tokens() -> None:
    assert stl_header("1.2.3", "J-0123ABCD", 4) == "JUDE 1.2.3 J-0123ABCD v4 mm F_export"
    for bad in (("1 2", "J-1", 1), ("1", "Иванова", 1), ("1", "J-1", 0), ("1", "J-1", True)):
        with pytest.raises(KernelContractError):
            stl_header(*bad)


def test_frame_must_be_f_export() -> None:
    m = MeshArrays.create(np.eye(3), np.array([[0, 1, 2]]), frame=Frame.F_ANAT)
    with pytest.raises(KernelContractError, match="F_export"):
        write_binary_stl(m, HEADER)


def test_float32_overflow_is_rejected() -> None:
    with pytest.raises(KernelContractError, match="overflow"):
        write_binary_stl(mesh([[1e39, 0, 0], [0, 1, 0], [0, 0, 1]], [[0, 1, 2]]), HEADER)


# Golden file hash of the reference sphere. A change here is a change of the manufacturing
# file format: it needs a reviewed reason (and a new op/format version where applicable).
GOLDEN_SPHERE5_SHA256 = "faed46d46d37e80c660a6e1273e5c2150934ca908fe1b3ae6fa24418bfeb9d35"


@pytest.mark.determinism
def test_golden_hash_and_100_runs() -> None:
    m = octa_sphere(5)
    hashes = {write_binary_stl(m, HEADER).sha256 for _ in range(100)}
    assert hashes == {GOLDEN_SPHERE5_SHA256}


def test_result_type() -> None:
    assert isinstance(write_binary_stl(octa_sphere(0), HEADER), StlBytes)
