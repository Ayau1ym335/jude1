"""UT-core + PT-jude-arr: canonical container (XC-FND-12 completion criteria).

- round-trip of jude-arr/1 is bit-exact;
- -0.0 is canonicalised;
- the decoder accepts only canonical bytes (so equal content <=> equal bytes <=> equal SHA).
"""

import hashlib
import struct
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp
import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core import Frame, JarrFormatError, MeshArrays, decode, decode_mesh, encode
from jude_kernel.core.jarr import MAGIC, encode_mesh

Arr = NDArray[Any]
MetaD = dict[str, Any]

TET_V = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=np.float64)
TET_F = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32)

# Pins the byte layout of jude-arr/1. If this changes, the format changed: that needs a new
# schema id (jude-arr/2), not an edit of this constant.
GOLDEN_TET_SHA256 = "381143dda8759d6b73ac20a0334d12f818e55ab6867f20053c497af3acd0bf57"


def tet() -> MeshArrays:
    return MeshArrays.create(
        TET_V,
        TET_F,
        frame=Frame.F_SCAN,
        face_tags=np.array([1, 1, 1, 2], dtype=np.uint8),
        vertex_attrs={"curv": np.array([0.5, -0.0, 1.0, 2.0])},
    )


@pytest.mark.determinism
def test_golden_bytes() -> None:
    assert hashlib.sha256(encode_mesh(tet())).hexdigest() == GOLDEN_TET_SHA256


@pytest.mark.determinism
def test_mesh_round_trip_bit_exact() -> None:
    data = encode_mesh(tet())
    back = decode_mesh(data)
    assert encode_mesh(back) == data
    assert back.V.tobytes() == tet().V.tobytes()
    assert back.F.tobytes() == tet().F.tobytes()
    assert back.frame is Frame.F_SCAN
    assert back.face_tags is not None and back.face_tags.tolist() == [1, 1, 1, 2]


def test_layout_header_and_alignment() -> None:
    data = encode({"a": np.arange(3, dtype=np.int32)}, {"kind": "x"})
    assert data[:8] == MAGIC
    (hlen,) = struct.unpack_from("<I", data, 8)
    assert data[12 : 12 + hlen].startswith(b'{"arrays":[{"dtype":"<i4","name":"a","shape":[3]}]')
    assert len(data) % 8 == 0


def test_negative_zero_canonicalised_on_encode() -> None:
    a = encode({"x": np.array([-0.0, 1.0])})
    b = encode({"x": np.array([0.0, 1.0])})
    assert a == b


def test_insertion_order_does_not_matter() -> None:
    x, y = np.arange(4, dtype=np.int32), np.ones(2)
    assert encode({"x": x, "y": y}, {"b": 1, "a": "z"}) == encode(
        {"y": y, "x": x}, {"a": "z", "b": 1}
    )


def test_big_endian_input_is_stored_little_endian() -> None:
    be = np.array([1.5, 2.5], dtype=">f8")
    assert encode({"x": be}) == encode({"x": np.array([1.5, 2.5], dtype="<f8")})


def test_decoded_arrays_are_read_only() -> None:
    arrays, _ = decode(encode({"x": np.ones(3)}))
    with pytest.raises(ValueError):
        arrays["x"][0] = 2.0


@pytest.mark.parametrize(
    ("arrays", "meta"),
    [
        ({"x": np.array([np.nan])}, {}),
        ({"x": np.array([True])}, {}),
        ({"x": np.array(["s"])}, {}),
        ({"bad name": np.ones(1)}, {}),
        ({"x": np.ones(1)}, {"f": 1.5}),
        ({"x": np.ones(1)}, {"Big": 1}),
        ({"x": np.ones(1)}, {"n": 2**60}),
    ],
)
def test_encode_rejects_non_canonical_inputs(arrays: dict[str, Arr], meta: MetaD) -> None:
    with pytest.raises(JarrFormatError):
        encode(arrays, meta)


def _mutations(data: bytes) -> dict[str, bytes]:
    (hlen,) = struct.unpack_from("<I", data, 8)
    header = data[12 : 12 + hlen]
    spaced = header.replace(b'"meta":', b'"meta": ')
    neg0 = bytearray(data)
    # first float64 of array "x" (x = [1.0, 2.0]) starts right after the padded header
    start = 12 + hlen + ((-(12 + hlen)) % 8)
    neg0[start : start + 8] = struct.pack("<d", -0.0)
    nan = bytearray(data)
    nan[start : start + 8] = struct.pack("<d", float("nan"))
    return {
        "wrong magic": b"JUDEARR2" + data[8:],
        "trailing byte": data + b"\0",
        "truncated": data[:-8],
        "non-canonical header": data[:8]
        + struct.pack("<I", len(spaced))
        + spaced
        + b"\0" * ((-(12 + len(spaced))) % 8)
        + data[12 + hlen + ((-(12 + hlen)) % 8) :],
        "negative zero": bytes(neg0),
        "nan": bytes(nan),
        "non-zero padding": data[:-1] + b"\1",
    }


@pytest.mark.parametrize(
    "case",
    list(_mutations(encode({"x": np.array([1.0, 2.0]), "y": np.ones(1, np.uint8)}, {"k": "v"}))),
)
def test_decode_rejects_non_canonical_bytes(case: str) -> None:
    data = encode({"x": np.array([1.0, 2.0]), "y": np.ones(1, np.uint8)}, {"k": "v"})
    with pytest.raises(JarrFormatError):
        decode(_mutations(data)[case])


def test_decode_mesh_rejects_wrong_container() -> None:
    with pytest.raises(JarrFormatError, match="mesh"):
        decode_mesh(encode({"V": TET_V, "F": TET_F}, {"kind": "deviation"}))
    with pytest.raises(JarrFormatError, match="mesh contract"):
        bad_f = TET_F.copy()
        bad_f[0, 0] = 9
        decode_mesh(
            encode(
                {"V": TET_V, "F": bad_f}, {"display_only": False, "frame": "F_scan", "kind": "mesh"}
            )
        )


# --- property tests (PT-jude-arr) ------------------------------------------------------------

DTYPES = st.sampled_from(["<f8", "<f4", "<i8", "<i4", "<u4", "<u1"])
NAMES = st.from_regex(r"[A-Za-z][A-Za-z0-9_.]{0,10}", fullmatch=True)


@st.composite
def array_sets(draw: st.DrawFn) -> dict[str, Arr]:
    names = draw(st.lists(NAMES, min_size=0, max_size=4, unique=True))
    out = {}
    for name in names:
        dtype = np.dtype(draw(DTYPES))
        shape = draw(hnp.array_shapes(min_dims=0, max_dims=3, min_side=0, max_side=4))
        elements = (
            st.floats(
                allow_nan=False, allow_infinity=False, width=64 if dtype.itemsize == 8 else 32
            )
            if dtype.kind == "f"
            else None
        )
        out[name] = draw(hnp.arrays(dtype, shape, elements=elements))
    return out


META = st.dictionaries(
    st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True),
    st.one_of(st.none(), st.booleans(), st.text(max_size=8), st.integers(-(2**53), 2**53)),
    max_size=4,
)


@pytest.mark.determinism
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(array_sets(), META)
def test_pt_round_trip_bit_exact(arrays: dict[str, Arr], meta: MetaD) -> None:
    data = encode(arrays, meta)
    back, back_meta = decode(data)
    assert back_meta == meta
    assert encode(back, back_meta) == data
    for name, a in arrays.items():
        expected = (
            np.where(a == 0, 0, a).astype(a.dtype.newbyteorder("<")) if a.dtype.kind == "f" else a
        )
        assert back[name].shape == a.shape
        assert (
            back[name].tobytes() == np.ascontiguousarray(expected, dtype=back[name].dtype).tobytes()
        )


@pytest.mark.determinism
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(array_sets(), META, st.data())
def test_pt_any_accepted_bytes_are_canonical(
    arrays: dict[str, Arr], meta: MetaD, data: st.DataObject
) -> None:
    """Flip one byte anywhere: either the decoder refuses, or the result re-encodes to the
    very same bytes. So two different byte strings never decode to equal content."""
    raw = bytearray(encode(arrays, meta))
    i = data.draw(st.integers(0, len(raw) - 1))
    raw[i] ^= data.draw(st.integers(1, 255))
    mutated = bytes(raw)
    try:
        back, back_meta = decode(mutated)
    except JarrFormatError:
        return
    assert encode(back, back_meta) == mutated


@pytest.mark.determinism
@settings(max_examples=100)
@given(st.integers(1, 30), st.integers(0, 30), st.data())
def test_pt_mesh_round_trip(n: int, m: int, data: st.DataObject) -> None:
    v = data.draw(hnp.arrays(np.float64, (n, 3), elements=st.floats(-1e4, 1e4)))
    f = data.draw(hnp.arrays(np.int32, (m, 3), elements=st.integers(0, n - 1)))
    mesh = MeshArrays.create(v, f, frame=Frame.F_ANAT)
    blob = encode_mesh(mesh)
    assert encode_mesh(decode_mesh(blob)) == blob
