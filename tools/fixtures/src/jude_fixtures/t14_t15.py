"""T14 tie fixtures and T15 contour shapes (XC-SHR-03; GTS T14/T15). Exact oracles: ``exact``.

T14 a) closest-point ties on an integer cube: query points equidistant from several faces. The
       tie rule of the shared BVH (XC-SHR-02) is "smallest face_id"; the oracle lists the whole
       tie set and the face that rule must return.
T14 b) planes through vertices and edges of an octahedron and a cube: section contours under
       the symbolic rule of ALG-23 (d = 0 counts as positive).
T15    closed polygons for ALG-25/35: convex, concave star, comb, spiral, near-touching and
       touching necks, bow-tie, collinear and duplicate points. Oracle: exact simplicity,
       signed area, orientation.

Coordinates are integers or dyadic rationals (mm), so they are exact in float64.
"""

import math
from typing import Any

from jude_fixtures import exact
from jude_fixtures.geometry import cos_sin, dyadic

# 40 mm cube, 12 outward triangles in a fixed order (face ids 0..11)
CUBE_V = [
    [0, 0, 0],
    [40, 0, 0],
    [40, 40, 0],
    [0, 40, 0],
    [0, 0, 40],
    [40, 0, 40],
    [40, 40, 40],
    [0, 40, 40],
]
CUBE_F = [
    [0, 2, 1],
    [0, 3, 2],  # z = 0
    [4, 5, 6],
    [4, 6, 7],  # z = 40
    [0, 1, 5],
    [0, 5, 4],  # y = 0
    [1, 2, 6],
    [1, 6, 5],  # x = 40
    [2, 3, 7],
    [2, 7, 6],  # y = 40
    [3, 0, 4],
    [3, 4, 7],  # x = 0
]
OCTA_V = [[40, 0, 0], [-40, 0, 0], [0, 40, 0], [0, -40, 0], [0, 0, 40], [0, 0, -40]]
OCTA_F = [[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4], [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]]

TIE_QUERIES: dict[str, list[float]] = {
    "centre_all_faces": [20, 20, 20],
    "above_top_diagonal": [20, 20, 60],
    "above_top_diagonal_offcentre": [10, 10, 50],
    "edge_region_x40_y40": [60, 60, 20],
    "corner_region_40_40_40": [60, 60, 60],
    "inside_near_two_walls": [2, 2, 20],
    "control_above_top_no_tie": [30, 10, 50],
    "control_outside_x": [55, 13, 7],
}

PLANES: dict[str, tuple[str, list[float], list[float]]] = {
    "octa_z0_through_4_vertices": ("octa", [0, 0, 0], [0, 0, 1]),
    "octa_z40_through_apex": ("octa", [0, 0, 40], [0, 0, 1]),
    "octa_x_eq_y_through_2_vertices": ("octa", [0, 0, 0], [1, -1, 0]),
    "octa_z20_generic": ("octa", [0, 0, 20], [0, 0, 1]),
    "cube_x0_on_face": ("cube", [0, 0, 0], [1, 0, 0]),
    "cube_x40_on_face": ("cube", [40, 0, 0], [1, 0, 0]),
    "cube_z20_generic": ("cube", [0, 0, 20], [0, 0, 1]),
    "cube_diagonal_through_edges": ("cube", [0, 0, 0], [1, -1, 0]),
}


def t14_truth() -> dict[str, Any]:
    ties = {
        name: exact.closest_faces(p, CUBE_V, CUBE_F) | {"query": p}
        for name, p in TIE_QUERIES.items()
    }
    meshes = {"octa": (OCTA_V, OCTA_F), "cube": (CUBE_V, CUBE_F)}
    sections = {}
    for name, (mesh, point, normal) in PLANES.items():
        v, f = meshes[mesh]
        sections[name] = {
            "mesh": mesh,
            "plane": {"point": point, "normal": normal},
            **exact.plane_section(v, f, point, normal),
        }
    return {
        "closest_point_ties": {
            "mesh": "cube_40 (face ids are row numbers of CUBE_F)",
            "tie_rule": "smallest face_id among the faces at the exact minimum distance",
            "queries": ties,
        },
        "plane_sections": {
            "rule": "ALG-23: d = n.(v - p); d = 0 counts as positive; t = d_a / (d_a - d_b)",
            "cases": sections,
        },
    }


def _star(n: int, r_out: float, r_in: float) -> list[list[float]]:
    pts = []
    for i in range(2 * n):
        r = r_out if i % 2 == 0 else r_in
        c, s = cos_sin(math.pi * i / n)
        pts.append([dyadic(r * c), dyadic(r * s)])
    return pts


def _f(points: list[Any]) -> list[list[float]]:
    return [[float(x) for x in pt] for pt in points]


def contours() -> dict[str, list[list[float]]]:
    convex = [
        [dyadic(80 * c), dyadic(80 * s)]
        for c, s in (cos_sin(2 * math.pi * i / 64) for i in range(64))
    ]
    comb = [[0, 0], [130, 0], [130, 40]]
    for i in range(12, 0, -1):  # teeth pointing up, 5 mm wide, 3 mm gaps... read right to left
        x = 10 * i
        comb += [[x, 40], [x, 70], [x - 5, 70], [x - 5, 40]]
    comb += [[0, 40]]
    spiral = [
        [0, 0],
        [100, 0],
        [100, 100],
        [10, 100],
        [10, 20],
        [80, 20],
        [80, 80],
        [30, 80],
        [30, 40],
        [60, 40],
        [60, 60],
        [50, 60],
        [50, 50],
        [40, 50],
        [40, 70],
        [70, 70],
        [70, 30],
        [20, 30],
        [20, 90],
        [90, 90],
        [90, 10],
        [0, 10],
    ]
    gap = 2.0**-20
    neck_near = [
        [0, 0],
        [40, 0],
        [40, 18],
        [60, 18],
        [60, 0],
        [100, 0],
        [100, 40],
        [60, 40],
        [60, 20 + gap],
        [40, 20 + gap],
        [40, 40],
        [0, 40],
    ]
    neck_touch = [
        [0, 0],
        [40, 0],
        [40, 20],
        [60, 20],
        [60, 0],
        [100, 0],
        [100, 40],
        [60, 40],
        [60, 20],
        [40, 20],
        [40, 40],
        [0, 40],
    ]
    return {
        "convex_64": _f(convex),
        "concave_star_10": _f(_star(10, 80.0, 35.0)),
        "comb_12": _f(comb),
        "spiral": _f(spiral),
        "neck_near_touching": _f(neck_near),
        "neck_touching": _f(neck_touch),
        "bowtie": _f([[0, 0], [40, 40], [40, 0], [0, 40]]),
        "collinear_vertices": _f([[0, 0], [20, 0], [40, 0], [40, 40], [0, 40], [0, 20]]),
        "duplicate_point": _f([[0, 0], [40, 0], [40, 0], [40, 40], [0, 40]]),
        "clockwise_square": _f([[0, 0], [0, 40], [40, 40], [40, 0]]),
        "triangle_minimal": _f([[0, 0], [1, 0], [0, 1]]),
    }


def t15_truth(shapes: dict[str, list[list[float]]]) -> dict[str, Any]:
    reports = {}
    for name, pts in shapes.items():
        r = exact.polygon_report(pts)
        k = len(pts)
        per = math.fsum(math.dist(pts[i], pts[(i + 1) % k]) for i in range(k))
        reports[name] = {**r, "perimeter": round(per, 9)}
    return {
        "oracle": "exact rational arithmetic (fractions): simple = no two non-adjacent "
        "edges share a "
        "point, adjacent edges share only their common vertex, no zero-length edge",
        "contours": reports,
    }
