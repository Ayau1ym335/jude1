"""UT/property tests of the exact predicates (XC-SHR-01, TD-04).

Completion criterion: 100 % agreement with a rational (``fractions.Fraction``) oracle on the
adversarial set T13 (>= 10**5 cases per predicate), and identical results over 100 runs.

T13 is generated here from a fixed seed (stdlib ``random``; the kernel bans numpy.random).
The frozen T13 fixture files come with XC-SHR-03 and will replace this generator as the input.
"""

from collections.abc import Callable, Iterator
from fractions import Fraction
import hashlib
import math
import os
import random
import subprocess
import sys

import numpy as np
from numpy.typing import NDArray
import pytest

from jude_kernel.core.errors import KernelContractError
from jude_kernel.shared import predicates as pred
from jude_kernel.shared.jit import KERNEL_JIT_OPTIONS

SEED = 20261122
ULP_HALF = math.ulp(0.5)  # 2**-53
SCALES = (-1000, -600, -260, -201, -150, 150, 201, 260, 600, 900)  # powers of two

Pts = NDArray[np.float64]


# ---------------------------------------------------------------------------------------------
# Independent rational oracle (does not share code with the kernel's own fallback)
# ---------------------------------------------------------------------------------------------
def _q(x: float) -> Fraction:
    return Fraction(x)


def oracle2d(a: Pts, b: Pts, c: Pts) -> NDArray[np.int8]:
    out = np.empty(a.shape[0], dtype=np.int8)
    for i in range(a.shape[0]):
        ax, ay = _q(a[i, 0]), _q(a[i, 1])
        det = (_q(b[i, 0]) - ax) * (_q(c[i, 1]) - ay) - (_q(b[i, 1]) - ay) * (_q(c[i, 0]) - ax)
        out[i] = (det > 0) - (det < 0)
    return out


def oracle3d(a: Pts, b: Pts, c: Pts, d: Pts) -> NDArray[np.int8]:
    out = np.empty(a.shape[0], dtype=np.int8)
    for i in range(a.shape[0]):
        o = [_q(a[i, k]) for k in range(3)]
        u = [_q(b[i, k]) - o[k] for k in range(3)]
        v = [_q(c[i, k]) - o[k] for k in range(3)]
        w = [_q(d[i, k]) - o[k] for k in range(3)]
        # w . (u x v)
        det = (
            w[0] * (u[1] * v[2] - u[2] * v[1])
            + w[1] * (u[2] * v[0] - u[0] * v[2])
            + w[2] * (u[0] * v[1] - u[1] * v[0])
        )
        out[i] = (det > 0) - (det < 0)
    return out


# ---------------------------------------------------------------------------------------------
# T13 generator: near-collinear / near-coplanar, 1-ulp offsets, exact degeneracies,
# huge / small / subnormal / mixed magnitudes, random
# ---------------------------------------------------------------------------------------------
def _nudge(x: float, k: int) -> float:
    step = math.inf if k > 0 else -math.inf
    for _ in range(abs(k)):
        x = math.nextafter(x, step)
    return x


class _Set:
    def __init__(self, dim: int, npts: int) -> None:
        self.dim, self.npts = dim, npts
        self.rows: list[list[tuple[float, ...]]] = [[] for _ in range(npts)]
        self.cats: list[str] = []

    def add(self, cat: str, *pts: tuple[float, ...]) -> None:
        for slot, p in zip(self.rows, pts, strict=True):
            slot.append(tuple(float(x) for x in p))
        self.cats.append(cat)

    def arrays(self) -> tuple[list[Pts], list[str]]:
        return [np.array(r, dtype=np.float64) for r in self.rows], self.cats


def _scaled(p: tuple[float, ...], k: int) -> tuple[float, ...]:
    return tuple(math.ldexp(x, k) for x in p)


def t13_orient2d(seed: int = SEED) -> tuple[list[Pts], list[str]]:
    rng = random.Random(seed)  # noqa: S311 — reproducible test data
    s = _Set(2, 3)
    # Shewchuk's near-collinear grid: a moves on a 256 x 256 ulp grid around (0.5, 0.5).
    for i in range(-128, 128):
        for j in range(-128, 128):
            s.add("ulp-grid", (0.5 + i * ULP_HALF, 0.5 + j * ULP_HALF), (12.0, 12.0), (24.0, 24.0))
    for i in range(-32, 32):
        for j in range(-32, 32):
            s.add(
                "ulp-grid-2", (0.5 + i * ULP_HALF, 0.5 + j * ULP_HALF), (17.3, 17.3), (24.1, 24.1)
            )
    near: list[tuple[tuple[float, ...], ...]] = []
    for _ in range(10_000):  # a point rounded onto a random line, then nudged by 0..2 ulps
        a = (rng.uniform(-500, 500), rng.uniform(-500, 500))
        b = (rng.uniform(-500, 500), rng.uniform(-500, 500))
        t = rng.uniform(-2, 3)
        c0 = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        for k in (0, 1, -2):
            c = (_nudge(c0[0], k), _nudge(c0[1], rng.choice((-1, 0, 1)) * abs(k)))
            s.add("near-collinear", a, b, c)
            near.append((a, b, c))
    for _ in range(2_000):  # exactly collinear integer points, scaled by 2**k (still exact)
        p = (rng.randint(-1000, 1000), rng.randint(-1000, 1000))
        d = (rng.randint(-50, 50), rng.randint(-50, 50))
        t1, t2 = rng.randint(-20, 20), rng.randint(-20, 20)
        k = rng.randint(-40, 40)
        pts = [(p[0] + t * d[0], p[1] + t * d[1]) for t in (0, t1, t2)]
        s.add("exact-collinear", *(_scaled(q, k) for q in pts))
    for _ in range(1_000):  # duplicate points
        a = (rng.uniform(-500, 500), rng.uniform(-500, 500))
        b = (rng.uniform(-500, 500), rng.uniform(-500, 500))
        s.add("duplicate", *rng.choice(((a, a, b), (a, b, a), (b, a, a), (a, a, a))))
    for na, nb, nc in near[:2_000]:  # magnitudes, including subnormal and out-of-domain
        for k in SCALES:
            s.add(f"scale-2^{k}", _scaled(na, k), _scaled(nb, k), _scaled(nc, k))
    for _ in range(5_000):  # mixed magnitudes within one case
        mixed2 = [
            tuple(math.ldexp(rng.uniform(-1, 1), rng.randint(-1070, 1000)) for _ in range(2))
            for _ in range(3)
        ]
        s.add("mixed-magnitude", *mixed2)
    for _ in range(5_000):
        s.add("random", *[(rng.uniform(-500, 500), rng.uniform(-500, 500)) for _ in range(3)])
    return s.arrays()


def t13_orient3d(seed: int = SEED) -> tuple[list[Pts], list[str]]:
    rng = random.Random(seed + 1)  # noqa: S311 — reproducible test data
    s = _Set(3, 4)

    def rnd() -> tuple[float, float, float]:
        return (rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(-500, 500))

    near: list[tuple[tuple[float, ...], ...]] = []
    for _ in range(35_000):  # d rounded onto plane (a, b, c), then nudged by 0..2 ulps
        a, b, c = rnd(), rnd(), rnd()
        u, v = rng.uniform(-1, 2), rng.uniform(-1, 2)
        d0 = tuple(a[k] + u * (b[k] - a[k]) + v * (c[k] - a[k]) for k in range(3))
        for k in (0, rng.choice((-2, -1, 1, 2))):
            d = tuple(_nudge(x, k * rng.choice((-1, 0, 1))) for x in d0)
            s.add("near-coplanar", a, b, c, d)
            near.append((a, b, c, d))
    planes = (
        ((0.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0), (0.5, 0.5, 1.0)),  # z = x + y
        ((0.1, 0.2, 0.3), (12.0, 7.0, 3.0), (3.0, 11.0, 5.0), (0.5, 0.5, 0.5)),
        (
            (100.0, 100.0, 100.0),
            (101.0, 100.0, 100.0),
            (100.0, 101.0, 100.0),
            (100.25, 100.75, 100.0),
        ),
    )
    for a, b, c, d0 in planes:  # d moves on a 64 x 64 ulp grid in x and y
        for i in range(-32, 32):
            for j in range(-32, 32):
                d = (d0[0] + i * math.ulp(d0[0] or 1.0), d0[1] + j * math.ulp(d0[1] or 1.0), d0[2])
                s.add("ulp-grid", a, b, c, d)
    for _ in range(3_000):  # exactly coplanar integer points, scaled by 2**k
        o = [rng.randint(-1000, 1000) for _ in range(3)]
        e1 = [rng.randint(-30, 30) for _ in range(3)]
        e2 = [rng.randint(-30, 30) for _ in range(3)]
        k = rng.randint(-40, 40)
        pts = []
        for _p in range(4):
            s1, s2 = rng.randint(-10, 10), rng.randint(-10, 10)
            pts.append(_scaled(tuple(o[m] + s1 * e1[m] + s2 * e2[m] for m in range(3)), k))
        s.add("exact-coplanar", *pts)
    for _ in range(3_000):  # degenerate triangles and duplicates
        a, b, d = rnd(), rnd(), rnd()
        t = rng.uniform(-2, 3)
        cc = tuple(a[k] + t * (b[k] - a[k]) for k in range(3))  # (nearly) collinear a, b, cc
        s.add("degenerate", *rng.choice(((a, b, cc, d), (a, a, b, d), (a, b, d, d), (a, b, a, d))))
    for quad in near[:2_000]:
        for k in SCALES:
            s.add(f"scale-2^{k}", *(_scaled(p, k) for p in quad))
    for _ in range(5_000):
        pts = [
            tuple(math.ldexp(rng.uniform(-1, 1), rng.randint(-1070, 1000)) for _ in range(3))
            for _ in range(4)
        ]
        s.add("mixed-magnitude", *pts)
    for _ in range(5_000):
        s.add("random", rnd(), rnd(), rnd(), rnd())
    return s.arrays()


@pytest.fixture(scope="module")
def t13_2d() -> tuple[list[Pts], list[str], NDArray[np.int8]]:
    pts, cats = t13_orient2d()
    return pts, cats, oracle2d(*pts)


@pytest.fixture(scope="module")
def t13_3d() -> tuple[list[Pts], list[str], NDArray[np.int8]]:
    pts, cats = t13_orient3d()
    return pts, cats, oracle3d(*pts)


def _mismatches(got: NDArray[np.int8], want: NDArray[np.int8], cats: list[str]) -> list[str]:
    bad = np.flatnonzero(got != want)
    return [f"#{i} {cats[i]}: got {got[i]} want {want[i]}" for i in bad[:10]]


# ---------------------------------------------------------------------------------------------
# Completion criterion: 100 % agreement on T13
# ---------------------------------------------------------------------------------------------
def test_t13_size_and_coverage(t13_2d: tuple, t13_3d: tuple) -> None:  # type: ignore[type-arg]
    for _pts, cats, want in (t13_2d, t13_3d):
        assert len(cats) >= 100_000
        assert {-1, 0, 1} <= set(np.unique(want).tolist())  # all three signs occur
    zeros2 = int((t13_2d[2] == 0).sum())
    zeros3 = int((t13_3d[2] == 0).sum())
    assert zeros2 > 1_000 and zeros3 > 1_000  # many exactly degenerate cases


def test_orient2d_agrees_with_rational_oracle_on_t13(t13_2d: tuple) -> None:  # type: ignore[type-arg]
    pts, cats, want = t13_2d
    got = pred.orient2d(*pts)
    assert _mismatches(got, want, cats) == []


def test_orient3d_agrees_with_rational_oracle_on_t13(t13_3d: tuple) -> None:  # type: ignore[type-arg]
    pts, cats, want = t13_3d
    got = pred.orient3d(*pts)
    assert _mismatches(got, want, cats) == []


def _exact2d_rows(a: Pts, b: Pts, c: Pts) -> NDArray[np.int8]:
    return pred._orient2d_rows_by(a, b, c, True)


def _filter2d_rows(a: Pts, b: Pts, c: Pts) -> NDArray[np.int8]:
    return pred._orient2d_rows_by(a, b, c, False)


def _exact3d_rows(a: Pts, b: Pts, c: Pts, d: Pts) -> NDArray[np.int8]:
    return pred._orient3d_rows_by(a, b, c, d, True)


def _filter3d_rows(a: Pts, b: Pts, c: Pts, d: Pts) -> NDArray[np.int8]:
    return pred._orient3d_rows_by(a, b, c, d, False)


def _in_domain(*pts: Pts) -> NDArray[np.bool_]:
    ok = np.ones(pts[0].shape[0], dtype=bool)
    for p in pts:
        m = np.abs(p)
        ok &= ((m == 0) | ((m >= pred.DOMAIN_MIN) & (m <= pred.DOMAIN_MAX))).all(axis=1)
    return ok


def test_exact_path_alone_agrees_on_every_in_domain_case(t13_2d: tuple, t13_3d: tuple) -> None:  # type: ignore[type-arg]
    """The filter decides most cases; this checks the expansion arithmetic on all of them."""
    pts, cats, want = t13_2d
    ok = _in_domain(*pts)
    got = _exact2d_rows(*(p[ok] for p in pts))
    assert _mismatches(got, want[ok], [c for c, k in zip(cats, ok, strict=True) if k]) == []
    pts, cats, want = t13_3d
    ok = _in_domain(*pts)
    got = _exact3d_rows(*(p[ok] for p in pts))
    assert _mismatches(got, want[ok], [c for c, k in zip(cats, ok, strict=True) if k]) == []


def test_filter_is_never_wrong_when_it_decides(t13_2d: tuple, t13_3d: tuple) -> None:  # type: ignore[type-arg]
    for rows, (pts, _cats, want) in ((_filter2d_rows, t13_2d), (_filter3d_rows, t13_3d)):
        ok = _in_domain(*pts)
        got = rows(*(p[ok] for p in pts))
        decided = got != pred.UNDECIDED
        assert (got[decided] == want[ok][decided]).all()
        assert 0 < decided.sum() < decided.size  # both paths are exercised by T13


def test_out_of_domain_rows_are_resolved_exactly(t13_3d: tuple) -> None:  # type: ignore[type-arg]
    pts, _cats, want = t13_3d
    out = ~_in_domain(*pts)
    assert out.sum() > 1_000
    assert (pred.orient3d(*(p[out] for p in pts)) == want[out]).all()


# ---------------------------------------------------------------------------------------------
# Error-free transformations (catch FMA contraction or reassociation by the compiler)
# ---------------------------------------------------------------------------------------------
def _floats(n: int) -> Iterator[float]:
    rng = random.Random(SEED + 7)  # noqa: S311 — reproducible test data
    for _ in range(n):
        yield math.ldexp(rng.uniform(1, 2) * rng.choice((-1, 1)), rng.randint(-300, 300))


def test_two_product_and_two_sum_are_exact() -> None:
    xs = list(_floats(4_000))
    for a, b in zip(xs[::2], xs[1::2], strict=True):
        x, y = pred._two_product(a, b)
        assert Fraction(x) + Fraction(y) == Fraction(a) * Fraction(b)
        assert x == a * b
        x, y = pred._two_sum(a, b)
        assert Fraction(x) + Fraction(y) == Fraction(a) + Fraction(b)
        x, y = pred._two_diff(a, b)
        assert Fraction(x) + Fraction(y) == Fraction(a) - Fraction(b)


def test_expansion_product_is_exact() -> None:
    xs = list(_floats(400))
    for i in range(0, 400, 4):
        e = pred._diff(xs[i], xs[i + 1])
        f = pred._diff(xs[i + 2], xs[i + 3])
        h = pred._mul(e, f)
        exact = (Fraction(xs[i]) - Fraction(xs[i + 1])) * (
            Fraction(xs[i + 2]) - Fraction(xs[i + 3])
        )
        assert sum((Fraction(float(c)) for c in h), Fraction(0)) == exact
        assert np.all(np.abs(h[:-1]) <= np.abs(h[1:]))  # increasing magnitude


# ---------------------------------------------------------------------------------------------
# Algebraic properties and contract
# ---------------------------------------------------------------------------------------------
def test_sign_symmetries(t13_3d: tuple, t13_2d: tuple) -> None:  # type: ignore[type-arg]
    (a, b, c), _, want2 = t13_2d
    assert (pred.orient2d(b, c, a) == want2).all()  # cyclic
    assert (pred.orient2d(b, a, c) == -want2).all()  # swap
    (a3, b3, c3, d3), _, want3 = t13_3d
    assert (pred.orient3d(b3, a3, c3, d3) == -want3).all()
    assert (pred.orient3d(a3, b3, d3, c3) == -want3).all()
    assert (pred.orient3d(a3, c3, d3, b3) == want3).all()  # even permutation


def test_convention_matches_specification() -> None:
    o = [0.0, 0.0, 0.0]
    assert pred.orient3d(o, [1, 0, 0], [0, 1, 0], [0, 0, 1]).tolist() == [1]  # d along (b-a)x(c-a)
    assert pred.orient2d([0, 0], [1, 0], [0, 1]).tolist() == [1]  # counter-clockwise


def test_contract_errors() -> None:
    with pytest.raises(KernelContractError):
        pred.orient2d([0, math.nan], [1, 0], [0, 1])
    with pytest.raises(KernelContractError):
        pred.orient3d([0, 0, math.inf], [1, 0, 0], [0, 1, 0], [0, 0, 1])
    with pytest.raises(KernelContractError):
        pred.orient2d(np.zeros((2, 2)), np.zeros((3, 2)), np.zeros((2, 2)))
    with pytest.raises(KernelContractError):
        pred.orient3d(np.zeros((1, 2)), np.zeros((1, 3)), np.zeros((1, 3)), np.zeros((1, 3)))


def test_numba_callers_get_out_of_domain_marker() -> None:
    assert pred.orient2d_nb(1e-300, 0.0, 0.0, 1e-300, 1e-300, 1e-300) == pred.OUT_OF_DOMAIN
    assert pred.orient2d_nb(0.0, 0.0, 1.0, 0.0, 0.0, 1.0) == 1


def test_kernel_jit_options_are_fixed() -> None:
    assert KERNEL_JIT_OPTIONS["fastmath"] is False
    assert KERNEL_JIT_OPTIONS["parallel"] is False
    assert KERNEL_JIT_OPTIONS["error_model"] == "numpy"
    assert pred._orient3d_exact.targetoptions["fastmath"] is False  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------------------------
# Determinism: 100 runs in-process + fresh processes (host and generic CPU target)
# ---------------------------------------------------------------------------------------------
def _digest(fn: Callable[..., NDArray[np.int8]], pts: list[Pts]) -> str:
    return hashlib.sha256(fn(*pts).tobytes()).hexdigest()


@pytest.mark.determinism
def test_100_runs_identical(t13_2d: tuple, t13_3d: tuple) -> None:  # type: ignore[type-arg]
    """100 in-process runs on every 10th T13 case (all categories; most take the exact path).

    The full T13 set is recomputed in fresh processes below and compared with the oracle.
    """
    p2 = [p[::10] for p in t13_2d[0]]
    p3 = [p[::10] for p in t13_3d[0]]
    d2 = {_digest(pred.orient2d, p2) for _ in range(100)}
    d3 = {_digest(pred.orient3d, p3) for _ in range(100)}
    assert len(d2) == 1 and len(d3) == 1
    assert d2 == {hashlib.sha256(t13_2d[2][::10].tobytes()).hexdigest()}
    assert d3 == {hashlib.sha256(t13_3d[2][::10].tobytes()).hexdigest()}


_CHILD = """
import hashlib, sys
sys.path.insert(0, sys.argv[1])
import test_shared_predicates as T
from jude_kernel.shared import predicates as pred
p2, _ = T.t13_orient2d()
p3, _ = T.t13_orient3d()
print(hashlib.sha256(pred.orient2d(*p2).tobytes() + pred.orient3d(*p3).tobytes()).hexdigest())
"""


@pytest.mark.determinism
@pytest.mark.parametrize("cpu", ["host", "generic"])
def test_fresh_processes_identical(cpu: str, t13_2d: tuple, t13_3d: tuple) -> None:  # type: ignore[type-arg]
    want = hashlib.sha256(t13_2d[2].tobytes() + t13_3d[2].tobytes()).hexdigest()
    env = dict(os.environ)
    env.pop("NUMBA_CPU_NAME", None)
    if cpu == "generic":
        env["NUMBA_CPU_NAME"] = "generic"
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(2):
        proc = subprocess.run(  # noqa: S603 — fixed argv, our own interpreter
            [sys.executable, "-c", _CHILD, here],
            env=env, capture_output=True, text=True, check=True, timeout=600,
        )  # fmt: skip
        assert proc.stdout.strip() == want
