"""T13: adversarial inputs for the exact predicates (XC-SHR-03; TD-04, GTS T13).

Generated from a fixed seed with the stdlib ``random`` module; the expected signs come from an
independent rational oracle (``fractions.Fraction``) that shares no code with the kernel.
Moved here from the XC-SHR-01 tests so the set can be frozen (``jude-fixtures``).
"""

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np
from numpy.typing import NDArray

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


# ---------------------------------------------------------------------------------------------
# Frozen set (XC-SHR-03): inputs pinned by hash, expected signs committed
# ---------------------------------------------------------------------------------------------
KEYS = {"orient2d": "abc", "orient3d": "abcd"}
FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures"


def generate(predicate: str) -> tuple[list[Pts], list[str]]:
    return t13_orient2d() if predicate == "orient2d" else t13_orient3d()


def inputs_bytes(predicate: str, pts: list[Pts]) -> bytes:
    from jude_kernel.core.jarr import encode

    return encode(
        dict(zip(KEYS[predicate], pts, strict=True)), {"schema": "t13/1", "predicate": predicate}
    )


def load(predicate: str, root: Path = FIXTURES) -> tuple[list[Pts], NDArray[np.int8], list[str]]:
    """Regenerate the inputs, prove they are the frozen ones, and return the frozen signs."""
    from jude_kernel.core.jarr import decode

    entry = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["fixtures"][
        f"T13/{predicate}"
    ]
    pts, cats = generate(predicate)
    digest = hashlib.sha256(inputs_bytes(predicate, pts)).hexdigest()
    if digest != entry["files"]["inputs.jarr"]["sha256"]:
        raise RuntimeError(f"T13/{predicate}: generated inputs differ from the frozen hash")
    arrays, _ = decode((root / entry["files"]["expected.jarr"]["path"]).read_bytes())
    want = arrays["sign_plus_1"].astype(np.int8) - 1
    return pts, want, cats
