"""UT-FN-KIO-05 / PT-FN-KIO-05: build and validate indexed mesh (ALG-05; TSK-KIO-05-K).

Completion criterion: the same object in all T4 encodings yields equal V/F counts, and the NaN
fixture is rejected. The OBJ and PLY encodings of T4 join this test when their parsers exist
(TSK-KIO-03-K / TSK-KIO-04-K). Today the binary STL, the ASCII STL and the indexed reference
(expected_sphere.jarr) are compared.
"""

from pathlib import Path
import struct

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core import Frame, KernelContractError, decode_mesh
from jude_kernel.k01_io import detect_bytes, from_indexed, from_soup, parse_stl

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
T4 = FIXTURES / "T4" / "format_set"
CAP = 1_000_000
STL_RECORD = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])


def raw_soup(path: Path) -> NDArray[np.float64]:
    """The corners of a binary STL as stored, without the parser's own checks."""
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 80)[0]
    return np.frombuffer(data, STL_RECORD, n, 84)["v"].reshape(-1, 3).astype(np.float64)


def stl_mesh(name: str) -> object:
    data = (T4 / name).read_bytes()
    parsed = parse_stl(data, detect_bytes(data).format, max_faces=CAP)  # type: ignore[arg-type]
    assert parsed.soup is not None
    return from_soup(parsed.soup, max_faces=CAP)


# --- completion criterion ------------------------------------------------------------------------


def test_completion_criterion_all_t4_encodings_give_equal_v_and_f() -> None:
    reference = decode_mesh((T4 / "expected_sphere.jarr").read_bytes())
    built = [stl_mesh("sphere_binary.stl"), stl_mesh("sphere_ascii.stl"),
             from_indexed(reference.V, reference.F, max_faces=CAP)]  # fmt: skip
    counts = {(b.mesh.n_vertices, b.mesh.n_faces) for b in built}  # type: ignore[attr-defined]
    assert counts == {(reference.n_vertices, reference.n_faces)}
    # the faces are the same geometry, corner for corner, in every encoding
    for b in built:
        m = b.mesh  # type: ignore[attr-defined]
        assert np.array_equal(m.V[m.F], reference.V[reference.F])
        assert m.frame is Frame.F_FILE


def test_completion_criterion_nan_fixture_is_rejected() -> None:
    path = FIXTURES / "T10" / "nan_coordinate" / "nan_coordinate.stl"
    soup = raw_soup(path)
    assert np.isnan(soup).any()
    built = from_soup(soup, max_faces=CAP)
    assert (built.reason_code, built.mesh) == ("NON_FINITE_COORDINATES", None)
    data = path.read_bytes()  # and the full import path stops at the parser already
    assert parse_stl(data, detect_bytes(data).format, max_faces=CAP).reason_code == (  # type: ignore[arg-type]
        "NON_FINITE_COORDINATES"
    )


# --- ALG-05 cases ---------------------------------------------------------------------------------


def test_shared_vertex_soup() -> None:
    a, b, c, d = [0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0], [1.0, 1, 0]
    built = from_soup(np.array([a, b, c, c, b, d]), max_faces=CAP)
    assert built.mesh is not None and built.stats is not None
    assert built.mesh.V.tolist() == [a, b, c, d]  # first-occurrence order
    assert built.mesh.F.tolist() == [[0, 1, 2], [2, 1, 3]]  # face order = file order
    assert built.stats.as_json() == {"n_vertices_in": 6, "n_vertices_merged": 2,
                                     "polygons_triangulated": 0, "notices": []}  # fmt: skip


def test_negative_zero_merges_with_zero() -> None:
    built = from_soup(np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [-0.0, -0.0, 0], [1, 0, 0],
                                [0, 0, 1]]), max_faces=CAP)  # fmt: skip
    assert built.mesh is not None and built.mesh.n_vertices == 4
    assert not np.signbit(built.mesh.V).any()


def test_near_duplicates_stay_separate() -> None:
    eps = np.nextafter(1.0, 2.0)  # one ulp: not equal, so not merged (no epsilon welding)
    built = from_soup(np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [eps, 0, 0],
                                [0, 0, 1]]), max_faces=CAP)  # fmt: skip
    assert built.mesh is not None and built.mesh.n_vertices == 5


def test_degenerate_faces_are_kept() -> None:
    p = [1.0, 2.0, 3.0]
    built = from_soup(np.array([p, p, p, [0.0, 0, 0], [1, 0, 0], [0, 1, 0]]), max_faces=CAP)
    assert built.mesh is not None and built.mesh.F.tolist()[0] == [0, 0, 0]  # ALG-08 reports


def test_icosphere_soup_has_euler_characteristic_two() -> None:
    built = from_soup(raw_soup(FIXTURES / "T1" / "icosphere_s4_r75" / "mesh.stl"), max_faces=CAP)
    m = built.mesh
    assert m is not None
    edges = {tuple(sorted(e)) for f in m.F.tolist() for e in ((f[0], f[1]), (f[1], f[2]),
                                                              (f[2], f[0]))}  # fmt: skip
    assert m.n_vertices - len(edges) + m.n_faces == 2


def test_indexed_input_merges_duplicate_vertices_and_remaps() -> None:
    v = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 0, 0], [5, 5, 5]])  # 3 == 1, 4 unused
    built = from_indexed(v, np.array([[0, 1, 2], [2, 3, 0]]), max_faces=CAP,
                         polygons_triangulated=1, notices=("OBJ_TEXTURE_IGNORED",))  # fmt: skip
    assert built.mesh is not None and built.stats is not None
    assert built.mesh.F.tolist() == [[0, 1, 2], [2, 1, 0]]
    assert built.mesh.n_vertices == 4  # the unused vertex stays (nothing is dropped)
    assert (built.stats.n_vertices_merged, built.stats.polygons_triangulated) == (1, 1)
    assert built.stats.notices == ("OBJ_TEXTURE_IGNORED",)


# --- refusals (one per code) and contract ---------------------------------------------------------


def test_file_empty() -> None:
    assert from_soup(np.zeros((0, 3)), max_faces=CAP).reason_code == "FILE_EMPTY"
    assert from_indexed(np.zeros((3, 3)), np.zeros((0, 3), int), max_faces=CAP).reason_code == (
        "FILE_EMPTY"
    )


def test_face_limit_and_index_range() -> None:
    six = np.tile(np.eye(3), (2, 1))
    assert from_soup(six, max_faces=1).reason_code == "FACE_LIMIT"
    assert from_soup(six, max_faces=2).reason_code is None  # inclusive
    bad = from_indexed(np.eye(3), np.array([[0, 1, 3]]), max_faces=CAP)
    assert bad.reason_code == "FILE_UNREADABLE" and "0..2" in bad.detail
    assert from_indexed(np.eye(3), np.array([[0, -1, 2]]), max_faces=CAP).reason_code == (
        "FILE_UNREADABLE"
    )


def test_non_finite_indexed_vertices() -> None:
    v = np.array([[0.0, 0, 0], [np.inf, 0, 0], [0, 1, 0]])
    assert from_indexed(v, np.array([[0, 1, 2]]), max_faces=CAP).reason_code == (
        "NON_FINITE_COORDINATES"
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: from_soup(np.zeros((4, 3)), max_faces=CAP),  # not a multiple of 3 corners
        lambda: from_soup(np.zeros((3, 2)), max_faces=CAP),
        lambda: from_soup(np.zeros((3, 3)), max_faces=0),  # the cap has no default
        lambda: from_soup(np.zeros((3, 3)), max_faces=2**30),  # indices would overflow int32
        lambda: from_indexed(np.zeros((3, 3)), np.array([[0.0, 1, 2]]), max_faces=CAP),
    ],
)
def test_contract(call: object) -> None:
    with pytest.raises(KernelContractError):
        call()  # type: ignore[operator]


# --- properties -----------------------------------------------------------------------------------

pool = st.sampled_from([-1.5, -0.0, 0.0, 0.25, 2.0, 1e-300, 7.0])  # few values: many duplicates


@settings(max_examples=300, deadline=None)
@given(st.lists(pool, min_size=9, max_size=9 * 40).filter(lambda c: len(c) % 9 == 0),
       st.randoms(use_true_random=False))  # fmt: skip
def test_property_invariants(values: list[float], rnd: object) -> None:
    soup = np.array(values, dtype=np.float64).reshape(-1, 3)
    built = from_soup(soup, max_faces=CAP)
    m = built.mesh
    assert m is not None
    canon = np.where(soup == 0, 0.0, soup)
    assert m.n_vertices <= soup.shape[0] and int(m.F.max()) < m.n_vertices
    assert np.array_equal(m.V[m.F].reshape(-1, 3), canon)  # every face unchanged bitwise
    seen: list[tuple[float, ...]] = []
    for row in map(tuple, canon.tolist()):  # V order = first occurrence in the soup
        if row not in seen:
            seen.append(row)
    assert [tuple(r) for r in m.V.tolist()] == seen
    again = from_soup(soup.copy(), max_faces=CAP).mesh
    assert again is not None and np.array_equal(again.V, m.V) and np.array_equal(again.F, m.F)
    # a shuffled face order follows the same rule on the shuffled soup
    faces = list(range(soup.shape[0] // 3))
    rnd.shuffle(faces)  # type: ignore[attr-defined]
    shuffled = soup.reshape(-1, 3, 3)[faces].reshape(-1, 3)
    sm = from_soup(shuffled, max_faces=CAP).mesh
    assert sm is not None
    assert np.array_equal(sm.V[sm.F].reshape(-1, 3), np.where(shuffled == 0, 0.0, shuffled))
