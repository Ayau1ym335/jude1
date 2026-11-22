"""Exact rational oracles for T14 / T15 (XC-SHR-03). ``fractions.Fraction`` only; no kernel code.

Doubles convert to Fractions exactly, so every answer here is the true answer for the stored
inputs, not an approximation.
"""

from collections import defaultdict
from collections.abc import Sequence
from fractions import Fraction

Q2 = tuple[Fraction, Fraction]
Q3 = tuple[Fraction, Fraction, Fraction]


def q(x: float | int) -> Fraction:
    return Fraction(x)


def q2(p: Sequence[float]) -> Q2:
    return (q(p[0]), q(p[1]))


def q3(p: Sequence[float]) -> Q3:
    return (q(p[0]), q(p[1]), q(p[2]))


def sign(x: Fraction) -> int:
    return (x > 0) - (x < 0)


def text(x: Fraction) -> str:
    return f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator)


# --------------------------------------------------------------------------------- 2D ---
def orient2(a: Q2, b: Q2, c: Q2) -> int:
    return sign((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))


def _on_segment(a: Q2, b: Q2, p: Q2) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def segments_intersect(a: Q2, b: Q2, c: Q2, d: Q2) -> bool:
    """Closed segments ab and cd share at least one point (touching and overlap included)."""
    o1, o2, o3, o4 = orient2(a, b, c), orient2(a, b, d), orient2(c, d, a), orient2(c, d, b)
    if o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4):
        return True
    return (
        (o1 == 0 and _on_segment(a, b, c))
        or (o2 == 0 and _on_segment(a, b, d))
        or (o3 == 0 and _on_segment(c, d, a))
        or (o4 == 0 and _on_segment(c, d, b))
        or (o1 != o2 and o3 != o4)
    )


def polygon_report(points: Sequence[Sequence[float]]) -> dict[str, object]:
    """Exact simplicity, signed area and degeneracies of a closed polygon (k >= 3)."""
    p = [q2(x) for x in points]
    k = len(p)
    seg = [(p[i], p[(i + 1) % k]) for i in range(k)]
    duplicates = sum(1 for i in range(k) if p[i] == p[(i + 1) % k])
    collinear = sum(1 for i in range(k) if orient2(p[i - 1], p[i], p[(i + 1) % k]) == 0)
    simple = duplicates == 0
    for i in range(k):
        if not simple:
            break
        for j in range(i + 1, k):
            adjacent = j == i + 1 or (i == 0 and j == k - 1)
            a, b = seg[i]
            c, d = seg[j]
            if adjacent:
                shared = b if j == i + 1 else a
                other = d if j == i + 1 else c
                own = a if j == i + 1 else b
                # adjacent edges may only share their common vertex: fold-back means overlap
                if (
                    orient2(own, shared, other) == 0
                    and _on_segment(own, shared, other)
                    and other != shared
                ):
                    simple = False
                    break
                if (
                    orient2(shared, other, own) == 0
                    and _on_segment(shared, other, own)
                    and own != shared
                ):
                    simple = False
                    break
                continue
            if segments_intersect(a, b, c, d):
                simple = False
                break
    area2 = sum(
        (p[i][0] * p[(i + 1) % k][1] - p[(i + 1) % k][0] * p[i][1] for i in range(k)), Fraction(0)
    )
    return {
        "n_vertices": k,
        "simple": simple,
        "signed_area": text(area2 / 2),
        "area_float": float(abs(area2) / 2),
        "orientation": {1: "ccw", -1: "cw", 0: "degenerate"}[sign(area2)],
        "duplicate_consecutive_points": duplicates,
        "collinear_vertices": collinear,
    }


# --------------------------------------------------------------------------------- 3D ---
def _sub(a: Q3, b: Q3) -> Q3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Q3, b: Q3) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add_scaled(a: Q3, s: Fraction, d: Q3) -> Q3:
    return (a[0] + s * d[0], a[1] + s * d[1], a[2] + s * d[2])


def closest_point_triangle(p: Q3, a: Q3, b: Q3, c: Q3) -> Q3:
    """Ericson 5.1.5 in exact arithmetic."""
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(p, a)
    d1, d2 = _dot(ab, ap), _dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = _sub(p, b)
    d3, d4 = _dot(ab, bp), _dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return _add_scaled(a, d1 / (d1 - d3), ab)
    cp = _sub(p, c)
    d5, d6 = _dot(ab, cp), _dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return _add_scaled(a, d2 / (d2 - d6), ac)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        return _add_scaled(b, (d4 - d3) / ((d4 - d3) + (d5 - d6)), _sub(c, b))
    denom = va + vb + vc
    v, w = vb / denom, vc / denom
    return (
        a[0] + ab[0] * v + ac[0] * w,
        a[1] + ab[1] * v + ac[1] * w,
        a[2] + ab[2] * v + ac[2] * w,
    )


def closest_faces(
    p: Sequence[float], verts: Sequence[Sequence[float]], faces: Sequence[Sequence[int]]
) -> dict[str, object]:
    """Exact squared distance from p to the mesh and every face that attains it (the tie set)."""
    pq = q3(p)
    vq = [q3(v) for v in verts]
    d2 = []
    for f in faces:
        cpt = closest_point_triangle(pq, vq[f[0]], vq[f[1]], vq[f[2]])
        diff = _sub(pq, cpt)
        d2.append(_dot(diff, diff))
    best = min(d2)
    tied = [i for i, d in enumerate(d2) if d == best]
    return {"distance_squared": text(best), "distance": float(best) ** 0.5, "tied_faces": tied,
            "face_by_tie_rule": min(tied)}  # fmt: skip


def plane_section(
    verts: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    point: Sequence[float],
    normal: Sequence[float],
) -> dict[str, object]:
    """ALG-23 in exact arithmetic: d = n.(v - p); d = 0 counts as positive; one point per crossed
    edge at t = d_a / (d_a - d_b); one segment per crossed face; segments chained by edge key."""
    vq = [q3(v) for v in verts]
    pq, nq = q3(point), q3(normal)
    d = [_dot(nq, _sub(v, pq)) for v in vq]
    pos = [x >= 0 for x in d]

    def edge_point(a: int, b: int) -> Q3:
        t = d[a] / (d[a] - d[b])
        return _add_scaled(vq[a], t, _sub(vq[b], vq[a]))

    links: dict[tuple[int, int], list[int]] = defaultdict(list)
    segs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for f in faces:
        crossed = [
            (min(a, b), max(a, b))
            for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0]))
            if pos[a] != pos[b]
        ]
        if crossed:
            segs.append((crossed[0], crossed[1]))
            for e in crossed:
                links[e].append(len(segs) - 1)
    used = [False] * len(segs)
    contours = []
    for s0 in range(len(segs)):
        if used[s0]:
            continue
        used[s0] = True
        start, cur = segs[s0]
        chain = [start, cur]
        closed = False
        while True:
            nxt = [s for s in links[cur] if not used[s]]
            if not nxt:
                closed = cur == start
                break
            used[nxt[0]] = True
            a, b = segs[nxt[0]]
            cur = b if a == cur else a
            if cur == start:
                closed = True
                break
            chain.append(cur)
        pts = [edge_point(a, b) if pos[a] != pos[b] else vq[a] for a, b in chain]
        length = sum(
            (sum(float(c) ** 2 for c in _sub(pts[i], pts[(i + 1) % len(pts)])) ** 0.5
             for i in range(len(pts) if closed else len(pts) - 1)),
            0.0,
        )  # fmt: skip
        contours.append({"closed": closed, "n_points": len(pts), "length": round(length, 9),
                         "points": [[text(c) for c in p] for p in pts]})  # fmt: skip
    return {
        "vertices_on_plane": sum(1 for x in d if x == 0),
        "crossed_edges": len(links),
        "n_contours": len(contours),
        "contours": contours,
    }
