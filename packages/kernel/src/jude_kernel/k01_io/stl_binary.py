"""FN-KIO-06 Write binary STL (ALG-06, TD-21; FR-100, INT-04).

The manufacturing file: little-endian binary STL in millimetres, F_export.

    80-byte ASCII header | uint32 triangle count M | M x (normal f32[3], vertices f32[3][3],
    attribute uint16 = 0)                     -> size = 84 + 50 * M bytes

- Vertices are float64 rounded to the nearest float32 (round-half-even). The error per
  coordinate is at most half a float32 ulp: <= 7.6e-6 mm for |x| <= 128 mm, far below the
  1e-4 mm file-fidelity tolerance (DEC-025).
- The facet normal is normalised (b - a) x (c - a), computed in float64 and then cast to
  float32. A degenerate face (zero cross product) gets the normal (0, 0, 0) (ALG-06).
- The header is caller-supplied text (``stl_header`` builds the FN-KIO-06 form). It must be
  printable ASCII, at most 80 bytes, contain no patient data, and must not start with "solid":
  readers would take the file for ASCII STL. It is padded with spaces.
- Output is a pure function of (V, F, header): the same inputs give the same bytes on every
  host. All arithmetic is element-wise IEEE double (no reductions whose order could vary).

Re-reading and comparing against the approved geometry is FN-KIO-07 / FN-EXP-02 (ALG-06 steps
5-7); this module only writes.
"""

from dataclasses import dataclass
import hashlib
import re
from typing import Final

import numpy as np

from jude_kernel.core.errors import KernelContractError
from jude_kernel.core.mesh import Frame, MeshArrays

HEADER_LEN: Final = 80
RECORD: Final = np.dtype(
    [("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]
)
assert RECORD.itemsize == 50  # noqa: S101 — layout invariant of the format
MAX_TRIANGLES: Final = 2**32 - 1
FLOAT32_MAX: Final = float(np.finfo(np.float32).max)
_TOKEN = re.compile(r"^[!-~]{1,32}$")  # printable ASCII without spaces


@dataclass(frozen=True)
class StlBytes:
    """The written file: bytes, their SHA-256 (hex) and the triangle count."""

    data: bytes
    sha256: str
    n_triangles: int


def stl_header(build: str, design_ref: str, version: int) -> str:
    """FN-KIO-06 header 'JUDE <build> <design ref> v<n> mm F_export'.

    ``design_ref`` is the system case/design identifier (e.g. J-0123ABCD), never a clinic
    reference or a name.
    """
    for name, value in (("build", build), ("design_ref", design_ref)):
        if not _TOKEN.fullmatch(value):
            raise KernelContractError(f"{name} must be 1-32 printable ASCII chars without spaces")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise KernelContractError("version must be an int >= 1")
    return f"JUDE {build} {design_ref} v{version} mm {Frame.F_EXPORT.value}"


def _header_bytes(header: str) -> bytes:
    try:
        raw = header.encode("ascii")
    except UnicodeEncodeError as exc:
        raise KernelContractError("STL header must be ASCII") from exc
    if len(raw) > HEADER_LEN:
        raise KernelContractError(f"STL header longer than {HEADER_LEN} bytes")
    if any(b < 0x20 or b > 0x7E for b in raw):
        raise KernelContractError("STL header must be printable ASCII")
    if raw.lstrip().lower().startswith(b"solid"):
        raise KernelContractError("binary STL header must not start with 'solid'")
    return raw.ljust(HEADER_LEN, b" ")


def _unit_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    ux, uy, uz = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1], b[:, 2] - a[:, 2]
    wx, wy, wz = c[:, 0] - a[:, 0], c[:, 1] - a[:, 1], c[:, 2] - a[:, 2]
    n = np.empty((f.shape[0], 3), dtype=np.float64)
    n[:, 0] = uy * wz - uz * wy
    n[:, 1] = uz * wx - ux * wz
    n[:, 2] = ux * wy - uy * wx
    length = np.sqrt(n[:, 0] * n[:, 0] + n[:, 1] * n[:, 1] + n[:, 2] * n[:, 2])
    nonzero = length > 0.0
    n[nonzero] /= length[nonzero, None]
    n[~nonzero] = 0.0
    return n


def write_binary_stl(mesh: MeshArrays, header: str) -> StlBytes:
    """Serialise ``mesh`` (frame F_export, mm) as little-endian binary STL."""
    if mesh.frame is not Frame.F_EXPORT:
        raise KernelContractError(f"STL export needs frame F_export, got {mesh.frame.value}")
    m = mesh.n_faces
    if m > MAX_TRIANGLES:
        raise KernelContractError("more triangles than binary STL can count")
    head = _header_bytes(header)

    records = np.zeros(m, dtype=RECORD)
    if m:
        if mesh.n_vertices and float(np.abs(mesh.V).max()) > FLOAT32_MAX:
            raise KernelContractError("a coordinate overflows float32")
        v32 = mesh.V.astype(np.float32)  # round-to-nearest-even
        records["vertices"] = v32[mesh.F]
        records["normal"] = _unit_normals(mesh.V, mesh.F).astype(np.float32)
    data = head + np.array([m], dtype="<u4").tobytes() + records.tobytes()
    return StlBytes(data=data, sha256=hashlib.sha256(data).hexdigest(), n_triangles=m)
