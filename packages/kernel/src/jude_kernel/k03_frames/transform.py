"""FN-KFR-03 Transform algebra and reflection guard (ALG-32, DS-06; SAF-03, FR-031, ADR-009).

The single implementation of 4x4 rigid transforms with explicit frames. A ``RigidTransform``
maps points given in ``from_frame`` to ``to_frame``:

    T = [[R, t], [0 0 0 1]],   x_to = R x_from + t

**Guard (INV-06).** Every transform passes the guard at construction. The tolerance is the one
DS-06 / ALG-32 state for stored transforms, the same that migration 0001 enforces on
``geometry.frame``:

- finite values, bottom row exactly ``0 0 0 1``;
- det R < 0 (a mirror: left and right swapped) -> ``REFLECTION_REJECTED`` (SAF-03);
- ``|det R - 1| > 1e-9`` or ``||R^T R - I||_F > 1e-9`` (scale, shear, a non-rotation) ->
  ``TRANSFORM_NOT_RIGID``.

``check_rigid`` returns the reason code, for ops that turn it into ``OpOutcome.rejected``.
``RigidTransform.create`` raises ``RigidTransformError`` carrying the code.

**Algebra.**

- ``b.after(a)`` is b ∘ a (first a, then b). It needs ``a.to_frame == b.from_frame``; a
  mismatch is a programming error (``KernelContractError``).
- ``inverse`` is ``[[R^T, -R^T t], [0, 1]]``, which is exact for a rotation, with the frames
  swapped. The result is checked by the guard like any other transform.
- ``apply_points`` applies R and t; ``apply_directions`` applies R only (normals, axes).
- ``nearest_rotation`` re-orthonormalises a near-rotation by polar decomposition (SVD). It is
  meant for construction only (ALG-32); nothing re-orthonormalises silently afterwards. It
  refuses a reflection rather than "fixing" it.

All arithmetic is float64 numpy, element-wise or small fixed-size matmul: pure, deterministic,
no randomness.
"""

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import Frame

# DS-06 / ALG-32 validity tolerance for stored rigid transforms (not an ad-hoc epsilon).
RIGID_TOLERANCE: Final = 1e-9
REFLECTION_REJECTED: Final = "REFLECTION_REJECTED"
TRANSFORM_NOT_RIGID: Final = "TRANSFORM_NOT_RIGID"
_BOTTOM: Final = np.array([0.0, 0.0, 0.0, 1.0])
_F64: Final = np.dtype("<f8")


class RigidTransformError(KernelContractError):
    """A matrix failed the guard; ``reason_code`` is REFLECTION_REJECTED or TRANSFORM_NOT_RIGID."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code


def _matrix(values: Any) -> NDArray[np.float64]:
    m = np.array(values, dtype=_F64, order="C", copy=True)
    if m.shape == (16,):
        m = m.reshape(4, 4)
    if m.shape != (4, 4):
        raise KernelContractError(f"matrix: shape (4, 4) or (16,) required, got {m.shape}")
    if not np.all(np.isfinite(m)):
        raise KernelContractError("matrix: values must be finite")
    return m


def _guard(m: NDArray[np.float64]) -> tuple[str, str] | None:
    if not np.array_equal(m[3], _BOTTOM):
        return TRANSFORM_NOT_RIGID, "bottom row must be exactly 0 0 0 1"
    r = m[:3, :3]
    det = float(np.linalg.det(r))
    if det < 0:
        return REFLECTION_REJECTED, f"det R = {det!r} < 0 (mirror)"
    ortho = float(np.linalg.norm(r.T @ r - np.eye(3), ord="fro"))
    if abs(det - 1.0) > RIGID_TOLERANCE or ortho > RIGID_TOLERANCE:
        return TRANSFORM_NOT_RIGID, f"det R = {det!r}, ||R^T R - I||_F = {ortho!r}"
    return None


def check_rigid(matrix: Any) -> str | None:
    """The guard's reason code (REFLECTION_REJECTED / TRANSFORM_NOT_RIGID), or None if rigid."""
    found = _guard(_matrix(matrix))
    return None if found is None else found[0]


def _frame(value: Frame | str, name: str) -> Frame:
    try:
        return Frame(value)
    except ValueError as exc:
        raise KernelContractError(f"{name}: unknown frame tag {value!r}") from exc


@dataclass(frozen=True, eq=False)
class RigidTransform:
    """A guarded rigid transform ``from_frame -> to_frame``. Build with ``create``."""

    matrix: NDArray[np.float64]
    from_frame: Frame
    to_frame: Frame

    @classmethod
    def create(
        cls, matrix: Any, *, from_frame: Frame | str, to_frame: Frame | str
    ) -> "RigidTransform":
        m = _matrix(matrix)
        found = _guard(m)
        if found is not None:
            raise RigidTransformError(*found)
        m.setflags(write=False)
        return cls(m, _frame(from_frame, "from_frame"), _frame(to_frame, "to_frame"))

    @classmethod
    def from_rotation_translation(
        cls, rotation: Any, translation: Any, *, from_frame: Frame | str, to_frame: Frame | str
    ) -> "RigidTransform":
        r = np.asarray(rotation, dtype=_F64)
        t = np.asarray(translation, dtype=_F64)
        if r.shape != (3, 3) or t.shape != (3,):
            raise KernelContractError("rotation (3, 3) and translation (3,) required")
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = r, t
        return cls.create(m, from_frame=from_frame, to_frame=to_frame)

    @classmethod
    def identity(cls, frame: Frame | str) -> "RigidTransform":
        return cls.create(np.eye(4), from_frame=frame, to_frame=frame)

    @property
    def rotation(self) -> NDArray[np.float64]:
        return self.matrix[:3, :3]

    @property
    def translation(self) -> NDArray[np.float64]:
        return self.matrix[:3, 3]

    @property
    def det(self) -> float:
        """det R, stored with the matrix (DS-06)."""
        return float(np.linalg.det(self.rotation))

    def after(self, first: "RigidTransform") -> "RigidTransform":
        """self ∘ first: apply ``first`` (F1 -> F2), then ``self`` (F2 -> F3)."""
        if first.to_frame is not self.from_frame:
            raise KernelContractError(
                f"compose: {first.from_frame}->{first.to_frame} then "
                f"{self.from_frame}->{self.to_frame} (frame tags do not chain)"
            )
        m = self.matrix @ first.matrix
        m[3] = _BOTTOM  # exact by construction; the product of exact 0/1 rows is exact anyway
        return RigidTransform.create(m, from_frame=first.from_frame, to_frame=self.to_frame)

    def inverse(self) -> "RigidTransform":
        rt = self.rotation.T
        m = np.eye(4)
        m[:3, :3] = rt
        m[:3, 3] = -(rt @ self.translation)
        return RigidTransform.create(m, from_frame=self.to_frame, to_frame=self.from_frame)

    def apply_points(self, points: Any) -> NDArray[np.float64]:
        p = _points(points)
        return p @ self.rotation.T + self.translation

    def apply_directions(self, directions: Any) -> NDArray[np.float64]:
        return _points(directions) @ self.rotation.T

    def as_row_major(self) -> list[float]:
        """The 16 values as DS-06 stores them."""
        return [float(x) for x in self.matrix.ravel()]


def _points(values: Any) -> NDArray[np.float64]:
    p = np.asarray(values, dtype=_F64)
    if p.ndim != 2 or p.shape[1] != 3:
        raise KernelContractError(f"points: shape (n, 3) required, got {p.shape}")
    if not np.all(np.isfinite(p)):
        raise KernelContractError("points: values must be finite")
    return p


def nearest_rotation(matrix: Any) -> NDArray[np.float64]:
    """Polar decomposition: the rotation closest to a 3x3 near-rotation (construction only).

    A reflection (det < 0) is refused with REFLECTION_REJECTED, never turned into a rotation.
    """
    a = np.asarray(matrix, dtype=_F64)
    if a.shape != (3, 3) or not np.all(np.isfinite(a)):
        raise KernelContractError("nearest_rotation: finite (3, 3) matrix required")
    if float(np.linalg.det(a)) <= 0:
        raise RigidTransformError(REFLECTION_REJECTED, "det <= 0: not a rotation to repair")
    u, _, vt = np.linalg.svd(a)
    r: NDArray[np.float64] = u @ vt
    return r
