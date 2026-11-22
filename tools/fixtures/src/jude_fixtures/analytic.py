"""Analytic ground truth for the phantoms (smooth surfaces, not the meshes).

Measurement formulas follow the function specifications exactly: CI = 100*W/L with L, W the
extents along A-P (x) and M-L (y) (FN-KMS-03); diagonals at +-theta through the centre,
CVA = |D1 - D2|, CVAI_short = 100*CVA/min, CVAI_long = 100*CVA/max (FN-KMS-04, IDR-02); HC =
perimeter of the closed section (FN-KMS-05). The angles 30 and 40 degrees are the shipped
presets (DEC-027). Values are of the smooth surface; the mesh differs by chord error, judged
with DEC-025 tolerances by the verification tasks.

All values are rounded to 1e-9 (mm or index units) so libm last-bit differences cannot change
the JSON bytes.
"""

import math
from typing import Any

from jude_fixtures.geometry import cos_sin

PRESET_ANGLES_DEG = (30, 40)


def r9(x: float) -> float:
    return round(x, 9)


def agm_complete_e(m: float) -> float:
    """Complete elliptic integral of the second kind E(m), m = k**2, by the AGM (sqrt only)."""
    a, g = 1.0, math.sqrt(1.0 - m)
    c2_sum, power = 0.5 * m, 0.5  # sum of 2**(n-1) * c_n**2, starting with n = 0
    for _ in range(64):  # quadratic convergence: < 10 rounds in practice
        if abs(a - g) <= 1e-17 * a:
            break
        c = (a - g) / 2.0
        a, g = (a + g) / 2.0, math.sqrt(a * g)
        power *= 2.0
        c2_sum += power * c * c
    k = math.pi / (2.0 * a)
    return k * (1.0 - c2_sum)


def ellipse_perimeter(p: float, q: float) -> float:
    a, b = max(p, q), min(p, q)
    if a == 0.0:
        return 0.0
    return 4.0 * a * agm_complete_e(1.0 - (b / a) ** 2)


def ellipse_radius_at(a: float, b: float, cos_a: float, sin_a: float) -> float:
    """Distance from the centre to the ellipse (semi-axes a on local x, b on local y)."""
    return a * b / math.sqrt((b * cos_a) ** 2 + (a * sin_a) ** 2)


def section_values(a: float, b: float, rot: tuple[float, float]) -> dict[str, Any]:
    """Measurement truth of an ellipse with semi-axes (a, b) rotated by ``rot`` (cos, sin)."""
    cs, sn = rot
    half_l = math.sqrt((a * cs) ** 2 + (b * sn) ** 2)  # half extent along x (A-P)
    half_w = math.sqrt((a * sn) ** 2 + (b * cs) ** 2)  # half extent along y (M-L)
    out: dict[str, Any] = {
        "L": r9(2 * half_l),
        "W": r9(2 * half_w),
        "CI": r9(100.0 * half_w / half_l),
        "HC": r9(ellipse_perimeter(a, b)),
        "diagonals": {},
    }
    for deg in PRESET_ANGLES_DEG:
        ct, st = cos_sin(math.radians(deg))
        lengths = []
        for sign in (1.0, -1.0):  # D1 at +theta, D2 at -theta from +x
            # direction angle relative to the ellipse's own axes: theta - phi
            ca = ct * cs + sign * st * sn
            sa = sign * st * cs - ct * sn
            lengths.append(2.0 * ellipse_radius_at(a, b, ca, sa))
        d1, d2 = lengths
        cva = abs(d1 - d2)
        out["diagonals"][str(deg)] = {
            "D1": r9(d1),
            "D2": r9(d2),
            "CVA": r9(cva),
            "CVAI_short": r9(100.0 * cva / min(d1, d2)),
            "CVAI_long": r9(100.0 * cva / max(d1, d2)),
        }
    return out


def ellipsoid_sections(
    a: float, b: float, c: float, rot: tuple[float, float], heights: tuple[float, ...]
) -> list[dict[str, Any]]:
    """Horizontal sections z = h of the ellipsoid (centre at the origin, centre rule irrelevant)."""
    out = []
    for h in heights:
        s = math.sqrt(1.0 - (h / c) ** 2)
        out.append(
            {
                "plane": {"point": [0.0, 0.0, h], "normal": [0.0, 0.0, 1.0]},
                "semi_axes": [r9(a * s), r9(b * s)],
                **section_values(a * s, b * s, rot),
            }
        )
    return out


def sphere_truth(radius: float, level: int) -> dict[str, Any]:
    return {
        "surface": "sphere",
        "radius": radius,
        "area": r9(4.0 * math.pi * radius**2),
        "volume": r9(4.0 / 3.0 * math.pi * radius**3),
        "mesh": {
            "n_vertices": 10 * 4**level + 2,
            "n_faces": 20 * 4**level,
            "euler": 2,
            "closed": True,
            "components": 1,
        },
        "sections": [
            {
                "plane": {"point": [0.0, 0.0, 0.0], "normal": [0.0, 0.0, 1.0]},
                **section_values(radius, radius, (1.0, 0.0)),
            }
        ],
    }
