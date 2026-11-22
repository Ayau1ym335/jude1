"""Exact geometric predicates orient2d / orient3d (XC-SHR-01; TD-04, ALG-11, ALG-25, ALG-35).

Port of Jonathan Shewchuk's adaptive-precision predicates (public domain, LIB-PREDICATES):
a floating-point filter with his static error bound decides almost every case; when it cannot,
the sign is computed exactly with floating-point expansion arithmetic. Every result is the sign
of the exact determinant of the input doubles: no epsilon, no tolerance (DEC-025 does not apply
to signs).

Sign conventions (FUNCTION_TECHNICAL_SPECIFICATIONS, FN-KVL-05):

- ``orient2d(a, b, c) = sign det[b - a, c - a]``: +1 if a, b, c turn counter-clockwise,
  -1 if clockwise, 0 if collinear. Same sign as Shewchuk's orient2d.
- ``orient3d(a, b, c, d) = sign det[b - a, c - a, d - a] = sign (d - a) . ((b - a) x (c - a))``:
  +1 if d lies on the side of plane (a, b, c) that the normal (b - a) x (c - a) points to,
  -1 on the other side, 0 if coplanar. This is the **negative** of Shewchuk's orient3d.

Exactness domain. Expansion arithmetic is exact as long as nothing overflows or underflows.
Every coordinate that is 0 or has 2**-200 <= |x| <= 2**200 is a multiple of 2**-252, so all
intermediate exact values are multiples of 2**-756 and below 2**610: no underflow, no overflow.
Inside numba code a call with any coordinate outside this domain returns ``OUT_OF_DOMAIN``
instead of a sign; the array functions below resolve those rows with exact rational arithmetic
(``fractions.Fraction``), so they are exact for every finite input. Non-finite input is a
contract error.

Changes from Shewchuk's C code:

- the intermediate adaptive stages B-D are not ported; a case the filter cannot decide goes
  straight to the full exact evaluation (simpler to verify; only the speed of rare cases
  differs, never the result);
- ``grow_expansion`` sums replace ``fast_expansion_sum`` (needs only nonoverlapping inputs,
  not strongly nonoverlapping ones).
"""

from fractions import Fraction
from typing import Final

import numpy as np
from numpy.typing import ArrayLike, NDArray

from jude_kernel.core.errors import KernelContractError
from jude_kernel.shared.jit import kernel_jit

EPSILON: Final = 2.0**-53  # half an ulp of 1.0 (round-to-nearest-even)
SPLITTER: Final = 2.0**27 + 1.0  # Dekker split of a 53-bit significand into 26 + 26 bits
CCW_ERRBOUND_A: Final = (3.0 + 16.0 * EPSILON) * EPSILON
O3D_ERRBOUND_A: Final = (7.0 + 56.0 * EPSILON) * EPSILON
DOMAIN_MIN: Final = 2.0**-200
DOMAIN_MAX: Final = 2.0**200

OUT_OF_DOMAIN: Final = 2  # numba-level result: a coordinate is outside the exactness domain
UNDECIDED: Final = 3  # filter result: the float filter cannot certify the sign


# ---------------------------------------------------------------------------------------------
# Error-free transformations (Knuth, Dekker; Shewchuk 1997 §2)
# ---------------------------------------------------------------------------------------------
@kernel_jit
def _two_sum(a: float, b: float) -> tuple[float, float]:
    x = a + b
    bv = x - a
    av = x - bv
    br = b - bv
    ar = a - av
    return x, ar + br


@kernel_jit
def _fast_two_sum(a: float, b: float) -> tuple[float, float]:
    """Requires |a| >= |b| (or a == 0)."""
    x = a + b
    bv = x - a
    return x, b - bv


@kernel_jit
def _two_diff(a: float, b: float) -> tuple[float, float]:
    x = a - b
    bv = a - x
    av = x + bv
    br = bv - b
    ar = a - av
    return x, ar + br


@kernel_jit
def _split(a: float) -> tuple[float, float]:
    c = SPLITTER * a
    abig = c - a
    ahi = c - abig
    return ahi, a - ahi


@kernel_jit
def _two_product(a: float, b: float) -> tuple[float, float]:
    x = a * b
    ahi, alo = _split(a)
    bhi, blo = _split(b)
    err1 = x - ahi * bhi
    err2 = err1 - alo * bhi
    err3 = err2 - ahi * blo
    return x, alo * blo - err3


# ---------------------------------------------------------------------------------------------
# Expansions: float64 arrays, nonoverlapping components in increasing magnitude, zero-free
# (a zero value is the one-component expansion [0.0]). The sign is that of the last component.
# ---------------------------------------------------------------------------------------------
@kernel_jit
def _grow(e: NDArray[np.float64], b: float) -> NDArray[np.float64]:
    h = np.empty(e.shape[0] + 1, dtype=np.float64)
    n = 0
    q = b
    for i in range(e.shape[0]):
        q, hh = _two_sum(q, e[i])
        if hh != 0.0:
            h[n] = hh
            n += 1
    if q != 0.0 or n == 0:
        h[n] = q
        n += 1
    return h[:n].copy()


@kernel_jit
def _add(e: NDArray[np.float64], f: NDArray[np.float64]) -> NDArray[np.float64]:
    h = e.copy()
    for i in range(f.shape[0]):
        h = _grow(h, f[i])
    return h


@kernel_jit
def _scale(e: NDArray[np.float64], b: float) -> NDArray[np.float64]:
    h = np.empty(2 * e.shape[0], dtype=np.float64)
    n = 0
    q, hh = _two_product(e[0], b)
    if hh != 0.0:
        h[n] = hh
        n += 1
    for i in range(1, e.shape[0]):
        p1, p0 = _two_product(e[i], b)
        s, hh = _two_sum(q, p0)
        if hh != 0.0:
            h[n] = hh
            n += 1
        q, hh = _fast_two_sum(p1, s)
        if hh != 0.0:
            h[n] = hh
            n += 1
    if q != 0.0 or n == 0:
        h[n] = q
        n += 1
    return h[:n].copy()


@kernel_jit
def _mul(e: NDArray[np.float64], f: NDArray[np.float64]) -> NDArray[np.float64]:
    h = _scale(e, f[0])
    for j in range(1, f.shape[0]):
        h = _add(h, _scale(e, f[j]))
    return h


@kernel_jit
def _sub(e: NDArray[np.float64], f: NDArray[np.float64]) -> NDArray[np.float64]:
    return _add(e, -f)


@kernel_jit
def _diff(a: float, b: float) -> NDArray[np.float64]:
    """Exact a - b as an expansion of one or two components."""
    hi, lo = _two_diff(a, b)
    if lo == 0.0:
        out = np.empty(1, dtype=np.float64)
        out[0] = hi
    else:
        out = np.empty(2, dtype=np.float64)
        out[0] = lo
        out[1] = hi
    return out


@kernel_jit
def _sign_of(x: float) -> int:
    if x > 0.0:
        return 1
    if x < 0.0:
        return -1
    return 0


@kernel_jit
def _in_domain(x: float) -> bool:
    m = abs(x)
    return m == 0.0 or (m >= DOMAIN_MIN and m <= DOMAIN_MAX)


# ---------------------------------------------------------------------------------------------
# orient2d
# ---------------------------------------------------------------------------------------------
@kernel_jit
def _orient2d_filter(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> int:
    """Sign if Shewchuk's stage-A bound certifies it, else UNDECIDED."""
    detleft = (bx - ax) * (cy - ay)
    detright = (by - ay) * (cx - ax)
    det = detleft - detright
    if detleft > 0.0:
        if detright <= 0.0:
            return _sign_of(det)
        detsum = detleft + detright
    elif detleft < 0.0:
        if detright >= 0.0:
            return _sign_of(det)
        detsum = -detleft - detright
    else:
        return _sign_of(det)
    errbound = CCW_ERRBOUND_A * detsum
    if det >= errbound or -det >= errbound:
        return _sign_of(det)
    return UNDECIDED


@kernel_jit
def _orient2d_exact(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> int:
    ux = _diff(bx, ax)
    uy = _diff(by, ay)
    vx = _diff(cx, ax)
    vy = _diff(cy, ay)
    det = _sub(_mul(ux, vy), _mul(uy, vx))
    return _sign_of(det[det.shape[0] - 1])


@kernel_jit
def orient2d_nb(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> int:
    """For numba callers: -1, 0, +1, or OUT_OF_DOMAIN (see module docstring)."""
    if not (
        _in_domain(ax)
        and _in_domain(ay)
        and _in_domain(bx)
        and _in_domain(by)
        and _in_domain(cx)
        and _in_domain(cy)
    ):
        return OUT_OF_DOMAIN
    s = _orient2d_filter(ax, ay, bx, by, cx, cy)
    if s != UNDECIDED:
        return s
    return _orient2d_exact(ax, ay, bx, by, cx, cy)


# ---------------------------------------------------------------------------------------------
# orient3d
# ---------------------------------------------------------------------------------------------
@kernel_jit
def _orient3d_filter(
    ax: float, ay: float, az: float,
    bx: float, by: float, bz: float,
    cx: float, cy: float, cz: float,
    dx: float, dy: float, dz: float,
) -> int:  # fmt: skip
    """Sign if Shewchuk's stage-A bound certifies it, else UNDECIDED.

    Same expression tree as Shewchuk's orient3d with rows (b - a, c - a, d - a) in place of
    (a - d, b - d, c - d), so his bound applies unchanged.
    """
    ux = bx - ax
    uy = by - ay
    uz = bz - az
    vx = cx - ax
    vy = cy - ay
    vz = cz - az
    wx = dx - ax
    wy = dy - ay
    wz = dz - az
    vxwy = vx * wy
    wxvy = wx * vy
    wxuy = wx * uy
    uxwy = ux * wy
    uxvy = ux * vy
    vxuy = vx * uy
    det = uz * (vxwy - wxvy) + vz * (wxuy - uxwy) + wz * (uxvy - vxuy)
    permanent = (
        (abs(vxwy) + abs(wxvy)) * abs(uz)
        + (abs(wxuy) + abs(uxwy)) * abs(vz)
        + (abs(uxvy) + abs(vxuy)) * abs(wz)
    )
    errbound = O3D_ERRBOUND_A * permanent
    if det > errbound or -det > errbound:
        return _sign_of(det)
    return UNDECIDED


@kernel_jit
def _orient3d_exact(
    ax: float, ay: float, az: float,
    bx: float, by: float, bz: float,
    cx: float, cy: float, cz: float,
    dx: float, dy: float, dz: float,
) -> int:  # fmt: skip
    ux = _diff(bx, ax)
    uy = _diff(by, ay)
    uz = _diff(bz, az)
    vx = _diff(cx, ax)
    vy = _diff(cy, ay)
    vz = _diff(cz, az)
    wx = _diff(dx, ax)
    wy = _diff(dy, ay)
    wz = _diff(dz, az)
    m1 = _sub(_mul(vx, wy), _mul(wx, vy))
    m2 = _sub(_mul(wx, uy), _mul(ux, wy))
    m3 = _sub(_mul(ux, vy), _mul(vx, uy))
    det = _add(_add(_mul(uz, m1), _mul(vz, m2)), _mul(wz, m3))
    return _sign_of(det[det.shape[0] - 1])


@kernel_jit
def orient3d_nb(
    ax: float, ay: float, az: float,
    bx: float, by: float, bz: float,
    cx: float, cy: float, cz: float,
    dx: float, dy: float, dz: float,
) -> int:  # fmt: skip
    """For numba callers: -1, 0, +1, or OUT_OF_DOMAIN (see module docstring)."""
    if not (
        _in_domain(ax) and _in_domain(ay) and _in_domain(az)
        and _in_domain(bx) and _in_domain(by) and _in_domain(bz)
        and _in_domain(cx) and _in_domain(cy) and _in_domain(cz)
        and _in_domain(dx) and _in_domain(dy) and _in_domain(dz)
    ):  # fmt: skip
        return OUT_OF_DOMAIN
    s = _orient3d_filter(ax, ay, az, bx, by, bz, cx, cy, cz, dx, dy, dz)
    if s != UNDECIDED:
        return s
    return _orient3d_exact(ax, ay, az, bx, by, bz, cx, cy, cz, dx, dy, dz)


# ---------------------------------------------------------------------------------------------
# Array API
# ---------------------------------------------------------------------------------------------
@kernel_jit
def _orient2d_rows(
    a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64]
) -> NDArray[np.int8]:
    out = np.empty(a.shape[0], dtype=np.int8)
    for i in range(a.shape[0]):
        out[i] = orient2d_nb(a[i, 0], a[i, 1], b[i, 0], b[i, 1], c[i, 0], c[i, 1])
    return out


@kernel_jit
def _orient3d_rows(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    d: NDArray[np.float64],
) -> NDArray[np.int8]:
    out = np.empty(a.shape[0], dtype=np.int8)
    for i in range(a.shape[0]):
        out[i] = orient3d_nb(
            a[i, 0], a[i, 1], a[i, 2],
            b[i, 0], b[i, 1], b[i, 2],
            c[i, 0], c[i, 1], c[i, 2],
            d[i, 0], d[i, 1], d[i, 2],
        )  # fmt: skip
    return out


# Path-specific row functions: diagnostics and tests check the filter and the exact
# evaluation separately (the public functions combine them).
@kernel_jit
def _orient2d_rows_by(
    a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64], exact: bool
) -> NDArray[np.int8]:
    out = np.empty(a.shape[0], dtype=np.int8)
    for i in range(a.shape[0]):
        args = (a[i, 0], a[i, 1], b[i, 0], b[i, 1], c[i, 0], c[i, 1])
        out[i] = _orient2d_exact(*args) if exact else _orient2d_filter(*args)
    return out


@kernel_jit
def _orient3d_rows_by(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    d: NDArray[np.float64],
    exact: bool,
) -> NDArray[np.int8]:
    out = np.empty(a.shape[0], dtype=np.int8)
    for i in range(a.shape[0]):
        args = (
            a[i, 0], a[i, 1], a[i, 2],
            b[i, 0], b[i, 1], b[i, 2],
            c[i, 0], c[i, 1], c[i, 2],
            d[i, 0], d[i, 1], d[i, 2],
        )  # fmt: skip
        out[i] = _orient3d_exact(*args) if exact else _orient3d_filter(*args)
    return out


def _points(name: str, value: ArrayLike, dim: int) -> NDArray[np.float64]:
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != dim:
        raise KernelContractError(f"{name} must have shape (n, {dim}) or ({dim},)")
    if not np.isfinite(arr).all():
        raise KernelContractError(f"{name} contains non-finite coordinates")
    return np.ascontiguousarray(arr)


def _same_rows(*arrays: NDArray[np.float64]) -> None:
    if len({a.shape[0] for a in arrays}) != 1:
        raise KernelContractError("all point arrays must have the same number of rows")


def _rational_sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def _orient2d_rational(
    a: NDArray[np.float64], b: NDArray[np.float64], c: NDArray[np.float64]
) -> int:
    ax, ay = (Fraction(float(x)) for x in a)
    bx, by = (Fraction(float(x)) for x in b)
    cx, cy = (Fraction(float(x)) for x in c)
    return _rational_sign((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))


def _orient3d_rational(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    c: NDArray[np.float64],
    d: NDArray[np.float64],
) -> int:
    ax, ay, az = (Fraction(float(x)) for x in a)
    ux, uy, uz = (Fraction(float(x)) - p for x, p in zip(b, (ax, ay, az), strict=True))
    vx, vy, vz = (Fraction(float(x)) - p for x, p in zip(c, (ax, ay, az), strict=True))
    wx, wy, wz = (Fraction(float(x)) - p for x, p in zip(d, (ax, ay, az), strict=True))
    det = ux * (vy * wz - vz * wy) - uy * (vx * wz - vz * wx) + uz * (vx * wy - vy * wx)
    return _rational_sign(det)


def orient2d(a: ArrayLike, b: ArrayLike, c: ArrayLike) -> NDArray[np.int8]:
    """Row-wise sign of det[b - a, c - a] for points of shape (n, 2) (or a single (2,) point).

    Exact for every finite input. Returns int8 values in {-1, 0, 1}.
    """
    pa, pb, pc = _points("a", a, 2), _points("b", b, 2), _points("c", c, 2)
    _same_rows(pa, pb, pc)
    out = _orient2d_rows(pa, pb, pc)
    for i in np.flatnonzero(out == OUT_OF_DOMAIN):
        out[i] = _orient2d_rational(pa[i], pb[i], pc[i])
    return out


def orient3d(a: ArrayLike, b: ArrayLike, c: ArrayLike, d: ArrayLike) -> NDArray[np.int8]:
    """Row-wise sign of det[b - a, c - a, d - a] for points of shape (n, 3) (or single points).

    Exact for every finite input. Returns int8 values in {-1, 0, 1}.
    """
    pa, pb, pc, pd = (_points(n, v, 3) for n, v in (("a", a), ("b", b), ("c", c), ("d", d)))
    _same_rows(pa, pb, pc, pd)
    out = _orient3d_rows(pa, pb, pc, pd)
    for i in np.flatnonzero(out == OUT_OF_DOMAIN):
        out[i] = _orient3d_rational(pa[i], pb[i], pc[i], pd[i])
    return out


def warm_up() -> None:
    """Compile (or load from cache) every predicate, including the exact path (X-06 §6.4)."""
    z2 = np.zeros((1, 2))
    one2 = np.array([[1.0, 1.0]])
    orient2d(z2, one2, 2.0 * one2)  # collinear: filter undecided -> exact path
    z3 = np.zeros((1, 3))
    orient3d(
        z3, np.array([[1.0, 0.0, 0.0]]), np.array([[0.0, 1.0, 0.0]]), np.array([[1.0, 1.0, 0.0]])
    )
