"""jude-arr/1: canonical binary container for kernel arrays (IDR-15, TQ-25, TD-20).

Blobs are addressed by the SHA-256 of their bytes, so equal content must give equal bytes.
The format therefore has exactly one valid encoding for a given set of arrays and metadata,
and the decoder accepts only that encoding: for every ``b`` that ``decode`` accepts,
``encode(*decode(b)) == b``. No pickle, no zip, no timestamps.

Layout (all integers little-endian; see packages/kernel/JUDE_ARR_1.md):

    offset 0   magic        8 bytes  b"JUDEARR1"
    offset 8   header_len   u32      length of the header JSON in bytes
    offset 12  header       UTF-8    canonical JSON (below), then zero padding to 8 bytes
    ...        arrays       raw      in header order, C order, each zero-padded to 8 bytes
    EOF        exactly at the end of the last padded array

Header JSON, serialised with sorted keys, separators (",", ":"), ASCII only:

    {"arrays":[{"dtype":"<f8","name":"V","shape":[n,3]}, ...],
     "meta":{...},
     "schema":"jude-arr/1"}

- arrays are sorted by name; names match ``NAME_RE``; dtypes are from ``DTYPES``;
- float arrays are finite and hold no -0.0 (canonicalised to +0.0 by ``encode``);
- meta values are str, bool, None or int within +-2**53 (no floats: their text form is not
  canonical across serialisers).
"""

from collections.abc import Mapping
import json
import re
import struct
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from jude_kernel.core.errors import JarrFormatError
from jude_kernel.core.mesh import Frame, MeshArrays, canonical_float

SCHEMA = "jude-arr/1"
MAGIC = b"JUDEARR1"
ALIGN = 8
MAX_HEADER_BYTES = 1 << 20
MAX_ARRAYS = 256
MAX_NDIM = 4
MAX_INT_META = 1 << 53
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,63}$")
META_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DTYPES: dict[str, np.dtype] = {
    "<f8": np.dtype("<f8"),
    "<f4": np.dtype("<f4"),
    "<i8": np.dtype("<i8"),
    "<i4": np.dtype("<i4"),
    "<u4": np.dtype("<u4"),
    "<u1": np.dtype("<u1"),
}

MetaValue = str | int | bool | None
Arrays = Mapping[str, NDArray[np.generic]]
Meta = Mapping[str, MetaValue]


def dtype_key(dtype: np.dtype) -> str:
    """Byte-order-explicit key, e.g. '<u1' (numpy itself spells single-byte types '|u1')."""
    return f"<{dtype.kind}{dtype.itemsize}"


def _pad(n: int) -> int:
    return (-n) % ALIGN


def _canonical_header(arrays: list[dict[str, object]], meta: Meta) -> bytes:
    doc = {"arrays": arrays, "meta": dict(meta), "schema": SCHEMA}
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _check_meta(meta: Meta) -> None:
    for key, value in meta.items():
        if not isinstance(key, str) or not META_KEY_RE.fullmatch(key):
            raise JarrFormatError(f"meta key {key!r} is not allowed")
        if value is None or isinstance(value, (str, bool)):
            continue
        if isinstance(value, int) and -MAX_INT_META <= value <= MAX_INT_META:
            continue
        raise JarrFormatError(f"meta[{key}]: only str, bool, None or int within 2**53")


def _canonical_array(name: str, values: NDArray[np.generic]) -> NDArray[np.generic]:
    if not NAME_RE.fullmatch(name):
        raise JarrFormatError(f"array name {name!r} is not allowed")
    src = np.asarray(values)
    key = dtype_key(src.dtype)
    if key not in DTYPES:
        raise JarrFormatError(f"{name}: dtype {src.dtype} is not allowed")
    if src.ndim > MAX_NDIM:
        raise JarrFormatError(f"{name}: more than {MAX_NDIM} dimensions")
    target = DTYPES[key]
    if target.kind == "f":
        try:
            return canonical_float(src, name=name, dtype=target)
        except ValueError as exc:
            raise JarrFormatError(str(exc)) from exc
    arr = np.array(src, dtype=target, order="C", copy=True)
    arr.setflags(write=False)
    return arr


def encode(arrays: Arrays, meta: Meta | None = None) -> bytes:
    """Serialise arrays + metadata to canonical jude-arr/1 bytes."""
    meta = meta or {}
    _check_meta(meta)
    if len(arrays) > MAX_ARRAYS:
        raise JarrFormatError(f"more than {MAX_ARRAYS} arrays")
    names = sorted(arrays)
    canon = [_canonical_array(n, arrays[n]) for n in names]
    entries: list[dict[str, object]] = [
        {"dtype": dtype_key(a.dtype), "name": n, "shape": [int(d) for d in a.shape]}
        for n, a in zip(names, canon, strict=True)
    ]
    header = _canonical_header(entries, meta)
    if len(header) > MAX_HEADER_BYTES:
        raise JarrFormatError("header too large")
    parts = [MAGIC, struct.pack("<I", len(header)), header, b"\0" * _pad(12 + len(header))]
    for a in canon:
        raw = a.tobytes(order="C")
        parts.append(raw)
        parts.append(b"\0" * _pad(len(raw)))
    return b"".join(parts)


def decode(data: bytes) -> tuple[dict[str, NDArray[np.generic]], dict[str, MetaValue]]:
    """Parse canonical jude-arr/1 bytes. Arrays are read-only views of ``data``."""
    if not isinstance(data, bytes):
        raise JarrFormatError("bytes required")
    if len(data) < 12 or data[:8] != MAGIC:
        raise JarrFormatError("not a jude-arr/1 container (magic)")
    (header_len,) = struct.unpack_from("<I", data, 8)
    if header_len > MAX_HEADER_BYTES or 12 + header_len > len(data):
        raise JarrFormatError("header length out of range")
    header = data[12 : 12 + header_len]
    try:
        doc = json.loads(header.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JarrFormatError("header is not ASCII JSON") from exc
    if not isinstance(doc, dict) or set(doc) != {"arrays", "meta", "schema"}:
        raise JarrFormatError("header must have exactly arrays, meta, schema")
    if doc["schema"] != SCHEMA:
        raise JarrFormatError(f"unsupported schema {doc['schema']!r}")
    meta, entries = doc["meta"], doc["arrays"]
    if not isinstance(meta, dict) or not isinstance(entries, list):
        raise JarrFormatError("header arrays/meta have the wrong type")
    _check_meta(meta)
    if len(entries) > MAX_ARRAYS:
        raise JarrFormatError(f"more than {MAX_ARRAYS} arrays")

    pos = 12 + header_len
    if any(data[pos : pos + _pad(pos)]) or pos + _pad(pos) > len(data):
        raise JarrFormatError("header padding must be zero bytes")
    pos += _pad(pos)

    arrays: dict[str, NDArray[np.generic]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"dtype", "name", "shape"}:
            raise JarrFormatError("array entry must have exactly dtype, name, shape")
        name, dtype_key, shape = entry["name"], entry["dtype"], entry["shape"]
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in arrays:
            raise JarrFormatError(f"array name {name!r} invalid or repeated")
        if dtype_key not in DTYPES:
            raise JarrFormatError(f"{name}: dtype {dtype_key!r} is not allowed")
        if (
            not isinstance(shape, list)
            or len(shape) > MAX_NDIM
            or not all(isinstance(d, int) and not isinstance(d, bool) and d >= 0 for d in shape)
        ):
            raise JarrFormatError(f"{name}: invalid shape")
        dtype = DTYPES[dtype_key]
        count = int(np.prod(shape, dtype=np.int64)) if shape else 1
        nbytes = count * dtype.itemsize
        end = pos + nbytes
        if end + _pad(nbytes) > len(data):
            raise JarrFormatError(f"{name}: truncated")
        arr = np.frombuffer(data, dtype=dtype, count=count, offset=pos).reshape(shape)
        if dtype.kind == "f":
            if not np.all(np.isfinite(arr)):
                raise JarrFormatError(f"{name}: non-finite value")
            if np.any((arr == 0) & np.signbit(arr)):
                raise JarrFormatError(f"{name}: -0.0 is not canonical")
        if any(data[end : end + _pad(nbytes)]):
            raise JarrFormatError(f"{name}: padding must be zero bytes")
        arrays[name] = arr
        pos = end + _pad(nbytes)

    if pos != len(data):
        raise JarrFormatError("trailing bytes after the last array")
    if [e["name"] for e in entries] != sorted(arrays):
        raise JarrFormatError("arrays must be sorted by name")
    if _canonical_header(entries, meta) != header:
        raise JarrFormatError("header JSON is not in canonical form")
    return arrays, meta


# --- DS-01 MeshArrays codec ---------------------------------------------------------------

MESH_KIND = "mesh"
ATTR_PREFIX = "vattr."


def encode_mesh(mesh: MeshArrays) -> bytes:
    arrays: dict[str, NDArray[np.generic]] = {"F": mesh.F, "V": mesh.V}
    if mesh.face_tags is not None:
        arrays["face_tags"] = mesh.face_tags
    for name, values in mesh.vertex_attrs.items():
        arrays[ATTR_PREFIX + name] = values
    meta: dict[str, MetaValue] = {
        "display_only": mesh.display_only,
        "frame": mesh.frame.value,
        "kind": MESH_KIND,
    }
    return encode(arrays, meta)


def decode_mesh(data: bytes) -> MeshArrays:
    arrays, meta = decode(data)
    if set(meta) != {"display_only", "frame", "kind"} or meta["kind"] != MESH_KIND:
        raise JarrFormatError("not a DS-01 mesh container")
    if not isinstance(meta["display_only"], bool) or not isinstance(meta["frame"], str):
        raise JarrFormatError("mesh meta has the wrong type")
    allowed = {"V", "F", "face_tags"}
    attrs = {k[len(ATTR_PREFIX) :]: v for k, v in arrays.items() if k.startswith(ATTR_PREFIX)}
    unknown = set(arrays) - allowed - {ATTR_PREFIX + k for k in attrs}
    if unknown or "V" not in arrays or "F" not in arrays:
        raise JarrFormatError(f"mesh arrays must be V, F, face_tags, vattr.*; got {sorted(arrays)}")
    expected = {"V": "<f8", "F": "<i4", "face_tags": "<u1"}
    for key, dt in expected.items():
        if key in arrays and dtype_key(arrays[key].dtype) != dt:
            raise JarrFormatError(f"mesh array {key} must be {dt}")
    if any(dtype_key(a.dtype) != "<f8" for a in attrs.values()):
        raise JarrFormatError("vertex attributes must be <f8")
    try:
        return MeshArrays.create(
            arrays["V"],
            arrays["F"],
            frame=Frame(meta["frame"]),
            face_tags=arrays.get("face_tags"),
            vertex_attrs=MappingProxyType(attrs),
            display_only=meta["display_only"],
        )
    except ValueError as exc:
        raise JarrFormatError(f"mesh contract: {exc}") from exc
