"""UT-FN-KIO-01 / PT-FN-KIO-01: detect file format by signature (ALG-01; TSK-KIO-01-K).

Completion criterion: the format set T4 (the same object in every encoding) is classified 100 %
correctly, and a binary STL whose header starts with 'solid' is classified as binary.
"""

import io
from pathlib import Path
import struct
import zipfile

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from jude_kernel.k01_io import Detection, FileFormat, detect_bytes, detect_format
from jude_kernel.k01_io.detect import EXTENSION_MISMATCH, FILE_UNREADABLE, WINDOW

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
T4 = FIXTURES / "T4" / "format_set"
EXPECTED = {
    "sphere_binary.stl": FileFormat.STL_BINARY,
    "sphere_ascii.stl": FileFormat.STL_ASCII,
    "sphere.obj": FileFormat.OBJ,
    "sphere_negative_indices.obj": FileFormat.OBJ,
    "sphere_texture_refs.obj": FileFormat.OBJ,
    "cube_quads.obj": FileFormat.OBJ,
    "sphere_ascii.ply": FileFormat.PLY_ASCII,
    "sphere_le.ply": FileFormat.PLY_BIN_LE,
    "sphere_be.ply": FileFormat.PLY_BIN_BE,
}
TRI = (
    b"facet normal 0 0 1\n outer loop\n  vertex 0 0 0\n  vertex 1 0 0\n  vertex 0 1 0\n"
    b" endloop\nendfacet\n"
)
ASCII_STL = b"solid part\n" + TRI + b"endsolid part\n"
OBJ = b"# x\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def binary_stl(n: int, header: bytes = b"JUDE test") -> bytes:
    return header.ljust(80, b" ")[:80] + struct.pack("<I", n) + bytes(50 * n)


def fmt(data: bytes, extension: str | None = None) -> FileFormat | None:
    return detect_bytes(data, extension=extension).format


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("part.stl", ASCII_STL)
    return buf.getvalue()


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_t4_format_set_is_classified_100_percent() -> None:
    files = {p.name: p.read_bytes() for p in T4.iterdir() if p.name in EXPECTED}
    assert set(files) == set(EXPECTED)
    assert {name: fmt(data) for name, data in files.items()} == EXPECTED
    assert set(EXPECTED.values()) == set(FileFormat)  # every encoding FN-KIO-01 lists


def test_completion_criterion_binary_stl_with_solid_header_is_binary() -> None:
    data = (T4 / "sphere_binary.stl").read_bytes()
    solid = b"solid sphere exported by some CAD tool".ljust(80, b" ") + data[80:]
    assert fmt(solid) is FileFormat.STL_BINARY
    tricky = b"solid x\nfacet normal 0 0 1".ljust(80, b" ") + data[80:]  # 'facet' in it too
    assert fmt(tricky) is FileFormat.STL_BINARY


# --- one fixture per format and the edge cases of ALG-01 ------------------------------------------


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (ASCII_STL, FileFormat.STL_ASCII),
        (b"\xef\xbb\xbf" + ASCII_STL, FileFormat.STL_ASCII),  # UTF-8 BOM
        (ASCII_STL.replace(b"\n", b"\r\n"), FileFormat.STL_ASCII),  # CRLF
        (b"\n\t  " + ASCII_STL, FileFormat.STL_ASCII),  # leading blank space
        (OBJ, FileFormat.OBJ),
        (b"\xef\xbb\xbf" + OBJ.replace(b"\n", b"\r\n"), FileFormat.OBJ),
        (b"ply\r\nformat ascii 1.0\r\nelement vertex 0\r\nend_header\r\n", FileFormat.PLY_ASCII),
        (b"ply\nformat binary_little_endian 1.0\nend_header\n\x00\x01", FileFormat.PLY_BIN_LE),
        (binary_stl(0), FileFormat.STL_BINARY),  # header only, zero triangles
        (binary_stl(3), FileFormat.STL_BINARY),
    ],
)
def test_formats(data: bytes, expected: FileFormat) -> None:
    assert fmt(data) is expected


@pytest.mark.parametrize(
    "data",
    [
        b"",  # empty file
        binary_stl(3)[:-1],  # truncated binary STL: the size rule fails
        binary_stl(3) + b"\x00",  # one extra byte
        b"solid part\nendsolid part\n",  # 'solid' without any facet
        b"solidpart\n" + TRI,  # 'solid' must be a token
        ASCII_STL.replace(b"facet", b"facets"),  # 'facet' must be a token
        b"v 0 0 0\nv 1 0 0\n",  # OBJ without faces
        b"f 1 2 3\n",  # OBJ without vertices
        OBJ + b"curv 0 1 1 2\n",  # unknown keyword
        b"ply\nelement vertex 0\nend_header\n",  # PLY without a format line
        b"ply\nformat binary_middle_endian 1.0\nend_header\n",
        b"\x89PNG\r\n\x1a\n" + bytes(200),
        "solid деталь\n".encode() + bytes(100),  # NUL bytes: not text
    ],
)
def test_unreadable(data: bytes) -> None:
    assert detect_bytes(data, extension=".stl") == Detection(None, FILE_UNREADABLE)


def test_unreadable_fixture_and_zip() -> None:
    empty = (FIXTURES / "T3" / "empty" / "empty.stl").read_bytes()
    for data in (empty, _zip()):  # T3 empty file; ZIP renamed .stl
        assert detect_bytes(data, extension=".stl") == Detection(None, FILE_UNREADABLE)


def test_large_obj_with_faces_beyond_the_first_window() -> None:
    vertices = b"".join(b"v %d.0 0.5 1.25\n" % i for i in range(2000))  # far more than 4 KiB
    data = b"# big\n" + vertices + b"f 1 2 3\nf 2 3 4\n"
    assert len(data) > 4 * WINDOW and fmt(data) is FileFormat.OBJ
    assert fmt(data + b"bogus 1\n") is None  # a stray non-OBJ line in a window disqualifies


def test_head_and_tail_windows_are_enough() -> None:
    data = (T4 / "sphere.obj").read_bytes()
    d = detect_format(data[:WINDOW], len(data), tail=data[-WINDOW:])
    assert d.format is FileFormat.OBJ
    big = (T4 / "sphere_binary.stl").read_bytes()
    assert detect_format(big[:WINDOW], len(big)).format is FileFormat.STL_BINARY


def test_size_must_cover_the_head() -> None:
    with pytest.raises(ValueError):
        detect_format(b"abc", 2)


# --- extension: notice only ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "ext", "notices"),
    [
        ("sphere_binary.stl", ".stl", ()),
        ("sphere_binary.stl", "STL", ()),
        ("sphere.obj", ".stl", (EXTENSION_MISMATCH,)),
        ("sphere_le.ply", ".obj", (EXTENSION_MISMATCH,)),
        ("sphere_ascii.stl", ".txt", ()),  # an unknown extension makes no claim
        ("sphere_ascii.stl", None, ()),
    ],
)
def test_extension_only_adds_a_notice(name: str, ext: str | None, notices: tuple[str, ...]) -> None:
    d = detect_bytes((T4 / name).read_bytes(), extension=ext)
    assert d.format is EXPECTED[name] and d.notices == notices


@settings(max_examples=200, deadline=None)
@given(name=st.sampled_from(sorted(EXPECTED)), ext=st.text(max_size=8))
def test_property_detection_is_independent_of_the_file_name(name: str, ext: str) -> None:
    assert fmt((T4 / name).read_bytes(), ext) is EXPECTED[name]


@settings(max_examples=300, deadline=None)
@given(data=st.binary(max_size=600))
def test_property_random_bytes_are_classified_deterministically(data: bytes) -> None:
    d = detect_bytes(data)
    assert d == detect_bytes(bytes(data))
    assert (d.format is None) == (d.reason_code == FILE_UNREADABLE)
    if d.format is FileFormat.STL_BINARY:  # only ever by the exact size identity
        assert len(data) == 84 + 50 * struct.unpack_from("<I", data, 80)[0]
