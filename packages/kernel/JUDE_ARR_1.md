# jude-arr/1: canonical array container

This is the binary format of kernel array blobs: meshes (DS-01) and, later, fields such as DS-13. It is defined by XC-FND-12 under IDR-15 and TQ-25: an own minimal header, little-endian raw arrays, no pickle and no zip timestamps. The reference implementation is [jarr.py](src/jude_kernel/core/jarr.py).

## Why the format is canonical

Blobs are addressed by the SHA-256 of their bytes (IF-04, DS-19). So the same content must always produce the same bytes. jude-arr/1 therefore allows exactly **one** encoding for a given set of arrays and metadata, and the decoder refuses every other encoding. For every byte string `b` that `decode` accepts, `encode(*decode(b)) == b`. The property test `test_pt_any_accepted_bytes_are_canonical` flips random bytes to check this.

## Layout

All integers are little-endian.

| Offset | Size | Content |
|---|---|---|
| 0 | 8 | Magic `JUDEARR1` (ASCII) |
| 8 | 4 | `header_len`, u32: length of the header in bytes (at most 1 MiB) |
| 12 | `header_len` | Header: canonical JSON, ASCII |
| … | 0–7 | Zero bytes up to the next multiple of 8 |
| … | per array | Raw array bytes in C order, then zero bytes up to the next multiple of 8 |

The file ends exactly after the last array's padding. Nothing may follow it.

## Header

The header is serialised with sorted keys, separators `,` and `:` (no spaces) and ASCII escapes for non-ASCII characters. It has exactly three keys:

```json
{"arrays":[{"dtype":"<f8","name":"V","shape":[4,3]}],"meta":{"frame":"F_scan","kind":"mesh"},"schema":"jude-arr/1"}
```

- **`arrays`:** one entry per array, sorted by `name`, each with exactly `dtype`, `name` and `shape`.
  - `name` matches `[A-Za-z][A-Za-z0-9_.]{0,63}`.
  - `dtype` is one of `<f8`, `<f4`, `<i8`, `<i4`, `<u4`, `<u1`.
  - `shape` is a list of 0 to 4 non-negative integers.
  - There are at most 256 arrays.
- **`meta`:** flat, with keys matching `[a-z][a-z0-9_]{0,63}`. Values are a string, a boolean, `null` or an integer within ±2^53. Floats are not allowed, because their text form is not canonical across serialisers.
- **`schema`:** always `"jude-arr/1"`.

## Rules for array values

- Float arrays hold only finite values and no `-0.0`. The encoder turns `-0.0` into `+0.0`, and the decoder rejects NaN, ±Inf and `-0.0`.
- Big-endian input is stored little-endian.
- Decoded arrays are read-only views of the blob bytes.

## Mesh profile (DS-01)

A DS-01 mesh is a jude-arr/1 container with these contents:

| Element | Name | dtype / value |
|---|---|---|
| Array | `V` | `<f8 [n,3]`, millimetres |
| Array | `F` | `<i4 [m,3]` |
| Array, optional | `face_tags` | `<u1 [m]`, bit flags 1/2/4/8/16 |
| Array, optional | `vattr.<name>` | `<f8 [n]`, one per vertex attribute |
| Meta | `kind` | `"mesh"` |
| Meta | `frame` | `F_file` / `F_scan` / `F_anat` / `F_export` |
| Meta | `display_only` | boolean |

`decode_mesh` also checks the full set of MeshArrays invariants, for example `0 ≤ F < n`.

## Pinned example

`packages/kernel/tests/test_core_jarr.py::test_golden_bytes` pins the SHA-256 of a small tetrahedron mesh at `381143dd…cd0bf57`. Any change to the layout breaks that test.

**A layout change is a new format.** Introduce `jude-arr/2` with a new magic and schema id. Do not edit jude-arr/1: stored blobs and approvals are bound to its bytes.

## Not covered here

- `geometry_sha` (ALG-54, layout `JGEO1`) is a separate hash over V and F, and belongs to TSK-KRP-02-K. Note that the integer width of nV and nF differs between ALG-54 (u64) and the FN-KRP-02 specification (uint32). That task must settle it.
- jude-mesh/1 (DS-14) is the display payload format, not this one.
