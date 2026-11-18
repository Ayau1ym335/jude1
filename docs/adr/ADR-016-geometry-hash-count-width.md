# ADR-016 — geometry_sha: vertex and face counts are u64 little-endian

| Field | Value |
|---|---|
| Status | **Accepted** |
| Date | 2026-11-19 |
| Decided by | Ayau — engineering lead (CTO) and product owner |
| Form of approval | Written statement in the implementation session on 2026-11-19: "counts пишутся как u64 little-endian, как в ALG-54" |
| Reversibility | **H** — after the first approval is bound to a geometry_sha, changing the layout invalidates every stored hash |
| Replaces | No IDR. Resolves a conflict between two Proposed texts under ADR-010 / TD-20 |
| Affected WBS tasks | TSK-KRP-02-K, TSK-KRP-02-V (FN-KRP-02); every task that reads or compares geometry_sha (approval, export, replay) |

## Context

ALG-54 (ALGORITHM_CATALOG_v1.0, CAD_GEOMETRY_ENGINE_DESIGN_v1.0 §ALG-54 and the "Mathematical Model" row of FN-KRP-02) defines the canonical geometry hash as:

> geometry_sha256 = SHA-256("JGEO1" ‖ nV (u64 LE) ‖ nF (u64 LE) ‖ V float64 LE row-major with −0.0 → +0.0 ‖ F int32 LE row-major)

The "Processing Algorithm" row of FN-KRP-02 in FUNCTION_TECHNICAL_SPECIFICATIONS_v1.0 wrote the counts as `uint32LE(N) ‖ uint32LE(M)`. The two layouts give different hashes for every mesh. The discrepancy was found while implementing XC-FND-12.

## Decision

The counts nV and nF are written as **unsigned 64-bit little-endian integers**, exactly as in ALG-54. The rest of the layout is unchanged.

```
"JGEO1" (5 ASCII bytes) ‖ nV u64 LE ‖ nF u64 LE ‖ V float64 LE row-major (−0.0 → +0.0) ‖ F int32 LE row-major
```

## Consequences

- The FN-KRP-02 Processing Algorithm row is corrected to `uint64LE(N) ‖ uint64LE(M)`. Recorded with XC-FND-10, documentation baseline alignment.
- TSK-KRP-02-K implements this layout. TSK-KRP-02-V verifies it against an independent byte-level construction.
- The geometry hash is separate from the jude-arr/1 blob hash (XC-FND-12). The two are not interchangeable.
