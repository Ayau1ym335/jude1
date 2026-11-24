"""UT-FN-KRP-02 / PT-FN-KRP-02: canonical geometry hash (ALG-54; TSK-KRP-02-K).

Completion criterion: identical arrays give an identical hash; a 1-ulp change in any coordinate
gives a different hash. Known vector: the layout is rebuilt independently with ``struct``.
"""

import hashlib
import struct

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core import Frame, KernelContractError, MeshArrays
from jude_kernel.k08_replay import (
    GEOMETRY_MAGIC,
    canonical_geometry_bytes,
    geometry_sha256,
    mesh_geometry_sha256,
)

TET_V = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=np.float64)
TET_F = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32)
# Pinned once from the independent struct layout below; a change means the identity of every
# stored geometry_sha changed (ADR-010) and must never happen silently.
TET_SHA = "2d924d790f24db452eebaf6b5cd62dc5cf2732a0caf542ff6d3de2bda52d7e88"


def reference_bytes(v: NDArray[np.float64], f: NDArray[np.int32]) -> bytes:
    """ALG-54 written out with struct, independent of the numpy implementation."""
    out = b"JGEO1" + struct.pack("<QQ", len(v), len(f))
    for row in v.tolist():
        out += struct.pack("<3d", *(0.0 if c == 0 else c for c in row))
    for row in f.tolist():
        out += struct.pack("<3i", *row)
    return out


# --- completion criterion ---------------------------------------------------------------------


def test_completion_criterion_identical_arrays_identical_hash() -> None:
    h = geometry_sha256(TET_V, TET_F)
    layouts = [
        (TET_V.copy(), TET_F.copy()),
        (np.asfortranarray(TET_V), np.asfortranarray(TET_F)),  # column-major memory
        (TET_V.astype(">f8"), TET_F.astype(">i4")),  # big-endian memory
        (np.repeat(TET_V, 2, axis=0)[::2], np.repeat(TET_F, 2, axis=0)[::2]),  # strided views
    ]
    for v, f in layouts:
        assert np.array_equal(v, TET_V) and geometry_sha256(v, f) == h


@pytest.mark.parametrize("direction", [np.inf, -np.inf], ids=["up", "down"])
def test_completion_criterion_one_ulp_in_any_coordinate_changes_the_hash(direction: float) -> None:
    v = TET_V + np.array([0.125, -3.5, 7.0])  # no zeros, so both directions are real ulps
    base = geometry_sha256(v, TET_F)
    seen = {base}
    for i, j in np.ndindex(v.shape):
        moved = v.copy()
        moved[i, j] = np.nextafter(moved[i, j], direction)
        assert moved[i, j] != v[i, j]
        h = geometry_sha256(moved, TET_F)
        assert h not in seen, (i, j)
        seen.add(h)


@settings(max_examples=300, deadline=None)
@given(
    coords=st.lists(
        st.floats(allow_nan=False, allow_infinity=False, width=64), min_size=3, max_size=30
    ).filter(lambda c: len(c) % 3 == 0),
    pick=st.integers(min_value=0),
    up=st.booleans(),
)
def test_property_one_ulp_anywhere_changes_the_hash(
    coords: list[float], pick: int, up: bool
) -> None:
    v = np.array(coords, dtype=np.float64).reshape(-1, 3)
    f = np.zeros((1, 3), dtype=np.int32)
    k = pick % v.size
    moved = v.copy().ravel()
    with np.errstate(over="ignore"):  # stepping past the largest float is skipped below
        target = np.nextafter(moved[k], np.inf if up else -np.inf)
    if not np.isfinite(target) or (moved[k] == 0 and target == 0):
        return  # stepping past the largest float, or -0.0 <-> +0.0 (canonicalised, same value)
    moved[k] = target
    assert geometry_sha256(moved.reshape(-1, 3), f) != geometry_sha256(v, f)
    assert geometry_sha256(v.copy(), f.copy()) == geometry_sha256(v, f)


# --- ALG-54 layout ----------------------------------------------------------------------------


def test_known_vector_matches_the_independent_layout() -> None:
    data = canonical_geometry_bytes(TET_V, TET_F)
    assert data == reference_bytes(TET_V, TET_F)
    assert data[:5] == GEOMETRY_MAGIC and len(data) == 5 + 16 + 4 * 3 * 8 + 4 * 3 * 4
    assert (
        geometry_sha256(TET_V, TET_F) == hashlib.sha256(reference_bytes(TET_V, TET_F)).hexdigest()
    )


@pytest.mark.determinism
def test_golden_hash_is_stable() -> None:
    assert geometry_sha256(TET_V, TET_F) == TET_SHA


def test_empty_mesh_is_just_the_header() -> None:
    empty_v, empty_f = np.zeros((0, 3), np.float64), np.zeros((0, 3), np.int32)
    expected = hashlib.sha256(b"JGEO1" + bytes(16)).hexdigest()
    assert geometry_sha256(empty_v, empty_f) == expected


def test_counts_separate_vertices_from_faces() -> None:
    # Two layouts whose payload bytes are identical but whose counts differ must not collide.
    one_vertex = np.array([[1.0, 2.0, 3.0]])
    no_faces = np.zeros((0, 3), np.int32)
    assert canonical_geometry_bytes(one_vertex, no_faces)[5:21] == struct.pack("<QQ", 1, 0)


# --- canonicalisation and bits ----------------------------------------------------------------


def test_negative_zero_is_the_only_canonicalisation() -> None:
    v = TET_V.copy()
    v[v == 0] = -0.0
    assert np.signbit(v).any()
    assert geometry_sha256(v, TET_F) == geometry_sha256(TET_V, TET_F)


def test_every_bit_of_every_coordinate_counts() -> None:
    """Hash changes when any bit changes, except the sign bit of a zero (-0.0 == +0.0)."""
    v = np.array([[1.5, -0.0, 123.456], [0.0, -7.25, 1e-300]], dtype=np.float64)
    f = np.array([[0, 1, 0]], dtype=np.int32)
    base = geometry_sha256(v, f)
    for i, j in np.ndindex(v.shape):
        for bit in range(64):
            moved = v.copy()
            raw = moved.view(np.uint64)
            raw[i, j] ^= np.uint64(1) << np.uint64(bit)
            value = moved[i, j]
            if not np.isfinite(value):
                with pytest.raises(KernelContractError):
                    geometry_sha256(moved, f)
            elif value == 0 and v[i, j] == 0:
                assert geometry_sha256(moved, f) == base  # sign of zero only
            else:
                assert geometry_sha256(moved, f) != base, (i, j, bit)


def test_face_and_vertex_order_are_part_of_the_identity() -> None:
    base = geometry_sha256(TET_V, TET_F)
    assert geometry_sha256(TET_V, TET_F[::-1]) != base  # face order
    assert geometry_sha256(TET_V, TET_F[:, [1, 2, 0]]) != base  # same triangle, rotated
    perm = [1, 0, 2, 3]
    inverse = np.argsort(perm)
    assert geometry_sha256(TET_V[perm], inverse[TET_F].astype(np.int32)) != base  # vertex order


# --- contract ---------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_is_a_programming_error(bad: float) -> None:
    v = TET_V.copy()
    v[2, 1] = bad
    with pytest.raises(KernelContractError, match="finite"):
        geometry_sha256(v, TET_F)


@pytest.mark.parametrize(
    ("v", "f", "match"),
    [
        (TET_V.astype(np.float32), TET_F, "float64"),
        (TET_V.astype(np.int64), TET_F, "float64"),
        (TET_V, TET_F.astype(np.int64), "int32"),
        (TET_V, TET_F.astype(np.uint32), "int32"),
        (TET_V[:, :2], TET_F, "shape"),
        (TET_V.ravel(), TET_F, "shape"),
        (TET_V, TET_F[:, :2], "shape"),
    ],
)
def test_no_silent_conversion(v: NDArray[np.generic], f: NDArray[np.generic], match: str) -> None:
    with pytest.raises(KernelContractError, match=match):
        geometry_sha256(v, f)


def test_mesh_hash_covers_geometry_only() -> None:
    plain = MeshArrays.create(TET_V, TET_F, frame=Frame.F_SCAN)
    tagged = MeshArrays.create(
        TET_V, TET_F, frame=Frame.F_ANAT, face_tags=np.ones(4, np.uint8),
        vertex_attrs={"curvature": np.arange(4.0)},
    )  # fmt: skip
    assert mesh_geometry_sha256(plain) == mesh_geometry_sha256(tagged)
    assert mesh_geometry_sha256(plain) == geometry_sha256(TET_V, TET_F)


def test_inputs_are_not_modified() -> None:
    v = TET_V.copy()
    v[0, 0] = -0.0
    geometry_sha256(v, TET_F)
    assert np.signbit(v[0, 0])  # canonicalisation works on a copy
