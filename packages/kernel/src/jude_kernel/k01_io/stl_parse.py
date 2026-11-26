"""FN-KIO-02 Parse STL, binary and ASCII (ALG-02; INT-01, FR-010, FR-015, SEC-07).

Reads an STL file into its triangle soup: ``float64[3n, 3]``, three corners per facet, in file
order. FN-KIO-05 then merges exactly equal vertices into an indexed mesh. Stored facet normals
are never used, because they are often wrong (05 §1.5). Winding defines orientation.

- **Binary:**
  - 80-byte header, uint32 LE count n, then n records of 50 bytes (normal float32[3],
    vertices float32[3][3], uint16 attribute), read with a fixed little-endian structured
    dtype;
  - the size must be exactly 84 + 50 n, else FILE_UNREADABLE (truncated or padded);
  - the header may start with "solid" (FN-KIO-01 decides the format, not the header);
  - the attribute bytes are ignored;
  - float32 to float64 is exact.
- **ASCII:** a line tokenizer over the grammar

      solid [name] { facet normal x y z  outer loop  (vertex x y z){3}  endloop  endfacet }
      endsolid [name]

  - one or more solids; any whitespace; blank lines anywhere;
  - numbers must be plain decimal or scientific notation, parsed to float64
    (≤ 0.5 ulp, Python float). A locale comma, an underscore, a hex float or any other form
    is FILE_UNREADABLE, and the detail names the line number.
- **Refusals** (``StlParse.reason_code``):
  - n = 0 → FILE_EMPTY;
  - n > ``max_faces`` → FACE_LIMIT. For binary input this is checked from the header,
    before anything is allocated;
  - a non-finite coordinate → NON_FINITE_COORDINATES (ALG-02 step 4);
  - anything malformed → FILE_UNREADABLE.

``max_faces`` is the deployment's face cap (OD-03 / OQ-FS-29) and has no default (SEC-07). The
parser runs in the worker sandbox (XC-FND-09); its own checks keep a hostile file from
allocating memory in the first place.
"""

from dataclasses import dataclass
import math
import re
from typing import Final

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import KernelContractError
from jude_kernel.k01_io.detect import FileFormat

HEADER: Final = 80
RECORD: Final = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attr", "<u2")])
FILE_UNREADABLE: Final = "FILE_UNREADABLE"
FILE_EMPTY: Final = "FILE_EMPTY"
FACE_LIMIT: Final = "FACE_LIMIT"
NON_FINITE: Final = "NON_FINITE_COORDINATES"
_NUMBER = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_NON_FINITE_WORDS: Final = {b"nan", b"inf", b"infinity"}


@dataclass(frozen=True)
class StlParse:
    """``soup`` (3n x 3 float64, read-only) on success, else ``reason_code`` and ``detail``."""

    soup: NDArray[np.float64] | None
    reason_code: str | None = None
    detail: str = ""

    @property
    def n_facets(self) -> int:
        return 0 if self.soup is None else self.soup.shape[0] // 3


def _refuse(code: str, detail: str) -> StlParse:
    return StlParse(None, code, detail)


def _ok(soup: NDArray[np.float64]) -> StlParse:
    if not np.all(np.isfinite(soup)):
        row = int(np.argwhere(~np.isfinite(soup))[0][0])
        return _refuse(NON_FINITE, f"facet {row // 3}: non-finite coordinate")
    soup.setflags(write=False)
    return StlParse(soup)


def parse_binary(data: bytes, *, max_faces: int) -> StlParse:
    if len(data) < HEADER + 4:
        return _refuse(FILE_UNREADABLE, f"{len(data)} bytes: shorter than the 84-byte header")
    n = int.from_bytes(data[HEADER : HEADER + 4], "little")
    if n == 0:
        return _refuse(FILE_EMPTY, "header declares 0 facets")
    if n > max_faces:  # before any allocation: a face bomb is refused from its header
        return _refuse(FACE_LIMIT, f"{n} facets declared, cap {max_faces}")
    expected = HEADER + 4 + RECORD.itemsize * n
    if len(data) != expected:
        return _refuse(FILE_UNREADABLE, f"{n} facets need {expected} bytes, file has {len(data)}")
    records = np.frombuffer(data, dtype=RECORD, count=n, offset=HEADER + 4)
    return _ok(records["vertices"].reshape(3 * n, 3).astype(np.float64))


def _number(token: bytes, line: int) -> float | StlParse:
    if token.lstrip(b"+-").lower() in _NON_FINITE_WORDS:
        return _refuse(NON_FINITE, f"line {line}: non-finite coordinate {token[:20]!r}")
    if not _NUMBER.fullmatch(token):
        return _refuse(FILE_UNREADABLE, f"line {line}: not a number {token[:20]!r}")
    value = float(token)
    if not math.isfinite(value):  # e.g. 1e999 overflows to inf
        return _refuse(NON_FINITE, f"line {line}: coordinate out of range {token[:20]!r}")
    return value


def parse_ascii(data: bytes, *, max_faces: int) -> StlParse:
    coords: list[float] = []
    state = "outside"  # outside | solid | facet | loop | endloop
    n_vertices = n_facets = 0
    line_no = 0
    for raw in data.splitlines():
        line_no += 1
        tokens = raw.split()
        if not tokens:
            continue
        word = tokens[0]
        if state == "outside":
            if word != b"solid":
                return _refuse(FILE_UNREADABLE, f"line {line_no}: expected 'solid'")
            state = "solid"
        elif state == "solid":
            if word == b"endsolid":
                state = "outside"
            elif word == b"facet" and len(tokens) == 5 and tokens[1] == b"normal":
                for t in tokens[2:]:  # the stored normal is never used, but must be a number
                    if isinstance(checked := _number(t, line_no), StlParse):
                        return checked
                if n_facets >= max_faces:
                    return _refuse(FACE_LIMIT, f"line {line_no}: more than {max_faces} facets")
                state = "facet"
            else:
                return _refuse(FILE_UNREADABLE, f"line {line_no}: expected 'facet normal x y z'")
        elif state == "facet":
            if tokens != [b"outer", b"loop"]:
                return _refuse(FILE_UNREADABLE, f"line {line_no}: expected 'outer loop'")
            state, n_vertices = "loop", 0
        elif state == "loop":
            if word == b"vertex" and len(tokens) == 4:
                if n_vertices == 3:
                    return _refuse(FILE_UNREADABLE, f"line {line_no}: more than 3 vertices")
                for t in tokens[1:]:
                    value = _number(t, line_no)
                    if isinstance(value, StlParse):
                        return value
                    coords.append(value)
                n_vertices += 1
            elif tokens == [b"endloop"]:
                if n_vertices != 3:
                    return _refuse(FILE_UNREADABLE, f"line {line_no}: {n_vertices} vertices")
                state = "endloop"
            else:
                return _refuse(FILE_UNREADABLE, f"line {line_no}: expected 'vertex x y z'")
        elif state == "endloop":
            if tokens != [b"endfacet"]:
                return _refuse(FILE_UNREADABLE, f"line {line_no}: expected 'endfacet'")
            n_facets += 1
            state = "solid"
    if state != "outside":
        return _refuse(FILE_UNREADABLE, f"line {line_no}: file ends inside a {state} block")
    if n_facets == 0:
        return _refuse(FILE_EMPTY, "no facets")
    return _ok(np.array(coords, dtype=np.float64).reshape(3 * n_facets, 3))


def parse_stl(data: bytes, fmt: FileFormat, *, max_faces: int) -> StlParse:
    """FN-KIO-02: triangle soup of an STL file whose format FN-KIO-01 detected."""
    if isinstance(max_faces, bool) or not isinstance(max_faces, int) or max_faces < 1:
        raise KernelContractError("max_faces: the configured face cap is required (no default)")
    if fmt is FileFormat.STL_BINARY:
        return parse_binary(data, max_faces=max_faces)
    if fmt is FileFormat.STL_ASCII:
        return parse_ascii(data, max_faces=max_faces)
    raise KernelContractError(f"parse_stl: not an STL format: {fmt}")
