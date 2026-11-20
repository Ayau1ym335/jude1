"""XC-EXP-06 representative numba kernels (stand-ins for the BM-01 kernels of ALG-11/33/34/40).

The real kernels arrive with their TT-K tasks (M1). These exercise the same kinds of floating
point work where non-determinism usually appears: long reductions, products that a compiler
could contract into FMA, branches with divisions, libm transcendental functions, neighbour
accumulation, sort-based spatial ordering and the ALG-63 monotone Hermite profile.

All kernels: fastmath off, parallel off (TD-19). ``cache=True`` lets the experiment measure the
warm (cached) start; the cache directory comes from NUMBA_CACHE_DIR.
"""

from numba import njit
import numpy as np

OPTS = {"fastmath": False, "parallel": False, "cache": True, "error_model": "numpy"}


@njit(**OPTS)
def ordered_sum(x):
    s = 0.0
    for v in x:
        s += v
    out = np.empty(1)
    out[0] = s
    return out


@njit(**OPTS)
def orient3d_float(a, b, c, d):
    """Float orient3d determinant (the non-exact filter of ALG-11); FMA-contraction sensitive."""
    n = a.shape[0]
    out = np.empty(n)
    for i in range(n):
        adx = a[i, 0] - d[i, 0]
        ady = a[i, 1] - d[i, 1]
        adz = a[i, 2] - d[i, 2]
        bdx = b[i, 0] - d[i, 0]
        bdy = b[i, 1] - d[i, 1]
        bdz = b[i, 2] - d[i, 2]
        cdx = c[i, 0] - d[i, 0]
        cdy = c[i, 1] - d[i, 1]
        cdz = c[i, 2] - d[i, 2]
        out[i] = (
            adx * (bdy * cdz - bdz * cdy)
            + bdx * (cdy * adz - cdz * ady)
            + cdx * (ady * bdz - adz * bdy)
        )
    return out


@njit(**OPTS)
def closest_point_triangle(p, a, b, c):
    """Closest point on triangle (Ericson 5.1.5), the inner test of ALG-33/40."""
    n = p.shape[0]
    out = np.empty((n, 3))
    for i in range(n):
        ab = b[i] - a[i]
        ac = c[i] - a[i]
        ap = p[i] - a[i]
        d1 = ab[0] * ap[0] + ab[1] * ap[1] + ab[2] * ap[2]
        d2 = ac[0] * ap[0] + ac[1] * ap[1] + ac[2] * ap[2]
        if d1 <= 0.0 and d2 <= 0.0:
            out[i] = a[i]
            continue
        bp = p[i] - b[i]
        d3 = ab[0] * bp[0] + ab[1] * bp[1] + ab[2] * bp[2]
        d4 = ac[0] * bp[0] + ac[1] * bp[1] + ac[2] * bp[2]
        if d3 >= 0.0 and d4 <= d3:
            out[i] = b[i]
            continue
        vc = d1 * d4 - d3 * d2
        if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
            v = d1 / (d1 - d3)
            out[i] = a[i] + v * ab
            continue
        cp = p[i] - c[i]
        d5 = ab[0] * cp[0] + ab[1] * cp[1] + ab[2] * cp[2]
        d6 = ac[0] * cp[0] + ac[1] * cp[1] + ac[2] * cp[2]
        if d6 >= 0.0 and d5 <= d6:
            out[i] = c[i]
            continue
        vb = d5 * d2 - d1 * d6
        if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
            w = d2 / (d2 - d6)
            out[i] = a[i] + w * ac
            continue
        va = d3 * d6 - d5 * d4
        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
            w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
            out[i] = b[i] + w * (c[i] - b[i])
            continue
        denom = 1.0 / (va + vb + vc)
        v = vb * denom
        w = vc * denom
        out[i] = a[i] + ab * v + ac * w
    return out


@njit(**OPTS)
def transcendental(x):
    """libm functions used by frames, profiles and smoothing (sin, cos, exp, log1p, atan2, sqrt)."""
    n = x.shape[0]
    out = np.empty((n, 6))
    for i in range(n):
        v = x[i]
        out[i, 0] = np.sin(v)
        out[i, 1] = np.cos(v)
        out[i, 2] = np.exp(-v * v)
        out[i, 3] = np.log1p(abs(v))
        out[i, 4] = np.arctan2(v, 1.0 + v * v)
        out[i, 5] = np.sqrt(1.0 + v * v)
    return out


@njit(**OPTS)
def laplacian_smooth(v, nbr_ptr, nbr_idx, lam, iters):
    """Jacobi Laplacian smoothing over a CSR neighbour list (accumulation in fixed order)."""
    cur = v.copy()
    nxt = np.empty_like(v)
    for _ in range(iters):
        for i in range(cur.shape[0]):
            sx = 0.0
            sy = 0.0
            sz = 0.0
            k0 = nbr_ptr[i]
            k1 = nbr_ptr[i + 1]
            for k in range(k0, k1):
                j = nbr_idx[k]
                sx += cur[j, 0]
                sy += cur[j, 1]
                sz += cur[j, 2]
            m = k1 - k0
            if m == 0:
                nxt[i] = cur[i]
            else:
                nxt[i, 0] = cur[i, 0] + lam * (sx / m - cur[i, 0])
                nxt[i, 1] = cur[i, 1] + lam * (sy / m - cur[i, 1])
                nxt[i, 2] = cur[i, 2] + lam * (sz / m - cur[i, 2])
        cur, nxt = nxt, cur
    return cur


@njit(**OPTS)
def median_split_order(points, leaf):
    """Top-down median-split ordering (the build step of a BVH): stable sort on the widest axis."""
    n = points.shape[0]
    order = np.arange(n)
    stack_lo = np.empty(2 * n + 2, dtype=np.int64)
    stack_hi = np.empty(2 * n + 2, dtype=np.int64)
    top = 0
    stack_lo[0] = 0
    stack_hi[0] = n
    top = 1
    while top > 0:
        top -= 1
        lo = stack_lo[top]
        hi = stack_hi[top]
        if hi - lo <= leaf:
            continue
        idx = order[lo:hi]
        best_axis = 0
        best_extent = -1.0
        for axis in range(3):
            col = points[idx, axis]
            extent = col.max() - col.min()
            if extent > best_extent:
                best_extent = extent
                best_axis = axis
        keys = points[idx, best_axis]
        perm = np.argsort(keys, kind="mergesort")
        order[lo:hi] = idx[perm]
        mid = lo + (hi - lo) // 2
        stack_lo[top] = lo
        stack_hi[top] = mid
        top += 1
        stack_lo[top] = mid
        stack_hi[top] = hi
        top += 1
    return order


@njit(**OPTS)
def hermite_profile(u, xs, ys):
    """ALG-63 custom profile: monotone cubic Hermite (Fritsch-Carlson) evaluated at u."""
    m = xs.shape[0]
    delta = np.empty(m - 1)
    for k in range(m - 1):
        delta[k] = (ys[k + 1] - ys[k]) / (xs[k + 1] - xs[k])
    slope = np.empty(m)
    slope[0] = delta[0]
    slope[m - 1] = delta[m - 2]
    for k in range(1, m - 1):
        if delta[k - 1] * delta[k] <= 0.0:
            slope[k] = 0.0
        else:
            slope[k] = 0.5 * (delta[k - 1] + delta[k])
    for k in range(m - 1):
        if delta[k] == 0.0:
            slope[k] = 0.0
            slope[k + 1] = 0.0
        else:
            a = slope[k] / delta[k]
            b = slope[k + 1] / delta[k]
            s = a * a + b * b
            if s > 9.0:
                t = 3.0 / np.sqrt(s)
                slope[k] = t * a * delta[k]
                slope[k + 1] = t * b * delta[k]
    out = np.empty(u.shape[0])
    for i in range(u.shape[0]):
        x = u[i]
        k = 0
        while k < m - 2 and x > xs[k + 1]:
            k += 1
        h = xs[k + 1] - xs[k]
        t = (x - xs[k]) / h
        t2 = t * t
        t3 = t2 * t
        out[i] = (
            (2 * t3 - 3 * t2 + 1) * ys[k]
            + (t3 - 2 * t2 + t) * h * slope[k]
            + (-2 * t3 + 3 * t2) * ys[k + 1]
            + (t3 - t2) * h * slope[k + 1]
        )
    return out
