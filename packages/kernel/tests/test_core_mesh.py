"""UT-core: DS-01 MeshArrays invariants (XC-FND-12)."""

from typing import Any

import numpy as np
import pytest

from jude_kernel.core import Frame, KernelContractError, MeshArrays, check_caps

TET_V = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=np.float64)
TET_F = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32)


def tet(**kw: Any) -> MeshArrays:
    return MeshArrays.create(TET_V, TET_F, frame=Frame.F_SCAN, **kw)


def test_valid_mesh_dtypes_and_shape() -> None:
    m = tet()
    assert m.V.dtype == np.dtype("<f8") and m.F.dtype == np.dtype("<i4")
    assert (m.n_vertices, m.n_faces) == (4, 4)
    assert m.V.flags.c_contiguous and m.F.flags.c_contiguous


def test_negative_zero_is_canonicalised() -> None:
    v = TET_V.copy()
    v[0] = [-0.0, -0.0, -0.0]
    m = MeshArrays.create(v, TET_F, frame="F_scan")
    assert not np.any(np.signbit(m.V[0]))


def test_arrays_are_read_only_and_not_aliased() -> None:
    v = TET_V.copy()
    m = MeshArrays.create(v, TET_F, frame="F_scan")
    v[1, 0] = 99.0
    assert m.V[1, 0] == 10.0
    with pytest.raises(ValueError):
        m.V[0, 0] = 1.0


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_vertices_rejected(bad: float) -> None:
    v = TET_V.copy()
    v[2, 1] = bad
    with pytest.raises(KernelContractError, match="finite"):
        MeshArrays.create(v, TET_F, frame="F_scan")


@pytest.mark.parametrize("index", [-1, 4])
def test_face_index_out_of_range_rejected(index: int) -> None:
    f = TET_F.copy()
    f[0, 0] = index
    with pytest.raises(KernelContractError, match="index"):
        MeshArrays.create(TET_V, f, frame="F_scan")


def test_shapes_and_dtypes_enforced() -> None:
    with pytest.raises(KernelContractError):
        MeshArrays.create(TET_V[:, :2], TET_F, frame="F_scan")
    with pytest.raises(KernelContractError):
        MeshArrays.create(TET_V, TET_F[:, :2], frame="F_scan")
    with pytest.raises(KernelContractError, match="integer"):
        MeshArrays.create(TET_V, TET_F.astype(np.float64), frame="F_scan")
    with pytest.raises(KernelContractError, match="range"):
        MeshArrays.create(TET_V, TET_F.astype(np.int64) + 2**40, frame="F_scan")


def test_frame_tag_required_and_checked() -> None:
    with pytest.raises(KernelContractError, match="frame"):
        MeshArrays.create(TET_V, TET_F, frame="F_world")


def test_face_tags_flags() -> None:
    assert tet(face_tags=np.array([1, 2, 4, 16], dtype=np.uint8)).face_tags is not None
    with pytest.raises(KernelContractError, match="bit flags"):
        tet(face_tags=np.array([1, 2, 4, 32], dtype=np.uint8))
    with pytest.raises(KernelContractError, match="shape"):
        tet(face_tags=np.array([1, 2], dtype=np.uint8))


def test_vertex_attrs() -> None:
    m = tet(vertex_attrs={"curv": np.array([0.0, 1.0, -0.0, 2.0])})
    assert not np.signbit(m.vertex_attrs["curv"][2])
    with pytest.raises(KernelContractError, match="name"):
        tet(vertex_attrs={"Bad Name": np.zeros(4)})
    with pytest.raises(KernelContractError, match="shape"):
        tet(vertex_attrs={"curv": np.zeros(3)})


def test_check_caps_needs_explicit_limits() -> None:
    m = tet()
    assert check_caps(m, max_vertices=4, max_faces=4) is None
    assert check_caps(m, max_vertices=10, max_faces=3) == "FACE_LIMIT"
    assert check_caps(m, max_vertices=3, max_faces=10) == "VERTEX_LIMIT"
    with pytest.raises(KernelContractError):
        check_caps(m, max_vertices=0, max_faces=10)
