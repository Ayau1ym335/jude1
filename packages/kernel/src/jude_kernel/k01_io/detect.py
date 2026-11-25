"""FN-KIO-01 Detect file format by signature (ALG-01; FR-010, FR-015, INT-01..03).

The parser is chosen from the file content, never from the extension (FR-010). Pure function
over a bounded prefix and suffix of the bytes and the file size; the sandboxed reader passes
the whole upload (<= the configured cap S) or just its windows.

Rules, in this order (FS FN-KIO-01; the order matters):

1. ``ply`` + LF/CRLF: PLY. Its ``format`` line decides ascii / binary_little_endian /
   binary_big_endian. A PLY without a known format line is unreadable.
2. ``size >= 84`` and ``size == 84 + 50 * n``, with n = uint32 LE at offset 80: binary STL.
   This rule comes before the ASCII rule because an 80-byte binary header may start with
   ``solid`` (the known STL ambiguity, 05 §1.1). An ASCII file whose size happens to fit the
   identity is read as binary, and the parser then reports what it finds.
3. first non-blank token ``solid`` and a ``facet`` token in the first 4 KiB: ASCII STL.
4. every complete line in the first and the last 4 KiB is blank or starts with an OBJ keyword
   (v, vt, vn, f, o, g, s, usemtl, mtllib, #), with at least one ``v`` and one ``f`` line: OBJ.
   Engineering decision (2026-11-25): the FS names the 4 KiB prefix, but writers put the faces
   after the vertices, so ``f`` lines are usually beyond it (T4 sphere.obj). The last 4 KiB
   are read too, which keeps detection O(1) in the file size.
5. otherwise ``FILE_UNREADABLE``.

Text rules ignore a UTF-8 BOM and accept CRLF; text containing a NUL byte is not text. The
extension is used only to add the notice ``EXTENSION_MISMATCH`` when it names another format
family. It is never an error and never changes the result.
"""

from dataclasses import dataclass
from enum import StrEnum
import re
import struct
from typing import Final

WINDOW: Final = 4096
STL_HEADER: Final = 80
STL_RECORD: Final = 50
BOM: Final = b"\xef\xbb\xbf"
FILE_UNREADABLE: Final = "FILE_UNREADABLE"
EXTENSION_MISMATCH: Final = "EXTENSION_MISMATCH"
OBJ_KEYWORDS: Final = frozenset({b"v", b"vt", b"vn", b"f", b"o", b"g", b"s", b"usemtl", b"mtllib"})
_PLY_MAGIC = re.compile(rb"\Aply\r?\n")
_PLY_FORMAT = re.compile(rb"^format[ \t]+(\S+)[ \t]+\S+[ \t]*\r?$", re.MULTILINE)
_FACET = re.compile(rb"(?<![A-Za-z0-9_])facet(?![A-Za-z0-9_])")


class FileFormat(StrEnum):
    STL_BINARY = "stl_binary"
    STL_ASCII = "stl_ascii"
    OBJ = "obj"
    PLY_ASCII = "ply_ascii"
    PLY_BIN_LE = "ply_bin_le"
    PLY_BIN_BE = "ply_bin_be"


_PLY_FORMATS: Final = {
    b"ascii": FileFormat.PLY_ASCII,
    b"binary_little_endian": FileFormat.PLY_BIN_LE,
    b"binary_big_endian": FileFormat.PLY_BIN_BE,
}
_FAMILY: Final = {
    FileFormat.STL_BINARY: "stl", FileFormat.STL_ASCII: "stl", FileFormat.OBJ: "obj",
    FileFormat.PLY_ASCII: "ply", FileFormat.PLY_BIN_LE: "ply", FileFormat.PLY_BIN_BE: "ply",
}  # fmt: skip


@dataclass(frozen=True)
class Detection:
    """``format`` is None exactly when ``reason_code`` is FILE_UNREADABLE."""

    format: FileFormat | None
    reason_code: str | None = None
    notices: tuple[str, ...] = ()


def _ply(head: bytes) -> Detection:
    m = _PLY_FORMAT.search(head.split(b"end_header", 1)[0])
    fmt = _PLY_FORMATS.get(m.group(1)) if m else None
    return Detection(fmt) if fmt else Detection(None, FILE_UNREADABLE)


def _is_binary_stl(head: bytes, size: int) -> bool:
    if size < STL_HEADER + 4 or len(head) < STL_HEADER + 4:
        return False
    n = int(struct.unpack_from("<I", head, STL_HEADER)[0])
    return size == STL_HEADER + 4 + STL_RECORD * n


def _is_ascii_stl(text: bytes) -> bool:
    tokens = text.split(None, 1)
    return bool(tokens) and tokens[0] == b"solid" and _FACET.search(text[:WINDOW]) is not None


def _complete_lines(window: bytes, *, cut_first: bool, cut_last: bool) -> list[bytes]:
    lines = window.splitlines()
    if cut_first and lines:
        lines = lines[1:]  # may start mid-line
    if cut_last and lines and not window.endswith((b"\n", b"\r")):
        lines = lines[:-1]  # may end mid-line
    return lines


def _is_obj(head: bytes, tail: bytes, *, whole: bool) -> bool:
    lines = _complete_lines(head, cut_first=False, cut_last=not whole)
    if not whole:
        lines += _complete_lines(tail, cut_first=True, cut_last=False)
    seen: set[bytes] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(b"#"):
            continue
        keyword = stripped.split(None, 1)[0]
        if keyword not in OBJ_KEYWORDS:
            return False
        seen.add(keyword)
    return b"v" in seen and b"f" in seen


def _notices(fmt: FileFormat, extension: str | None) -> tuple[str, ...]:
    if extension is None:
        return ()
    ext = extension.lower().lstrip(".")
    return () if ext == _FAMILY[fmt] or ext not in _FAMILY.values() else (EXTENSION_MISMATCH,)


def detect_format(
    head: bytes, size: int, *, tail: bytes = b"", extension: str | None = None
) -> Detection:
    """Classify a file from its first bytes (``head``), its ``size`` and its last bytes.

    ``head`` must hold the first ``min(size, 4096)`` bytes and ``tail`` the last
    ``min(size, 4096)`` bytes (``tail`` may be omitted when ``head`` is the whole file).
    """
    if size < 0 or len(head) > size:
        raise ValueError("size must be >= len(head) >= 0")
    head = head[:WINDOW] if size > WINDOW else head
    whole = len(head) == size
    tail = head if whole else tail[-WINDOW:]
    text = head[len(BOM) :] if head.startswith(BOM) else head

    if _PLY_MAGIC.match(text):
        found = _ply(text)
    elif _is_binary_stl(head, size):
        found = Detection(FileFormat.STL_BINARY)
    elif b"\x00" in text or (not whole and b"\x00" in tail):
        found = Detection(None, FILE_UNREADABLE)
    elif _is_ascii_stl(text):
        found = Detection(FileFormat.STL_ASCII)
    elif _is_obj(text, tail, whole=whole):
        found = Detection(FileFormat.OBJ)
    else:
        found = Detection(None, FILE_UNREADABLE)
    if found.format is None:
        return found
    return Detection(found.format, None, _notices(found.format, extension))


def detect_bytes(data: bytes, *, extension: str | None = None) -> Detection:
    """``detect_format`` over a whole file held in memory."""
    return detect_format(data[:WINDOW], len(data), tail=data[-WINDOW:], extension=extension)
