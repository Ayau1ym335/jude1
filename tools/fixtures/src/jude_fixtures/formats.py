"""Test-only mesh file writers for the format set T4 and the defect files of T3.

Independent of the production importers (FN-KIO-01..05). Every float is written with Python's
shortest round-trip repr, so text formats hold exactly the same doubles as the binary ones.
"""

import struct

import numpy as np
from numpy.typing import NDArray

Vec = NDArray[np.float64]
Faces = NDArray[np.int32]


def _num(x: float) -> str:
    return repr(float(x))


def _normals(v: Vec, f: Faces) -> Vec:
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    length = np.sqrt(n[:, 0] * n[:, 0] + n[:, 1] * n[:, 1] + n[:, 2] * n[:, 2])
    out = np.zeros_like(n)
    ok = length > 0
    out[ok] = n[ok] / length[ok, None]
    return out


def ascii_stl(v: Vec, f: Faces, name: str = "jude_fixture") -> bytes:
    lines = [f"solid {name}"]
    for (i, j, k), n in zip(f.tolist(), _normals(v, f).tolist(), strict=True):
        lines.append("  facet normal " + " ".join(_num(x) for x in n))
        lines.append("    outer loop")
        for idx in (i, j, k):
            lines.append("      vertex " + " ".join(_num(x) for x in v[idx]))
        lines += ["    endloop", "  endfacet"]
    lines.append(f"endsolid {name}")
    return ("\n".join(lines) + "\n").encode("ascii")


def obj(
    v: Vec,
    faces: list[list[int]],
    *,
    negative: bool = False,
    texture: bool = False,
    comment: str = "jude fixture",
) -> bytes:
    """Wavefront OBJ; ``faces`` are 0-based polygons (triangles or quads)."""
    lines = [f"# {comment}", "o fixture"]
    lines += ["v " + " ".join(_num(x) for x in p) for p in v.tolist()]
    if texture:
        lines += ["vt 0.0 0.0", "vt 1.0 0.0", "vt 0.0 1.0", "vn 0.0 0.0 1.0"]
    n = v.shape[0]
    for poly in faces:
        refs = []
        for k, idx in enumerate(poly):
            ref = str(idx - n) if negative else str(idx + 1)
            if texture:
                ref += f"/{(k % 3) + 1}/1"
            refs.append(ref)
        lines.append("f " + " ".join(refs))
    return ("\n".join(lines) + "\n").encode("ascii")


def ply(v: Vec, f: Faces, fmt: str) -> bytes:
    """PLY with float64 vertices and int32 face indices; fmt: ascii | binary_little_endian |
    binary_big_endian."""
    header = (
        f"ply\nformat {fmt} 1.0\ncomment jude fixture\n"
        f"element vertex {v.shape[0]}\nproperty double x\nproperty double y\nproperty double z\n"
        f"element face {f.shape[0]}\nproperty list uchar int vertex_indices\nend_header\n"
    ).encode("ascii")
    if fmt == "ascii":
        body = "".join(" ".join(_num(x) for x in p) + "\n" for p in v.tolist())
        body += "".join("3 " + " ".join(str(i) for i in t) + "\n" for t in f.tolist())
        return header + body.encode("ascii")
    order = "<" if fmt == "binary_little_endian" else ">"
    out = bytearray(header)
    for p in v.tolist():
        out += struct.pack(order + "3d", *p)
    for t in f.tolist():
        out += struct.pack(order + "B3i", 3, *t)
    return bytes(out)
