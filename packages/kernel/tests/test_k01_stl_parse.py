"""UT-FN-KIO-02 / PT-FN-KIO-02: parse STL, binary and ASCII (ALG-02; TSK-KIO-02-K).

Completion criterion: the binary and ASCII reference files give V/F counts equal to the
reference after FN-KIO-05. The reference is the T4 format set: every sphere file "imports to
the V and F of expected_sphere.jarr (STL: after vertex welding of identical coordinates)". The
weld below is FN-KIO-05's rule (exactly equal triples, first-occurrence order), written in the
test until that task exists. The soup is also cross-checked against an independent ``struct``
reader. The trimesh / numpy-stl oracle runs belong to the oracle stage (TSK-OPS-07-C).
"""

from pathlib import Path
import struct

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core import Frame, KernelContractError, MeshArrays, decode_mesh
from jude_kernel.k01_io import FileFormat, detect_bytes, parse_stl, stl_header, write_binary_stl
from jude_kernel.k01_io.stl_parse import parse_ascii, parse_binary

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
T4 = FIXTURES / "T4" / "format_set"
CAP = 1_000_000
TRI = np.array([[0.0, 0, 0], [10, 0, 0], [0, 10, 0]])


def weld(soup: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.int64]]:
    """FN-KIO-05's merge: bitwise-equal triples (-0.0 as +0.0), first-occurrence order."""
    canon = np.where(soup == 0, 0.0, soup)
    _, first, inverse = np.unique(canon, axis=0, return_index=True, return_inverse=True)
    rank = np.argsort(np.argsort(first))  # unique id -> first-occurrence position
    v = canon[np.sort(first)]
    return v, rank[inverse.ravel()].reshape(-1, 3)


def struct_reader(data: bytes) -> NDArray[np.float64]:
    """An independent binary reader: stdlib struct, record by record."""
    (n,) = struct.unpack_from("<I", data, 80)
    rows = []
    for i in range(n):
        vals = struct.unpack_from("<12fH", data, 84 + 50 * i)
        rows.extend([vals[3:6], vals[6:9], vals[9:12]])
    return np.array(rows, dtype=np.float64)


def binary(tris: NDArray[np.float64], header: bytes = b"JUDE test", attr: int = 0) -> bytes:
    out = header.ljust(80, b" ")[:80] + struct.pack("<I", len(tris) // 3)
    for i in range(0, len(tris), 3):
        out += struct.pack("<12fH", 0.0, 0.0, 1.0, *tris[i : i + 3].ravel(), attr)
    return out


def ascii_stl(tris: NDArray[np.float64], sep: bytes = b"\n") -> bytes:
    lines = [b"solid part"]
    for i in range(0, len(tris), 3):
        lines += [b"  facet normal 0 0 1", b"    outer loop"]
        lines += [
            b"      vertex " + b" ".join(repr(float(c)).encode() for c in p)
            for p in tris[i : i + 3]
        ]
        lines += [b"    endloop", b"  endfacet"]
    lines.append(b"endsolid part")
    return sep.join(lines) + sep


# --- completion criterion ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["sphere_binary.stl", "sphere_ascii.stl"])
def test_completion_criterion_reference_files_give_the_reference_v_and_f(name: str) -> None:
    reference = decode_mesh((T4 / "expected_sphere.jarr").read_bytes())
    data = (T4 / name).read_bytes()
    parsed = parse_stl(data, detect_bytes(data).format, max_faces=CAP)  # type: ignore[arg-type]
    assert parsed.reason_code is None and parsed.soup is not None
    v, f = weld(parsed.soup)
    assert (v.shape[0], f.shape[0]) == (reference.n_vertices, reference.n_faces)
    # stronger than counts: the same corners, face by face
    assert np.array_equal(v[f], reference.V[reference.F])


def test_binary_soup_equals_an_independent_reader() -> None:
    data = (T4 / "sphere_binary.stl").read_bytes()
    parsed = parse_binary(data, max_faces=CAP)
    assert parsed.soup is not None and np.array_equal(parsed.soup, struct_reader(data))
    assert parsed.n_facets == 320 and not parsed.soup.flags.writeable


def test_binary_and_ascii_of_the_same_object_agree() -> None:
    b = parse_stl((T4 / "sphere_binary.stl").read_bytes(), FileFormat.STL_BINARY, max_faces=CAP)
    a = parse_stl((T4 / "sphere_ascii.stl").read_bytes(), FileFormat.STL_ASCII, max_faces=CAP)
    assert b.soup is not None and a.soup is not None and np.array_equal(a.soup, b.soup)


# --- ALG-02 hand-built files ---------------------------------------------------------------------


def test_one_and_two_facet_files_in_file_order() -> None:
    two = np.vstack([TRI, TRI + 5.0])
    for data in (binary(TRI), ascii_stl(TRI)):
        p = parse_stl(data, detect_bytes(data).format, max_faces=CAP)  # type: ignore[arg-type]
        assert p.soup is not None and np.array_equal(p.soup, TRI)
    for data in (binary(two), ascii_stl(two)):
        p = parse_stl(data, detect_bytes(data).format, max_faces=CAP)  # type: ignore[arg-type]
        assert p.soup is not None and np.array_equal(p.soup, two)  # facet order = file order


def test_binary_header_solid_attribute_bytes_and_stored_normals_are_ignored() -> None:
    plain = parse_binary(binary(TRI), max_faces=CAP)
    tricky = parse_binary(
        binary(TRI, header=b"solid facet ascii-looking", attr=0xBEEF), max_faces=CAP
    )
    assert plain.soup is not None and tricky.soup is not None
    assert np.array_equal(plain.soup, tricky.soup)
    wrong_normals = bytearray(binary(TRI))
    wrong_normals[84:96] = struct.pack("<3f", 9.0, -9.0, 9.0)
    again = parse_binary(bytes(wrong_normals), max_faces=CAP)
    assert again.soup is not None and np.array_equal(again.soup, TRI)


@pytest.mark.parametrize(
    "variant",
    [
        lambda b: b.replace(b"\n", b"\r\n"),  # CRLF
        lambda b: b.replace(b"  ", b"\t \t"),  # tabs and mixed whitespace
        lambda b: b"\n\n" + b.replace(b"endloop\n", b"endloop\n\n"),  # blank lines
        lambda b: b + ascii_stl(TRI),  # a second solid in the same file
        lambda b: b.replace(b"vertex 10.0 0.0 0.0", b"vertex 1.0E+01 0.0e0 -0.0"),  # notation
        lambda b: b.replace(b"solid part", b"solid"),  # unnamed solid
    ],
)
def test_ascii_grammar_variants(variant: object) -> None:
    data = variant(ascii_stl(TRI))  # type: ignore[operator]
    p = parse_ascii(data, max_faces=CAP)
    assert p.reason_code is None and p.soup is not None
    assert np.array_equal(p.soup[:3], TRI)


# --- refusals (one negative test per error code) -------------------------------------------------


def test_file_empty() -> None:
    assert parse_binary(binary(np.zeros((0, 3))), max_faces=CAP).reason_code == "FILE_EMPTY"
    assert parse_ascii(b"solid x\nendsolid x\n", max_faces=CAP).reason_code == "FILE_EMPTY"


def test_face_limit_is_checked_before_allocation() -> None:
    bomb = b"JUDE".ljust(80, b" ") + struct.pack("<I", 2**31) + bytes(100)  # T3 face bomb shape
    p = parse_binary(bomb, max_faces=CAP)
    assert (p.reason_code, p.soup) == ("FACE_LIMIT", None) and "2147483648" in p.detail
    three = np.vstack([TRI, TRI, TRI])
    assert parse_binary(binary(three), max_faces=2).reason_code == "FACE_LIMIT"
    assert parse_ascii(ascii_stl(three), max_faces=2).reason_code == "FACE_LIMIT"
    assert parse_binary(binary(three), max_faces=3).reason_code is None  # the cap is inclusive


@pytest.mark.parametrize(
    "data",
    [
        binary(TRI)[:-1],  # truncated by one byte
        binary(TRI) + b"\x00",  # one byte too long
        b"short",
        (FIXTURES / "T3" / "truncated" / "truncated.stl").read_bytes(),
    ],
)
def test_binary_size_mismatch_is_unreadable(data: bytes) -> None:
    assert parse_binary(data, max_faces=CAP).reason_code == "FILE_UNREADABLE"


@pytest.mark.parametrize(
    ("broken", "line"),
    [
        (lambda b: b.replace(b"vertex 10.0 0.0 0.0", b"vertex 10,0 0.0 0.0"), 5),  # locale comma
        (lambda b: b.replace(b"vertex 10.0 0.0 0.0", b"vertex 1_0 0.0 0.0"), 5),  # underscore
        (lambda b: b.replace(b"vertex 10.0 0.0 0.0", b"vertex 0x1p3 0.0 0.0"), 5),  # hex float
        (lambda b: b.replace(b"vertex 10.0 0.0 0.0", b"vertex 10.0 0.0"), 5),  # 2 coordinates
        (lambda b: b.replace(b"      vertex 10.0 0.0 0.0\n", b""), 6),  # 2 vertices
        (lambda b: b.replace(b"    endloop\n", b""), 7),  # missing endloop
        (lambda b: b.replace(b"outer loop", b"outer lop"), 3),
        (lambda b: b.replace(b"endsolid part\n", b""), 8),  # unterminated solid
        (lambda b: b"garbage\n" + b, 1),
    ],
)
def test_malformed_ascii_names_the_line(broken: object, line: int) -> None:
    p = parse_ascii(broken(ascii_stl(TRI)), max_faces=CAP)  # type: ignore[operator]
    assert p.reason_code == "FILE_UNREADABLE" and p.detail.startswith(f"line {line}:"), p.detail


@pytest.mark.parametrize("token", [b"nan", b"-inf", b"Infinity", b"1e999"])
def test_non_finite_coordinates(token: bytes) -> None:
    data = ascii_stl(TRI).replace(b"vertex 10.0 0.0 0.0", b"vertex " + token + b" 0.0 0.0")
    assert parse_ascii(data, max_faces=CAP).reason_code == "NON_FINITE_COORDINATES"
    raw = bytearray(binary(TRI))
    raw[96:100] = struct.pack("<f", float("nan"))
    assert parse_binary(bytes(raw), max_faces=CAP).reason_code == "NON_FINITE_COORDINATES"


def test_contract() -> None:
    with pytest.raises(KernelContractError, match="face cap"):
        parse_stl(binary(TRI), FileFormat.STL_BINARY, max_faces=0)
    with pytest.raises(KernelContractError, match="not an STL"):
        parse_stl(b"", FileFormat.OBJ, max_faces=CAP)


# --- properties -----------------------------------------------------------------------------------


coords = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, width=32)


@settings(max_examples=200, deadline=None)
@given(st.lists(coords, min_size=9, max_size=9 * 20).filter(lambda c: len(c) % 9 == 0))
def test_property_float32_round_trip_through_writer_and_both_formats(values: list[float]) -> None:
    tris = np.array(values, dtype=np.float64).reshape(-1, 3)
    mesh = MeshArrays.create(tris, np.arange(len(tris)).reshape(-1, 3), frame=Frame.F_EXPORT)
    data = write_binary_stl(mesh, header=stl_header("0.0.0", "J-0123ABCD", 1)).data
    b = parse_stl(data, detect_bytes(data).format, max_faces=CAP)  # type: ignore[arg-type]
    canon = np.where(tris == 0, 0.0, tris)  # the writer canonicalises -0.0 (DS-01)
    assert b.soup is not None and np.array_equal(b.soup, canon)  # float32 -> float64 is exact
    a = parse_ascii(ascii_stl(tris), max_faces=CAP)
    assert a.soup is not None and np.array_equal(a.soup, tris)  # repr() round-trips
