"""UT-FN-KFR-03 / PT-FN-KFR-03: transform algebra and reflection guard (ALG-32; TSK-KFR-03-K).

Completion criterion: random rigid transforms round-trip within 1e-12 mm (property test); a
reflection matrix is rejected.
"""

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core import Frame, KernelContractError
from jude_kernel.k03_frames import (
    REFLECTION_REJECTED,
    RIGID_TOLERANCE,
    TRANSFORM_NOT_RIGID,
    RigidTransform,
    RigidTransformError,
    check_rigid,
    nearest_rotation,
)

ROUND_TRIP_MM = 1e-12  # completion criterion
SCAN, ANAT, EXPORT = Frame.F_SCAN, Frame.F_ANAT, Frame.F_EXPORT


def quat_rotation(q: NDArray[np.float64]) -> NDArray[np.float64]:
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])  # fmt: skip


coord = st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False)
quaternion = (
    st.lists(st.floats(-1, 1, allow_nan=False), min_size=4, max_size=4)
    .map(np.array)
    .filter(lambda q: np.linalg.norm(q) > 0.1)
)
rigid = st.builds(
    lambda q, t: RigidTransform.from_rotation_translation(
        quat_rotation(q), np.array(t), from_frame=SCAN, to_frame=ANAT
    ),
    quaternion,
    st.lists(coord, min_size=3, max_size=3),
)
points = st.lists(st.lists(coord, min_size=3, max_size=3), min_size=1, max_size=20).map(np.array)


def rot_z(deg: float) -> NDArray[np.float64]:
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])


# --- completion criterion ---------------------------------------------------------------------


@settings(max_examples=500, deadline=None)
@given(t=rigid, p=points)
def test_completion_criterion_random_rigid_transforms_round_trip(
    t: RigidTransform, p: NDArray[np.float64]
) -> None:
    back = t.inverse().apply_points(t.apply_points(p))
    assert np.max(np.abs(back - p)) <= ROUND_TRIP_MM
    identity = t.inverse().after(t)
    assert (identity.from_frame, identity.to_frame) == (SCAN, SCAN)
    assert np.max(np.abs(identity.matrix - np.eye(4))) <= ROUND_TRIP_MM


@pytest.mark.parametrize(
    "mirror",
    [
        np.diag([-1.0, 1, 1, 1]),  # left <-> right
        np.diag([1.0, -1, 1, 1]),
        np.diag([1.0, 1, -1, 1]),
        np.diag([-1.0, -1, -1, 1]),  # point reflection
        np.array([[0.0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]),  # axis swap
    ],
)
def test_completion_criterion_reflection_is_rejected(mirror: NDArray[np.float64]) -> None:
    for m in (mirror, mirror @ np.block([[rot_z(37.0), np.zeros((3, 1))], [np.zeros((1, 3)), 1]])):
        assert check_rigid(m) == REFLECTION_REJECTED
        with pytest.raises(RigidTransformError) as exc:
            RigidTransform.create(m, from_frame=ANAT, to_frame=EXPORT)
        assert exc.value.reason_code == REFLECTION_REJECTED


@settings(max_examples=200, deadline=None)
@given(t=rigid, axis=st.integers(0, 2))
def test_property_any_mirrored_rigid_transform_is_rejected(t: RigidTransform, axis: int) -> None:
    mirror = np.eye(4)
    mirror[axis, axis] = -1.0
    assert check_rigid(t.matrix @ mirror) == REFLECTION_REJECTED


# --- guard ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "matrix",
    [
        np.diag([1.001, 1, 1, 1]),  # scale
        np.diag([2.0, 2, 2, 1]),
        np.array([[1.0, 0.01, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]),  # shear
        np.array([[1.0, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1e-3, 1]]),  # projective row
        np.diag([1.0, 1, 1, 2]),
    ],
)
def test_non_rigid_is_rejected(matrix: NDArray[np.float64]) -> None:
    assert check_rigid(matrix) == TRANSFORM_NOT_RIGID
    with pytest.raises(RigidTransformError):
        RigidTransform.create(matrix, from_frame=SCAN, to_frame=ANAT)


def test_tolerance_is_the_ds06_value() -> None:
    assert RIGID_TOLERANCE == 1e-9
    near = np.eye(4)
    near[0, 0] = 1 + 0.4e-9  # det and orthonormality inside 1e-9
    assert check_rigid(near) is None
    far = np.eye(4)
    far[0, 0] = 1 + 2e-9
    assert check_rigid(far) == TRANSFORM_NOT_RIGID


@pytest.mark.parametrize(
    "bad", [np.eye(3), np.zeros(15), np.full((4, 4), np.nan), np.diag([1.0, 1, 1, np.inf])]
)
def test_malformed_matrix_is_a_programming_error(bad: Any) -> None:
    with pytest.raises(KernelContractError):
        check_rigid(bad)


def test_row_major_16_values_are_accepted_and_kept() -> None:
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = rot_z(30.0), [1.0, -2.0, 3.5]
    t = RigidTransform.create(m.ravel().tolist(), from_frame=SCAN, to_frame=ANAT)
    assert t.as_row_major() == m.ravel().tolist() and abs(t.det - 1.0) <= RIGID_TOLERANCE
    with pytest.raises(ValueError):
        t.matrix[0, 0] = 2.0  # read-only


# --- algebra --------------------------------------------------------------------------------------


def test_compose_checks_frames_and_order() -> None:
    a = RigidTransform.from_rotation_translation(rot_z(90), [10.0, 0, 0], from_frame=SCAN,
                                                 to_frame=ANAT)  # fmt: skip
    b = RigidTransform.from_rotation_translation(np.eye(3), [0.0, 5, 0], from_frame=ANAT,
                                                 to_frame=EXPORT)  # fmt: skip
    ba = b.after(a)
    assert (ba.from_frame, ba.to_frame) == (SCAN, EXPORT)
    p = np.array([[1.0, 0, 0]])
    assert np.allclose(ba.apply_points(p), b.apply_points(a.apply_points(p)), atol=1e-12, rtol=0)
    assert np.allclose(ba.apply_points(p), [[10.0, 6.0, 0.0]], atol=1e-12, rtol=0)
    with pytest.raises(KernelContractError, match="do not chain"):
        a.after(b)  # EXPORT -> ? does not feed SCAN
    with pytest.raises(KernelContractError, match="do not chain"):
        a.after(a)


def test_inverse_swaps_frames_and_uses_the_transpose() -> None:
    t = RigidTransform.from_rotation_translation(rot_z(30), [3.0, 4, 5], from_frame=SCAN,
                                                 to_frame=ANAT)  # fmt: skip
    inv = t.inverse()
    assert (inv.from_frame, inv.to_frame) == (ANAT, SCAN)
    assert np.array_equal(inv.rotation, t.rotation.T)
    assert np.array_equal(inv.translation, -(t.rotation.T @ t.translation))


def test_directions_ignore_the_translation() -> None:
    t = RigidTransform.from_rotation_translation(rot_z(90), [100.0, 200, 300], from_frame=SCAN,
                                                 to_frame=ANAT)  # fmt: skip
    d = t.apply_directions(np.array([[1.0, 0, 0]]))
    assert np.allclose(d, [[0.0, 1.0, 0.0]], atol=1e-15, rtol=0)
    assert np.allclose(np.linalg.norm(d, axis=1), 1.0, atol=1e-15, rtol=0)


@settings(max_examples=100, deadline=None)
@given(t=rigid, p=points)
def test_property_distances_and_handedness_are_preserved(
    t: RigidTransform, p: NDArray[np.float64]
) -> None:
    q = t.apply_points(p)
    d_before = np.linalg.norm(p[:, None] - p[None], axis=2)
    d_after = np.linalg.norm(q[:, None] - q[None], axis=2)
    assert np.max(np.abs(d_after - d_before)) <= 1e-9  # rigid: no scale
    assert abs(t.det - 1.0) <= RIGID_TOLERANCE  # det preserved, never -1


def test_repeated_composition_drift() -> None:
    t = RigidTransform.from_rotation_translation(quat_rotation(np.array([0.3, -0.5, 0.7, 0.2])),
                                                 [12.5, -80.0, 301.25], from_frame=SCAN,
                                                 to_frame=SCAN)  # fmt: skip
    acc = RigidTransform.identity(SCAN)
    for _ in range(1000):
        acc = t.inverse().after(t.after(acc))  # every step must return to the identity
    assert np.max(np.abs(acc.matrix - np.eye(4))) <= ROUND_TRIP_MM


def test_point_contract() -> None:
    t = RigidTransform.identity(SCAN)
    for bad in (np.zeros(3), np.zeros((2, 2)), np.array([[np.nan, 0, 0]])):
        with pytest.raises(KernelContractError):
            t.apply_points(bad)
    with pytest.raises(KernelContractError, match="frame"):
        RigidTransform.create(np.eye(4), from_frame="F_world", to_frame=SCAN)


# --- nearest rotation (construction only) ---------------------------------------------------------


def test_nearest_rotation_repairs_near_rotations_and_refuses_mirrors() -> None:
    noisy = rot_z(20.0) + 1e-7 * np.array([[1, 2, 0], [0, -1, 3], [2, 0, 1]])
    assert check_rigid(np.block([[noisy, np.zeros((3, 1))], [np.zeros((1, 3)), 1]])) is not None
    r = nearest_rotation(noisy)
    m = np.eye(4)
    m[:3, :3] = r
    assert check_rigid(m) is None and np.max(np.abs(r - rot_z(20.0))) < 1e-6
    with pytest.raises(RigidTransformError) as exc:
        nearest_rotation(np.diag([-1.0, 1, 1]))
    assert exc.value.reason_code == REFLECTION_REJECTED
